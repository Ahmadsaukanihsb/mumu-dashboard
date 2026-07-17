import json, urllib.request, urllib.error

def verify_cookie(cookie):
    try:
        req = urllib.request.Request('https://users.roblox.com/v1/users/authenticated')
        req.add_header('Cookie', f'.ROBLOSECURITY={cookie}')
        req.add_header('User-Agent', 'Roblox/Win32')
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            uid = data.get('id')
            name = data.get('name', '')
            robux = 0
            avatar = ''
            if uid:
                try:
                    req2 = urllib.request.Request(f'https://economy.roblox.com/v1/users/{uid}/currency')
                    req2.add_header('Cookie', f'.ROBLOSECURITY={cookie}')
                    req2.add_header('User-Agent', 'Roblox/Win32')
                    with urllib.request.urlopen(req2, timeout=10) as r2:
                        robux = json.loads(r2.read().decode()).get('robux', 0)
                except:
                    pass
                try:
                    req3 = urllib.request.Request(f'https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={uid}&size=48x48&format=png')
                    req3.add_header('User-Agent', 'Roblox/Win32')
                    with urllib.request.urlopen(req3, timeout=10) as r3:
                        thumb_data = json.loads(r3.read().decode())
                        if thumb_data.get('data'):
                            avatar = thumb_data['data'][0].get('imageUrl', '')
                except:
                    pass
            return {'valid': True, 'username': name, 'robux': robux, 'avatar': avatar, 'id': uid}
    except urllib.error.HTTPError as e:
        return {'valid': False, 'error': f'HTTP {e.code}'}
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def build_join_link(sv):
    base = sv.get('place_id', '')
    if not base:
        return None
    if sv.get('type') == 'private':
        code = sv.get('server_code', '')
        if code:
            return f'roblox://placeId={base}&privateServerLinkCode={code}'
    return f'roblox://placeId={base}'

def _adb_extract_cookie(serial):
    from services.adb import find_adb
    adb = find_adb()
    if not adb: return None
    try:
        import subprocess
        subprocess.run([adb, '-s', serial, 'root'], capture_output=True, text=True, timeout=10)
        r = subprocess.run([
            adb, '-s', serial, 'shell',
            'sqlite3', '/data/data/com.roblox.client/app_webview/Default/Cookies',
            '"SELECT value FROM cookies WHERE name=\'.ROBLOSECURITY\';"'
        ], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            out = (r.stdout or '').strip()
            if out.startswith('_|') and len(out) > 20:
                return out
    except: pass
    return None
