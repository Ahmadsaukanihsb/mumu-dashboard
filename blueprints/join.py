import threading, time, uuid

from flask import Blueprint, request, jsonify

from models import accounts, servers, settings, _data_lock, _join_threads, _join_threads_lock, log_activity, log_account, save_data, decrypt_cookie
from services.adb import find_adb, get_serial, adb_connect, adb_force_stop_roblox, adb_cmd
from services.roblox import build_join_link
from services.mumu import launch_mumu

join_bp = Blueprint('join', __name__)

def _is_cloudphone(acc):
    return bool(acc.get('package_name') and acc.get('device_id'))

def _queue_remote_join(acc, link, sv):
    from blueprints.mailbox import mailbox_commands, mailbox_results, command_lock
    cmd_id = f'join-{uuid.uuid4().hex[:8]}'
    command = {
        'id': cmd_id,
        'type': 'join',
        'account': acc['name'],
        'package': acc['package_name'],
        'link': link,
        'timestamp': time.time(),
        'status': 'pending'
    }
    with command_lock:
        mailbox_commands.append(command)
        mailbox_results[cmd_id] = {'status': 'pending', 'message': 'Menunggu remote monitor...'}
    log_account(acc['id'], acc['name'], f'Join command queued → remote monitor ({acc.get("device_id")})')
    return cmd_id

@join_bp.route('/api/accounts/<acc_id>/join', methods=['POST'])
def join_server(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    sv = None
    if acc.get('server_id'):
        sv = next((s for s in servers if s['id'] == acc['server_id']), None)
    if not sv and servers:
        sv = servers[0]
    if not sv:
        return jsonify({'error': 'No server configured'}), 400
    link = build_join_link(sv)
    if not link:
        return jsonify({'error': 'Could not build join link'}), 400
    with _data_lock:
        acc['status'] = 'joining'
        acc['active'] = True
    save_data()
    log_account(acc['id'], acc['name'], f'Joining server "{sv["name"]}"')
    if _is_cloudphone(acc):
        cmd_id = _queue_remote_join(acc, link, sv)
        return jsonify({'status': 'joining', 'link': link, 'via': 'remote_monitor', 'command_id': cmd_id})
    with _join_threads_lock:
        if acc['id'] not in _join_threads:
            _join_threads.add(acc['id'])
            threading.Thread(target=launch_mumu, args=(acc, link, sv, acc['id']), daemon=True).start()
    return jsonify({'status': 'joining', 'link': link})

@join_bp.route('/api/join-all', methods=['POST'])
def join_all():
    if not servers:
        return jsonify({'error': 'No servers configured'}), 400
    sv = servers[0]
    link = build_join_link(sv)
    if not link:
        return jsonify({'error': 'Could not build join link'}), 400
    count = 0
    remote_count = 0
    for acc in accounts:
        if acc.get('cookie') or _is_cloudphone(acc):
            with _data_lock:
                acc['status'] = 'joining'
                acc['active'] = True
            if _is_cloudphone(acc):
                _queue_remote_join(acc, link, sv)
                remote_count += 1
            else:
                with _join_threads_lock:
                    if acc['id'] not in _join_threads:
                        _join_threads.add(acc['id'])
                        threading.Thread(target=launch_mumu, args=(acc, link, sv, acc['id']), daemon=True).start()
                        count += 1
    save_data()
    log_activity(f'Join all: {count} MuMu + {remote_count} Cloudphone accounts starting')
    return jsonify({'status': 'joining', 'count': count, 'remote_count': remote_count})

@join_bp.route('/api/accounts/<acc_id>/disconnect', methods=['POST'])
def disconnect_account(acc_id):
    acc = None
    with _data_lock:
        found = next((a for a in accounts if a['id'] == acc_id), None)
        if found:
            found['active'] = False
            found['status'] = 'idle'
            acc = found
    if acc:
        save_data()
        log_account(acc['id'], acc['name'], 'Disconnected')
    return jsonify({'success': True})

@join_bp.route('/api/accounts/<acc_id>/rollback', methods=['POST'])
def rollback_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    name = acc.get('name', '?')
    sv = next((s for s in servers if acc.get('server_ids') and s['id'] in acc.get('server_ids')), None) or (servers[0] if servers else None)
    if not sv:
        return jsonify({'error': 'No server configured'}), 400
    link = build_join_link(sv)
    if not link:
        return jsonify({'error': 'Failed to build join link'}), 500
    if _is_cloudphone(acc):
        _queue_remote_join(acc, link, sv)
        acc['status'] = 'rollback'
        log_account(acc_id, name, f'Rollback → remote monitor rejoin ke {sv["name"]}')
        log_activity(f'[{name}] Rollback via remote monitor')
        save_data()
        return jsonify({'success': True, 'message': f'Rollback via remote monitor → {sv["name"]}'})
    instance = acc.get('mumu_instance')
    serial = None
    if instance is not None:
        serial = get_serial(instance)
    if not serial:
        serial = acc.get('serial', '')
    if not serial:
        return jsonify({'error': f'No serial for account {name}'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500
    try:
        adb_force_stop_roblox(serial)
        time.sleep(2)
        adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'"], serial)
        acc['status'] = 'rollback'
        log_account(acc_id, name, f'Rollback: force-stop + rejoin ke {sv["name"]}')
        log_activity(f'[{name}] Rollback executed (force-stop + rejoin)')
        save_data()
        return jsonify({'success': True, 'message': f'Rollback: force-stop + rejoin {sv["name"]}'})
    except Exception as e:
        log_activity(f'[{name}] Rollback error: {e}')
        return jsonify({'error': str(e)}), 500
