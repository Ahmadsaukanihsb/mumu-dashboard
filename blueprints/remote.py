import json, time

from flask import Blueprint, jsonify, request

from models import accounts, servers, settings, _data_lock, save_data, encrypt_cookie, log_activity, log_account
from services.webhook import send_webhook

remote_bp = Blueprint('remote', __name__)

remote_monitors = {}

@remote_bp.route('/api/remote/register', methods=['POST'])
def remote_register():
    data = request.json or {}
    device_id = data.get('device_id', '')
    serial = data.get('serial', '')
    packages = data.get('packages', [])
    if not device_id or not packages:
        return jsonify({'error': 'device_id and packages required'}), 400

    existing_pkgs = {(acc.get('device_id', ''), acc.get('package_name', '')) for acc in accounts}
    auto_created = []

    for pkg_info in packages:
        pkg = pkg_info.get('name', '')
        label = pkg_info.get('label', pkg.split('.')[-1])
        combo = (device_id, pkg)
        if pkg and combo not in existing_pkgs:
            acc_name = f"{label}-{device_id}" if device_id else label
            acc = {
                'id': str(int(time.time() * 1000000) + hash(f"{device_id}{pkg}") % 100000),
                'name': acc_name,
                'cookie': '',
                'active': False,
                'status': 'idle',
                'last_joined': None,
                'server_id': '',
                'server_ids': [],
                'mumu_instance': 0,
                'package_name': pkg,
                'device_id': device_id,
                'app_label': label,
                'auto_join': False,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'remote': True
            }
            with _data_lock:
                accounts.append(acc)
            auto_created.append(pkg)
            log_activity(f'Auto-created account: {acc_name} ({pkg})')

    if auto_created:
        save_data()

    account_map = {}
    for acc in accounts:
        if acc.get('device_id') == device_id:
            pkg = acc.get('package_name', '')
            if pkg:
                account_map[pkg] = acc.get('name', pkg)

    remote_monitors[device_id] = {
        'device_id': device_id,
        'serial': serial,
        'packages': [{'name': p.get('name', ''), 'label': p.get('label', '')} for p in packages],
        'registered_at': time.time(),
        'last_report': 0
    }
    log_activity(f'Remote monitor registered: {device_id} ({len(packages)} packages, {len(auto_created)} new)')
    return jsonify({
        'success': True,
        'account_map': account_map,
        'accounts': len(accounts),
        'auto_created': auto_created
    })

@remote_bp.route('/api/remote/monitors', methods=['GET'])
def remote_monitors_list():
    result = []
    for device_id, info in remote_monitors.items():
        packages = info.get('packages', [])
        pkg_status = []
        for pkg_info in packages:
            if isinstance(pkg_info, str):
                pkg = pkg_info
                label = pkg.split('.')[-1]
            else:
                pkg = pkg_info.get('name', '')
                label = pkg_info.get('label', pkg.split('.')[-1])
            matched_account = None
            for acc in accounts:
                if acc.get('device_id') == device_id and acc.get('package_name') == pkg:
                    matched_account = acc.get('name', '')
                    break
            pkg_status.append({
                'package': pkg,
                'label': label,
                'account': matched_account or 'Unassigned',
                'has_account': bool(matched_account)
            })
        result.append({
            'device_id': device_id,
            'packages': pkg_status,
            'registered_at': info.get('registered_at', 0),
            'package_count': len(packages)
        })
    return jsonify({'monitors': result, 'count': len(result)})

@remote_bp.route('/api/remote/cookie', methods=['POST'])
def remote_cookie():
    data = request.json or {}
    package = data.get('package', '')
    cookie = data.get('cookie', '')
    if not package or not cookie:
        return jsonify({'error': 'package and cookie required'}), 400
    for acc in accounts:
        if acc.get('package_name') == package:
            if not acc.get('cookie') or acc['cookie'] == '':
                acc['cookie'] = encrypt_cookie(cookie)
                acc['status'] = 'cookie_ready'
                save_data()
                log_activity(f'Cookie auto-extracted for {package} -> {acc.get("name", "?")}')
                return jsonify({'success': True, 'account': acc.get('name', ''), 'package': package})
            else:
                return jsonify({'success': True, 'account': acc.get('name', ''), 'package': package, 'note': 'Cookie already set'})
    return jsonify({'error': f'No account for package {package}'}), 404

@remote_bp.route('/api/remote/status', methods=['POST'])
def remote_status():
    data = request.json or {}
    account_name = data.get('account_name', '')
    package = data.get('package', '')
    status = data.get('status', 'unknown')
    tc = data.get('thread_count')
    kicked = data.get('kicked')
    print(f'[REMOTE] {account_name} ({package}): {status} tc={tc} kicked={kicked}')
    for acc in accounts:
        if acc.get('name', '').lower() == account_name.lower() or acc.get('package_name') == package:
            old_status = acc.get('status', '')
            acc['status'] = status
            if status in ('in_game', 'monitoring', 'connected', 'active'):
                acc['active'] = True
            elif status in ('kicked', 'disconnected', 'error'):
                acc['active'] = False
                if status == 'kicked' and old_status != 'kicked':
                    send_webhook(
                        f'⚠️ {account_name} — KICKED (Remote)',
                        f'Package: {package}\nKicked: {kicked or "unknown"}',
                        0xffaa00,
                        acc.get('verified_avatar')
                    )
            save_data()
            break
    if account_name:
        log_account(account_name, account_name, f'[Remote] {status} (tc={tc}, kicked={kicked})')
    return jsonify({'success': True})

@remote_bp.route('/api/remote/config', methods=['GET'])
def remote_config():
    account_settings = {}
    for acc in accounts:
        pkg = acc.get('package_name', '')
        if pkg:
            account_settings[pkg] = {
                'auto_join': acc.get('auto_join', False)
            }
    return jsonify({
        'monitor_interval': settings.get('monitor_interval', 5),
        'rejoin_interval': settings.get('rejoin_interval', 2400),
        'thread_threshold': settings.get('thread_threshold', 80),
        'rejoin_delay': settings.get('rejoin_delay', 3),
        'max_retries': settings.get('max_retries', 5),
        'auto_join_enabled': settings.get('auto_join_enabled', True),
        'current_server': servers[0] if servers else {},
        'servers': [{'id': s.get('id'), 'name': s.get('name'), 'place_id': s.get('place_id'), 'type': s.get('type'), 'server_code': s.get('server_code', ''), 'link': s.get('link', '')} for s in servers],
        'account_settings': account_settings
    })

@remote_bp.route('/api/remote/commands', methods=['GET'])
def remote_commands():
    from blueprints.mailbox import mailbox_commands, command_lock
    account = request.args.get('account', '')
    if not account:
        return jsonify({'commands': [], 'count': 0})
    with command_lock:
        pending = [cmd for cmd in mailbox_commands
                   if cmd.get('account') == account and cmd['status'] == 'pending']
    return jsonify({'commands': pending, 'count': len(pending)})

@remote_bp.route('/api/remote/commands/<cmd_id>/complete', methods=['POST'])
def remote_command_complete(cmd_id):
    from blueprints.mailbox import mailbox_commands, mailbox_results, command_lock
    data = request.json or {}
    success = data.get('success', False)
    message = data.get('message', '')
    with command_lock:
        if cmd_id in mailbox_results:
            mailbox_results[cmd_id] = {
                'status': 'completed' if success else 'failed',
                'message': message,
                'completed_at': time.time()
            }
        for cmd in mailbox_commands:
            if cmd['id'] == cmd_id:
                cmd['status'] = 'completed' if success else 'failed'
                break
    return jsonify({'success': True})
