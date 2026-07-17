import os, json, time, threading, tempfile, subprocess, re, urllib.request

from flask import Blueprint, render_template, request, jsonify

from models import accounts, servers, settings, acc_logs, monitor_state, _data_lock, _join_threads, _join_threads_lock, log_activity, log_account, save_data, encrypt_cookie, decrypt_cookie, get_package_name
from services.adb import find_adb, get_serial, adb_connect, adb_force_stop_roblox, adb_cmd, adb_dismiss_dialogs, adb_check_join_failed, auto_push_script_to_vm
from services.roblox import verify_cookie, _adb_extract_cookie, build_join_link
from services.mumu import launch_mumu
from services.webhook import send_webhook
from config import PACKAGE_MAP

accounts_bp = Blueprint('accounts', __name__)

@accounts_bp.route('/api/accounts', methods=['GET'])
def get_accounts():
    now = time.time()
    ri = max(settings.get('rejoin_interval', 2400), 120)
    result = []
    for acc in accounts:
        a = dict(acc)
        st = monitor_state.get(acc.get('id', ''), {})
        gs = st.get('in_game_since', 0)
        ingame = st.get('in_game', False)
        last_intent = st.get('last_intent', 0)
        last_join = a.get('last_join_time', 0)
        next_rejoin = None
        if gs > 0 and ingame:
            next_rejoin = gs + ri
        elif last_intent > 0:
            next_rejoin = last_intent + ri
        elif last_join > 0:
            next_rejoin = last_join + ri
        if next_rejoin:
            a['next_rejoin_in'] = max(0, int(next_rejoin - now))
        else:
            a['next_rejoin_in'] = int(ri)
        from services.delta import delta_key_store
        dk = delta_key_store.get(acc.get('id', ''), {})
        a['delta_key'] = {
            'has_key': bool(dk.get('key')),
            'expires_at': dk.get('expires_at', 0),
            'expires_in': max(0, int(dk.get('expires_at', 0) - now)) if dk.get('expires_at') else None,
            'updated_at': dk.get('updated_at', 0)
        }
        result.append(a)
    return jsonify(result)

@accounts_bp.route('/api/accounts', methods=['POST'])
def add_account():
    data = request.json
    if not data or not data.get('cookie'):
        return jsonify({'error': 'Cookie wajib diisi'}), 400
    if not data.get('name'):
        return jsonify({'error': 'Nama wajib diisi'}), 400
    inst = data.get('mumu_instance', 0)
    serials = settings.get('mumu_serials', [])
    max_idx = len(serials) - 1 if serials else 0
    if not isinstance(inst, int) or inst < 0 or inst > max_idx:
        return jsonify({'error': f'mumu_instance harus 0-{max_idx}'}), 400
    server_id = data.get('server_id', '')
    server_ids = data.get('server_ids', [])
    if not server_ids and server_id:
        server_ids = [server_id]
    used_pkgs = {a.get('package_name') for a in accounts}
    pkg = data.get('package_name', '')
    if not pkg:
        for idx in range(5):
            candidate = PACKAGE_MAP.get(idx, f'com.roblox.client.clone{idx}')
            if candidate not in used_pkgs:
                pkg = candidate
                break
        if not pkg:
            pkg = f'com.roblox.client.clone{len(accounts)}'
    acc = {
        'id': str(int(time.time() * 1000)),
        'name': data.get('name', ''),
        'cookie': encrypt_cookie(data.get('cookie', '')),
        'active': False,
        'status': 'idle',
        'last_joined': None,
        'server_id': server_id,
        'server_ids': server_ids,
        'mumu_instance': data.get('mumu_instance', 0),
        'package_name': pkg,
        'auto_join': data.get('auto_join', False),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with _data_lock:
        accounts.append(acc)
    save_data()
    log_activity(f'Account "{acc["name"]}" ditambahkan (package: {pkg})')
    if settings.get('auto_push_script', True):
        try:
            serial = get_serial(acc.get('mumu_instance', 0))
            if serial:
                adb_connect(serial)
                auto_push_script_to_vm(acc, serial)
        except Exception as e:
            log_activity(f'Auto-push script gagal: {e}', 'warning')
    return jsonify(acc), 201

@accounts_bp.route('/api/accounts/<acc_id>', methods=['PUT'])
def update_account(acc_id):
    data = request.json
    with _data_lock:
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return jsonify({'error': 'Account not found'}), 404
        acc['name'] = data.get('name', acc['name'])
        if 'cookie' in data:
            acc['cookie'] = encrypt_cookie(data['cookie'])
        acc['server_id'] = data.get('server_id', acc['server_id'])
        acc['server_ids'] = data.get('server_ids', acc.get('server_ids', []))
        if not acc['server_ids'] and acc['server_id']:
            acc['server_ids'] = [acc['server_id']]
        acc['mumu_instance'] = data.get('mumu_instance', acc.get('mumu_instance', 0))
        if 'package_name' in data:
            acc['package_name'] = data['package_name']
        aj = data.get('auto_join')
        if aj is not None:
            acc['auto_join'] = aj
        if data.get('auto_join_server_id'):
            acc['server_id'] = data['auto_join_server_id']
            log_activity(f'[{acc["name"]}] Auto-join server diubah')
    save_data()
    log_activity(f'Account "{acc["name"]}" diperbarui')
    return jsonify(acc)

@accounts_bp.route('/api/accounts/<acc_id>', methods=['DELETE'])
def delete_account(acc_id):
    acc = None
    with _data_lock:
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        accounts[:] = [a for a in accounts if a['id'] != acc_id]
        monitor_state.pop(acc_id, None)
        acc_logs.pop(acc_id, None)
    save_data()
    if acc:
        log_activity(f'Account "{acc["name"]}" dihapus')
    return jsonify({'success': True})

@accounts_bp.route('/api/accounts/<acc_id>/verify', methods=['POST'])
def verify_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    cookie = decrypt_cookie(acc.get('cookie', ''))
    if not cookie:
        return jsonify({'valid': False, 'error': 'No cookie'})
    result = verify_cookie(cookie)
    if result['valid']:
        acc['verified_username'] = result['username']
        acc['verified_robux'] = result['robux']
        acc['verified_avatar'] = result['avatar']
        acc['verified_id'] = result.get('id', '')
        save_data()
        return jsonify(result)
    return jsonify({'valid': False, 'error': result.get('error', 'Unknown')})

@accounts_bp.route('/api/accounts/verify-all', methods=['POST'])
def verify_all_accounts():
    results = []
    for acc in accounts:
        cookie = decrypt_cookie(acc.get('cookie', ''))
        if not cookie:
            results.append({'id': acc['id'], 'name': acc['name'], 'valid': False, 'error': 'No cookie'})
            continue
        result = verify_cookie(cookie)
        if result['valid']:
            with _data_lock:
                acc['verified_username'] = result['username']
                acc['verified_robux'] = result['robux']
                acc['verified_avatar'] = result['avatar']
                acc['verified_id'] = result.get('id', '')
            results.append({'id': acc['id'], 'name': acc['name'], 'valid': True, 'username': result['username'], 'robux': result['robux']})
        else:
            results.append({'id': acc['id'], 'name': acc['name'], 'valid': False, 'error': result.get('error', 'unknown')})
    save_data()
    return jsonify({'results': results})

@accounts_bp.route('/api/accounts/scan-vm', methods=['POST'])
def scan_vm_cookies():
    mumu_serials = settings.get('mumu_serials', [])
    from services.mumu import load_vm_display_names
    display_names = load_vm_display_names()
    results = []
    added = 0
    already_exist = 0

    for idx, serial in enumerate(mumu_serials):
        vm_key = f'MuMuPlayerGlobal-12.0-{idx}'
        vm_name = display_names.get(vm_key, f'MuMu-{idx}')
        entry = {'instance': idx, 'vm': vm_name, 'status': 'skipped', 'username': '', 'message': ''}
        if not serial:
            entry['message'] = 'No ADB serial'
            results.append(entry)
            continue

        cookie = _adb_extract_cookie(serial)
        if not cookie:
            entry['status'] = 'not_found'
            entry['message'] = 'Cookie tidak ditemukan'
            results.append(entry)
            continue

        ver = verify_cookie(cookie)
        if not ver.get('valid'):
            entry['status'] = 'invalid'
            entry['message'] = ver.get('error', 'Invalid cookie')
            results.append(entry)
            continue

        username = ver.get('username', 'unknown')
        entry['username'] = username
        existing = next((a for a in accounts if a.get('cookie') == cookie), None)
        if existing:
            already_exist += 1
            entry['status'] = 'exists'
            entry['message'] = f'Sudah ada sebagai "{existing["name"]}"'
            results.append(entry)
            continue

        existing_by_name = next((a for a in accounts if a.get('name', '').lower() == username.lower()), None)
        if existing_by_name:
            already_exist += 1
            entry['status'] = 'exists'
            entry['message'] = f'Already exists as "{existing_by_name["name"]}" (same username)'
            results.append(entry)
            continue

        acc = {
            'id': str(int(time.time() * 1000000 + idx)),
            'name': username,
            'cookie': cookie,
            'active': False,
            'status': 'idle',
            'last_joined': None,
            'server_id': '',
            'server_ids': [],
            'mumu_instance': idx,
            'auto_join': False,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'verified_username': username,
            'verified_robux': ver.get('robux', 0),
            'verified_avatar': ver.get('avatar', ''),
            'verified_id': ver.get('id', ''),
        }
        with _data_lock:
            accounts.append(acc)
        save_data()
        added += 1
        entry['status'] = 'added'
        entry['message'] = f'Berhasil ditambahkan sebagai "{username}"'
        results.append(entry)
        log_activity(f'Auto-import: "{username}" dari {vm_name}')
        if settings.get('auto_push_script', True):
            try:
                auto_push_script_to_vm(acc, serial)
            except Exception as e:
                log_activity(f'Auto-push script gagal ({username}): {e}', 'warning')

    return jsonify({'success': True, 'results': results, 'added': added, 'already_exist': already_exist})

@accounts_bp.route('/api/accounts/<acc_id>/profile', methods=['GET'])
def account_profile(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Not found'}), 404
    profile = {
        'id': acc.get('verified_id', ''),
        'username': acc.get('verified_username', ''),
        'robux': acc.get('verified_robux', 0),
        'avatar': acc.get('verified_avatar', ''),
        'status': acc.get('status', 'unknown'),
        'last_joined': acc.get('last_joined', '-'),
        'auto_join': acc.get('auto_join', False),
        'mumu_instance': acc.get('mumu_instance', 0),
        'created_at': acc.get('created_at', ''),
    }
    uid = acc.get('verified_id', '')

    def roblox_api_fetch(url, cookie):
        try:
            req = urllib.request.Request(url)
            if cookie:
                req.add_header('Cookie', f'.ROBLOSECURITY={cookie}')
            req.add_header('User-Agent', 'Roblox/Win32')
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except:
            return None

    if uid:
        cookie = acc.get('cookie', '')
        user_data = roblox_api_fetch(f'https://users.roblox.com/v1/users/{uid}', '')
        if user_data:
            profile['display_name'] = user_data.get('displayName', '')
            profile['description'] = (user_data.get('description', '') or '')[:200]
            profile['created'] = user_data.get('created', '')[:10]
        friends = roblox_api_fetch(f'https://friends.roblox.com/v1/users/{uid}/friends/count', '')
        if friends:
            profile['friend_count'] = friends.get('count', 0)
        try:
            req = urllib.request.Request('https://presence.roblox.com/v1/presence/users')
            req.add_header('Cookie', f'.ROBLOSECURITY={cookie}')
            req.add_header('User-Agent', 'Roblox/Win32')
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, data=json.dumps({'userIds': [int(uid)]}).encode(), timeout=10) as r:
                pdata = json.loads(r.read().decode())
                if pdata.get('userPresences'):
                    p = pdata['userPresences'][0]
                    profile['last_online'] = p.get('lastOnline', '')
                    profile['presence_type'] = p.get('userPresenceType', 0)
        except:
            pass
    return jsonify({'profile': profile})

@accounts_bp.route('/api/accounts/<acc_id>/auto-join', methods=['POST'])
def toggle_auto_join(acc_id):
    data = request.json
    enabled = data.get('auto_join')
    server_id = data.get('server_id')
    with _data_lock:
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return jsonify({'error': 'Not found'}), 404
        if enabled is not None:
            acc['auto_join'] = enabled
            log_activity(f'Auto-Join {"ON" if enabled else "OFF"} untuk "{acc["name"]}"')
        if server_id:
            acc['server_id'] = server_id
    save_data()
    return jsonify({'auto_join': acc.get('auto_join', False), 'server_id': acc.get('server_id', '')})

@accounts_bp.route('/api/accounts/<acc_id>/move-vm', methods=['POST'])
def move_account_vm(acc_id):
    instance = request.json.get('mumu_instance')
    serials = settings.get('mumu_serials', [])
    max_idx = len(serials) - 1 if serials else 0
    if instance is None or not isinstance(instance, int) or instance < 0 or instance > max_idx:
        return jsonify({'error': f'Invalid mumu_instance (0-{max_idx})'}), 400
    for acc in accounts:
        if acc['id'] == acc_id:
            with _data_lock:
                acc['mumu_instance'] = instance
                log_activity(f'[{acc["name"]}] Pindah ke VM {instance}')
            save_data()
            return jsonify({'mumu_instance': instance})
    return jsonify({'error': 'Not found'}), 404

@accounts_bp.route('/api/accounts/<acc_id>/inject', methods=['POST'])
def inject_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    cookie = decrypt_cookie(acc.get('cookie', ''))
    if not cookie:
        return jsonify({'success': False, 'error': 'No cookie'})
    instance = acc.get('mumu_instance', 0)
    package = acc.get('package_name', '') or 'com.roblox.client'
    serial = get_serial(instance)
    if not serial:
        return jsonify({'success': False, 'error': f'Instance {instance}: serial kosong'})

    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'success': False, 'error': msg})

    methods_tried = []
    adb = find_adb()
    try:
        subprocess.run([adb, '-s', serial, 'shell', 'pm', 'clear', package], capture_output=True, timeout=15)
        methods_tried.append('pm clear')
        time.sleep(2)

        auth_xml = f'<?xml version="1.0" encoding="utf-8"?><map><string name="ROBLOSECURITY">{cookie}</string></map>'
        injected = False
        written_path = None

        root_paths = [
            f'/data/data/{package}/shared_prefs/roblox.xml',
            f'/data/data/{package}/shared_prefs/AuthInfo.xml'
        ]

        for path in root_paths:
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
                    f.write(auth_xml)
                    tmp = f.name
                subprocess.run([adb, '-s', serial, 'push', tmp, path], capture_output=True, timeout=10)
                os.unlink(tmp)
                tmp = None
                r = subprocess.run([adb, '-s', serial, 'shell', 'chmod', '600', path], capture_output=True, timeout=5)
                if r.returncode == 0:
                    injected = True
                    written_path = path
                    methods_tried.append(f'push {path}')
                    break
            except:
                if tmp:
                    try: os.unlink(tmp)
                    except: pass
                continue

        if not injected:
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
                    f.write(auth_xml)
                    tmp = f.name
                subprocess.run([adb, '-s', serial, 'push', tmp, '/data/local/tmp/roblox.xml'], capture_output=True, timeout=10)
                r = subprocess.run([adb, '-s', serial, 'shell', 'su', '-c',
                    f'cp /data/local/tmp/roblox.xml /data/data/{package}/shared_prefs/roblox.xml && chmod 600 /data/data/{package}/shared_prefs/roblox.xml'],
                    capture_output=True, timeout=10)
                os.unlink(tmp)
                tmp = None
                if r.returncode == 0:
                    injected = True
                    written_path = f'/data/data/{package}/shared_prefs/roblox.xml'
                    methods_tried.append('su')
            except:
                if tmp:
                    try: os.unlink(tmp)
                    except: pass

        if not injected:
            try:
                subprocess.run([adb, '-s', serial, 'shell', 'am', 'start',
                    '-n', f'{package}/.AccountLogin'], capture_output=True, timeout=10)
                methods_tried.append('open login (manual)')
                log_account(acc['id'], acc['name'], f'Cookie injection requires root/debug on {serial} ({package})')
            except:
                pass
            return jsonify({'success': False, 'error': 'No root access - cannot inject cookie',
                           'methods_tried': methods_tried, 'note': 'Roblox login opened manually'})

        subprocess.run([adb, '-s', serial, 'shell', 'am', 'start',
            '-n', f'{package}/.RobloxApp'], capture_output=True, timeout=10)

        log_account(acc['id'], acc['name'], f'Cookie injected to {package} on instance {instance} ({serial})')
        return jsonify({'success': True, 'methods_tried': methods_tried})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@accounts_bp.route('/api/accounts/<acc_id>/join', methods=['POST'])
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
    with _join_threads_lock:
        if acc['id'] not in _join_threads:
            _join_threads.add(acc['id'])
            threading.Thread(target=launch_mumu, args=(acc, link, sv, acc['id']), daemon=True).start()
    return jsonify({'status': 'joining', 'link': link})

@accounts_bp.route('/api/join-all', methods=['POST'])
def join_all():
    if not servers:
        return jsonify({'error': 'No servers configured'}), 400
    sv = servers[0]
    link = build_join_link(sv)
    if not link:
        return jsonify({'error': 'Could not build join link'}), 400
    count = 0
    for acc in accounts:
        if acc.get('cookie'):
            with _data_lock:
                acc['status'] = 'joining'
                acc['active'] = True
            with _join_threads_lock:
                if acc['id'] not in _join_threads:
                    _join_threads.add(acc['id'])
                    threading.Thread(target=launch_mumu, args=(acc, link, sv, acc['id']), daemon=True).start()
                    count += 1
    save_data()
    log_activity(f'Join all: {count} accounts starting')
    return jsonify({'status': 'joining', 'count': count})

@accounts_bp.route('/api/accounts/<acc_id>/disconnect', methods=['POST'])
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

@accounts_bp.route('/api/accounts/<acc_id>/logs', methods=['GET'])
def get_account_logs(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    name = acc['name'] if acc else '?'
    logs = acc_logs.get(acc_id, [])
    return jsonify({'logs': logs, 'name': name})

@accounts_bp.route('/api/accounts/<acc_id>/push-script', methods=['POST'])
def push_script(acc_id):
    import tempfile
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    name = acc.get('name', 'Account')
    package = acc.get('package_name', '')
    url = settings.get('dashboard_url', 'http://localhost:5000')
    from blueprints.misc import make_script_for
    script = make_script_for(name, url)

    instance = acc.get('mumu_instance', 0)
    serial = get_serial(instance)
    if not serial:
        return jsonify({'error': f'No serial for instance {instance}'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500

    tmp = os.path.join(tempfile.gettempdir(), f'delta_push_{acc_id}.luau')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(script)
        if package:
            script_path = f'/data/data/{package}/files/Delta/Autoexecute/monitor.luau'
            target = package
        else:
            script_path = '/sdcard/Delta/Autoexecute/monitor.luau'
            target = 'sdcard'
        code, out = adb_cmd(['push', tmp, script_path], serial)
        if code != 0:
            return jsonify({'error': f'ADB push failed: {out}'}), 500
        if acc:
            log_account(acc_id, name, f'Script pushed to {target} OK')
        return jsonify({'success': True, 'message': f'Script pushed to {target}'})
    finally:
        try: os.remove(tmp)
        except: pass

@accounts_bp.route('/api/accounts/<acc_id>/rollback', methods=['POST'])
def rollback_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    name = acc.get('name', '?')
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
    from services.roblox import build_join_link
    sv = next((s for s in servers if acc.get('server_ids') and s['id'] in acc.get('server_ids')), None) or (servers[0] if servers else None)
    if not sv:
        return jsonify({'error': 'No server configured'}), 400
    link = build_join_link(sv)
    if not link:
        return jsonify({'error': 'Failed to build join link'}), 500
    try:
        adb_force_stop_roblox(serial)
        time.sleep(2)
        adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'", '-p', 'com.roblox.client'], serial)
        acc['status'] = 'rollback'
        log_account(acc_id, name, f'Rollback: force-stop + rejoin ke {sv["name"]}')
        log_activity(f'[{name}] Rollback executed (force-stop + rejoin)')
        save_data()
        return jsonify({'success': True, 'message': f'Rollback: force-stop + rejoin {sv["name"]}'})
    except Exception as e:
        log_activity(f'[{name}] Rollback error: {e}')
        return jsonify({'error': str(e)}), 500
