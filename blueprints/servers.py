import json, urllib.request

from flask import Blueprint, request, jsonify

from models import servers, _data_lock, log_activity, save_data

servers_bp = Blueprint('servers', __name__)

@servers_bp.route('/api/servers', methods=['GET'])
def get_servers():
    return jsonify(servers)

@servers_bp.route('/api/servers', methods=['POST'])
def add_server():
    data = request.json
    import time
    sv = {
        'id': str(int(time.time() * 1000)),
        'name': data.get('name', ''),
        'type': data.get('type', 'public'),
        'place_id': data.get('place_id', ''),
        'server_code': data.get('server_code', ''),
        'link': data.get('link', ''),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with _data_lock:
        servers.append(sv)
    save_data()
    log_activity(f'Server "{sv["name"]}" ditambahkan')
    return jsonify(sv), 201

@servers_bp.route('/api/servers/<sv_id>', methods=['PUT'])
def update_server(sv_id):
    data = request.json
    with _data_lock:
        sv = next((s for s in servers if s['id'] == sv_id), None)
        if not sv:
            return jsonify({'error': 'Server not found'}), 404
        sv['name'] = data.get('name', sv['name'])
        sv['type'] = data.get('type', sv['type'])
        sv['place_id'] = data.get('place_id', sv['place_id'])
        sv['server_code'] = data.get('server_code', sv['server_code'])
        sv['link'] = data.get('link', sv['link'])
    save_data()
    log_activity(f'Server "{sv["name"]}" diperbarui')
    return jsonify(sv)

@servers_bp.route('/api/servers/<sv_id>', methods=['DELETE'])
def delete_server(sv_id):
    with _data_lock:
        sv = next((s for s in servers if s['id'] == sv_id), None)
        servers[:] = [s for s in servers if s['id'] != sv_id]
    save_data()
    if sv:
        log_activity(f'Server "{sv["name"]}" dihapus')
    return jsonify({'success': True})

@servers_bp.route('/api/servers/<sv_id>/game-info', methods=['GET'])
def server_game_info(sv_id):
    sv = next((s for s in servers if s['id'] == sv_id), None)
    if not sv:
        return jsonify({'error': 'Not found'}), 404
    place_id = sv.get('place_id', '')
    if not place_id:
        return jsonify({'info': None})
    info = {'place_id': place_id}
    try:
        req = urllib.request.Request(f'https://thumbnails.roblox.com/v1/places/gameicons?placeIds={place_id}&size=128x128&format=png')
        req.add_header('User-Agent', 'Roblox/Win32')
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            if data.get('data'):
                info['thumbnail'] = data['data'][0].get('imageUrl', '')
    except:
        pass
    try:
        req = urllib.request.Request(f'https://apis.roblox.com/universes/v1/places/{place_id}/universe')
        req.add_header('User-Agent', 'Roblox/Win32')
        with urllib.request.urlopen(req, timeout=10) as r:
            universe_data = json.loads(r.read().decode())
            universe_id = universe_data.get('universeId')
            if universe_id:
                info['universe_id'] = universe_id
                req2 = urllib.request.Request(f'https://games.roblox.com/v1/games?universeIds={universe_id}')
                req2.add_header('User-Agent', 'Roblox/Win32')
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    game_data = json.loads(r2.read().decode())
                    if game_data.get('data'):
                        g = game_data['data'][0]
                        info['game_name'] = g.get('name', '')
                        info['player_count'] = g.get('playing', 0)
                        info['visits'] = g.get('visits', 0)
                        info['genre'] = g.get('genre', '')
    except:
        pass
    return jsonify({'info': info})

@servers_bp.route('/api/game-info', methods=['GET'])
def game_info_by_place():
    place_id = request.args.get('place_id', '')
    if not place_id:
        return jsonify({'info': None})
    info = {'place_id': place_id}
    try:
        req = urllib.request.Request(f'https://thumbnails.roblox.com/v1/places/gameicons?placeIds={place_id}&size=128x128&format=png')
        req.add_header('User-Agent', 'Roblox/Win32')
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            if data.get('data'):
                info['thumbnail'] = data['data'][0].get('imageUrl', '')
    except:
        pass
    try:
        req = urllib.request.Request(f'https://apis.roblox.com/universes/v1/places/{place_id}/universe')
        req.add_header('User-Agent', 'Roblox/Win32')
        with urllib.request.urlopen(req, timeout=10) as r:
            universe_data = json.loads(r.read().decode())
            universe_id = universe_data.get('universeId')
            if universe_id:
                info['universe_id'] = universe_id
                req2 = urllib.request.Request(f'https://games.roblox.com/v1/games?universeIds={universe_id}')
                req2.add_header('User-Agent', 'Roblox/Win32')
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    game_data = json.loads(r2.read().decode())
                    if game_data.get('data'):
                        g = game_data['data'][0]
                        info['game_name'] = g.get('name', '')
                        info['player_count'] = g.get('playing', 0)
                        info['visits'] = g.get('visits', 0)
                        info['genre'] = g.get('genre', '')
    except:
        pass
    return jsonify({'info': info})

@servers_bp.route('/api/servers/scan-from-accounts', methods=['POST'])
def scan_servers_from_accounts():
    from models import accounts
    results = []
    added = 0
    already_exist = 0
    seen_places = set()

    for acc in accounts:
        uid = acc.get('verified_id')
        cookie = acc.get('cookie', '')
        name = acc.get('name', '?')
        if not uid or not cookie:
            results.append({'account': name, 'status': 'skipped', 'message': 'Not verified or no cookie'})
            continue
        try:
            req = urllib.request.Request('https://presence.roblox.com/v1/presence/users')
            req.add_header('Cookie', f'.ROBLOSECURITY={cookie}')
            req.add_header('User-Agent', 'Roblox/Win32')
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, data=json.dumps({'userIds': [int(uid)]}).encode(), timeout=10) as r:
                pdata = json.loads(r.read().decode())
            presences = pdata.get('userPresences', [])
            if not presences:
                results.append({'account': name, 'status': 'skipped', 'message': 'No presence data'})
                continue
            p = presences[0]
            ptype = p.get('userPresenceType', 0)
            if ptype != 2:
                results.append({'account': name, 'status': 'skipped', 'message': f'Not in game (type={ptype})'})
                continue
            place_id = str(p.get('placeId', ''))
            if not place_id:
                results.append({'account': name, 'status': 'skipped', 'message': 'No placeId'})
                continue
            if place_id in seen_places:
                results.append({'account': name, 'status': 'exists', 'place_id': place_id, 'message': f'Same place ({place_id}) already scanned'})
                continue
            if any(s.get('place_id') == place_id for s in servers if isinstance(s.get('place_id'), str)):
                already_exist += 1
                seen_places.add(place_id)
                results.append({'account': name, 'status': 'exists', 'place_id': place_id, 'message': f'Already in server list'})
                continue

            game_name = place_id
            try:
                ureq = urllib.request.Request(f'https://apis.roblox.com/universes/v1/places/{place_id}/universe')
                ureq.add_header('User-Agent', 'Roblox/Win32')
                with urllib.request.urlopen(ureq, timeout=10) as ur:
                    udata = json.loads(ur.read().decode())
                    universe_id = udata.get('universeId')
                    if universe_id:
                        greq = urllib.request.Request(f'https://games.roblox.com/v1/games?universeIds={universe_id}')
                        greq.add_header('User-Agent', 'Roblox/Win32')
                        with urllib.request.urlopen(greq, timeout=10) as gr:
                            gdata = json.loads(gr.read().decode())
                            if gdata.get('data'):
                                game_name = gdata['data'][0].get('name', place_id)
            except: pass

            import time
            sv = {
                'id': str(int(time.time() * 1000000 + len(servers))),
                'name': game_name,
                'type': 'public',
                'place_id': place_id,
                'server_code': '',
                'link': '',
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            with _data_lock:
                servers.append(sv)
            save_data()
            added += 1
            seen_places.add(place_id)
            results.append({'account': name, 'status': 'added', 'place_id': place_id, 'message': f'Added "{game_name}" ({place_id})'})
            log_activity(f'Auto-scan server: "{game_name}" dari akun {name}')
        except Exception as e:
            results.append({'account': name, 'status': 'error', 'message': f'{type(e).__name__}: {str(e)[:100]}'})

    return jsonify({'success': True, 'results': results, 'added': added, 'already_exist': already_exist})
