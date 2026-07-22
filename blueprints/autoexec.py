import time
import uuid
import threading

from flask import Blueprint, jsonify, request

from models import accounts, settings, log_activity
from services.adb import (
    get_serial, adb_connect, detect_autoexec_folders
)
from blueprints.remote import remote_monitors

autoexec_bp = Blueprint('autoexec', __name__)

# In-memory scan results: { scan_id: { 'status': 'scanning'|'done', 'vm': {...}, 'cloudphone': {...}, 'started_at': ts } }
_scans = {}
_scans_lock = threading.Lock()
SCAN_TTL = 300  # hasil scan disimpan 5 menit


def _cleanup_scans():
    now = time.time()
    with _scans_lock:
        expired = [k for k, v in _scans.items() if now - v.get('started_at', 0) > SCAN_TTL]
        for k in expired:
            del _scans[k]


def _scan_vm(serial, package, label=''):
    """Scan satu VM via ADB. Blocking."""
    ok, msg = adb_connect(serial)
    if not ok:
        return {'label': label or serial, 'serial': serial, 'package': package,
                'status': 'error', 'message': f'ADB: {msg}', 'found': []}
    result = detect_autoexec_folders(serial.strip(), package)
    return {
        'label': label or serial,
        'serial': serial,
        'package': package,
        'status': 'ok',
        'found': result['found'],
        'checked_count': len(result['checked']),
        'error': result['error'],
    }


def _send_cloudphone_detect_command(acc, scan_id):
    """Queue a detect_autoexec command for a cloudphone account."""
    from blueprints.mailbox import mailbox_commands, mailbox_results, command_lock
    cmd_id = f'autoexec-{uuid.uuid4().hex[:8]}'
    command = {
        'id': cmd_id,
        'type': 'detect_autoexec',
        'account': acc.get('name', ''),
        'package': acc.get('package_name', ''),
        'scan_id': scan_id,
        'timestamp': time.time(),
        'status': 'pending',
    }
    with command_lock:
        mailbox_commands.append(command)
        mailbox_results[cmd_id] = {'status': 'pending', 'message': 'Menunggu remote monitor...'}
    return cmd_id


@autoexec_bp.route('/api/autoexec/scan', methods=['POST'])
def scan_autoexec():
    """Scan auto-execute folders di semua VM lokal + semua cloudphone.

    Body (optional):
        include_vm: bool (default true)
        include_cloudphone: bool (default true)
    """
    _cleanup_scans()
    data = request.get_json(silent=True) or {}
    include_vm = data.get('include_vm', True)
    include_cloudphone = data.get('include_cloudphone', True)

    scan_id = uuid.uuid4().hex[:12]
    scan = {
        'scan_id': scan_id,
        'status': 'scanning',
        'started_at': time.time(),
        'vm': [],
        'cloudphone': [],
    }
    with _scans_lock:
        _scans[scan_id] = scan

    # --- Scan VM lokal (synchronous, cepat) ---
    if include_vm:
        serials = settings.get('mumu_serials', [])
        for idx, serial in enumerate(serials):
            if not serial or not serial.strip():
                continue
            serial = serial.strip()
            acc = next((a for a in accounts if a.get('mumu_instance') == idx), None)
            package = acc.get('package_name', '') if acc else ''
            label = acc.get('name', f'VM #{idx}') if acc else f'VM #{idx}'
            vm_result = _scan_vm(serial, package, label)
            vm_result['instance'] = idx
            vm_result['type'] = 'vm'
            scan['vm'].append(vm_result)

    # --- Scan cloudphone (async via command queue) ---
    cloudphone_accounts = []
    if include_cloudphone:
        for acc in accounts:
            if acc.get('device_id') and acc.get('package_name'):
                # Cek device online
                did = acc['device_id']
                info = remote_monitors.get(did, {})
                last_report = info.get('last_report', 0)
                is_online = (time.time() - last_report) < 180 if last_report > 0 else False
                cloudphone_accounts.append((acc, is_online))

        for acc, is_online in cloudphone_accounts:
            entry = {
                'label': acc.get('name', '?'),
                'device_id': acc.get('device_id', ''),
                'package': acc.get('package_name', ''),
                'type': 'cloudphone',
                'online': is_online,
                'status': 'queued' if is_online else 'offline',
                'found': [],
            }
            if is_online:
                cmd_id = _send_cloudphone_detect_command(acc, scan_id)
                entry['command_id'] = cmd_id
            scan['cloudphone'].append(entry)

    # Jika tidak ada cloudphone yang perlu ditunggu, langsung done
    pending_cp = [c for c in scan['cloudphone'] if c['status'] == 'queued']
    if not pending_cp:
        scan['status'] = 'done'

    log_activity(f'Autoexec scan {scan_id}: {len(scan["vm"])} VM, {len(scan["cloudphone"])} cloudphone ({len(pending_cp)} queued)')
    return jsonify({'success': True, 'scan_id': scan_id,
                    'vm_scanned': len(scan['vm']),
                    'cloudphone_queued': len(pending_cp),
                    'cloudphone_total': len(scan['cloudphone'])})


@autoexec_bp.route('/api/autoexec/scan/<scan_id>', methods=['GET'])
def scan_result(scan_id):
    """Ambil hasil scan. Cloudphone results di-update via /api/remote/autoexec/report."""
    _cleanup_scans()
    with _scans_lock:
        scan = _scans.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found atau sudah expired'}), 404

    # Cek apakah cloudphone results sudah masuk (via report endpoint yang mengupdate mailbox_results)
    from blueprints.mailbox import mailbox_results, command_lock
    still_pending = 0
    for cp in scan['cloudphone']:
        if cp['status'] != 'queued':
            continue
        cmd_id = cp.get('command_id', '')
        with command_lock:
            result = mailbox_results.get(cmd_id, {})
        if result.get('status') in ('completed', 'done'):
            # Data sudah diisi oleh /api/remote/autoexec/report via _update_cloudphone_result
            pass  # cp sudah diupdate oleh endpoint report
        elif result.get('status') == 'failed':
            cp['status'] = 'error'
            cp['message'] = result.get('message', 'Failed')
        else:
            still_pending += 1

    if still_pending == 0 and scan['status'] == 'scanning':
        scan['status'] = 'done'

    total_found = sum(len(v.get('found', [])) for v in scan['vm'])
    total_found += sum(len(c.get('found', [])) for c in scan['cloudphone'])

    return jsonify({
        'scan_id': scan_id,
        'status': scan['status'],
        'vm': scan['vm'],
        'cloudphone': scan['cloudphone'],
        'total_folders': total_found,
        'pending': still_pending,
    })


@autoexec_bp.route('/api/remote/autoexec/report', methods=['POST'])
def autoexec_report():
    """Terima hasil deteksi dari remote monitor (cloudphone)."""
    data = request.get_json(silent=True) or {}
    device_id = data.get('device_id', '')
    scan_id = data.get('scan_id', '')
    package = data.get('package', '')
    found = data.get('found', [])

    if not scan_id:
        return jsonify({'error': 'scan_id required'}), 400

    with _scans_lock:
        scan = _scans.get(scan_id)
    if not scan:
        return jsonify({'error': 'Scan not found atau expired'}), 404

    # Update cloudphone entry yang cocok
    updated = False
    for cp in scan['cloudphone']:
        if cp.get('device_id') == device_id and cp.get('package') == package and cp['status'] == 'queued':
            cp['status'] = 'ok'
            cp['found'] = found
            updated = True
            break

    # Jika package kosong (scan semua), update entry pertama yang match device_id
    if not updated and not package:
        for cp in scan['cloudphone']:
            if cp.get('device_id') == device_id and cp['status'] == 'queued':
                cp['status'] = 'ok'
                cp['found'] = found
                updated = True
                break

    # Tandai command sebagai complete
    from blueprints.mailbox import mailbox_results, command_lock
    for cp in scan['cloudphone']:
        cmd_id = cp.get('command_id', '')
        if cmd_id and cp.get('device_id') == device_id:
            with command_lock:
                if cmd_id in mailbox_results:
                    mailbox_results[cmd_id] = {'status': 'completed', 'message': f'{len(found)} folders found'}

    log_activity(f'Autoexec report dari {device_id}: {len(found)} folders')
    return jsonify({'success': True, 'updated': updated})
