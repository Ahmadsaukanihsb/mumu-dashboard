import os, json, time, urllib.request

from flask import Blueprint, render_template, request, jsonify

from models import accounts, servers, settings, acc_logs, monitor_state, _data_lock, log_activity, log_account, save_data, encrypt_cookie, decrypt_cookie, get_package_name
from services.adb import find_adb, get_serial, adb_connect, auto_push_script_to_vm
from services.roblox import verify_cookie, _adb_extract_cookie
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

@accounts_bp.route('/api/accounts/batch-delete', methods=['POST'])
def batch_delete_accounts():
    data = request.json or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    deleted = []
    with _data_lock:
        for acc_id in ids:
            acc = next((a for a in accounts if a['id'] == acc_id), None)
            if acc:
                deleted.append(acc.get('name', acc_id))
                accounts[:] = [a for a in accounts if a['id'] != acc_id]
                monitor_state.pop(acc_id, None)
                acc_logs.pop(acc_id, None)
    save_data()
    if deleted:
        log_activity(f'Batch delete: {len(deleted)} accounts dihapus')
    return jsonify({'success': True, 'deleted': deleted, 'count': len(deleted)})

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

@accounts_bp.route('/api/accounts/<acc_id>/logs', methods=['GET'])
def get_account_logs(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    name = acc['name'] if acc else '?'
    logs = acc_logs.get(acc_id, [])
    return jsonify({'logs': logs, 'name': name})
