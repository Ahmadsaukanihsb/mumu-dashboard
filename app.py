import os
import json
import time
import threading
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import tempfile
import re
from flask import Flask, render_template, request, jsonify, Response, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dash-roblox-secret-change-me')
CORS(app)

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')

accounts = []
servers = []
settings = {
    'auto_join_enabled': True,
    'rejoin_delay': 3,
    'max_retries': 5,
    'monitor_interval': 2,
    'rejoin_interval': 2400,
    'theme': 'dark',
    'adb_path': '',
    'mumu_serials': ['', '', '', '', ''],
    'webhook_url': '',
    'webhook_enabled': False,
}
activity_log = []
acc_logs = {}
monitor_running = False
monitor_thread = None
user_shutdown_instances = set()

def send_webhook(title, description, color=0xff4444, avatar_url=None):
    url = settings.get('webhook_url', '')
    if not url or not settings.get('webhook_enabled'):
        return
    try:
        import urllib.request
        embed = {
            'title': title,
            'description': description,
            'color': color,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()),
            'footer': {'text': 'Dashboard Roblox'}
        }
        if avatar_url:
            embed['thumbnail'] = {'url': avatar_url}
        data = json.dumps({'embeds': [embed]}).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'DashboardRoblox/1.0'})
        urllib.request.urlopen(req, timeout=5)
    except:
        pass

def adb_check_roblox(serial):
    adb = find_adb()
    if not adb: return False
    try:
        r = subprocess.run([adb, '-s', serial, 'shell', 'pidof', 'com.roblox.client'],
            capture_output=True, text=True, timeout=10)
        pid = r.stdout.strip()
        return bool(pid and pid.isdigit())
    except:
        return False

def adb_get_thread_count(serial):
    adb = find_adb()
    if not adb: return None
    try:
        r = subprocess.run([adb, '-s', serial, 'shell', 'pidof', 'com.roblox.client'],
            capture_output=True, text=True, timeout=10)
        pid_str = r.stdout.strip()
        if not pid_str:
            return None
        pid = pid_str.split()[0]
        if not pid.isdigit():
            return None
        r = subprocess.run([adb, '-s', serial, 'shell', 'cat', f'/proc/{pid}/status'],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.split('\n'):
            if 'Threads' in line:
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1])
        return None
    except:
        return None

def adb_force_stop_roblox(serial):
    adb = find_adb()
    if not adb: return
    try:
        subprocess.run([adb, '-s', serial, 'shell', 'am', 'force-stop', 'com.roblox.client'],
            capture_output=True, timeout=10)
    except:
        pass

def adb_dismiss_dialogs(serial):
    adb = find_adb()
    if not adb: return
    try:
        for _ in range(3):
            subprocess.run([adb, '-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_BACK'],
                capture_output=True, timeout=5)
            time.sleep(0.3)
        for xy in [('540', '960'), ('540', '1100'), ('540', '800'), ('360', '1020'), ('720', '1020')]:
            subprocess.run([adb, '-s', serial, 'shell', 'input', 'tap', xy[0], xy[1]],
                capture_output=True, timeout=5)
            time.sleep(0.2)
    except:
        pass

def adb_detect_kicked_dialog(serial):
    adb = find_adb()
    if not adb: return False

    pid = None
    try:
        r = subprocess.run([adb, '-s', serial, 'shell', 'pidof', 'com.roblox.client'],
            capture_output=True, text=True, timeout=5)
        pid = r.stdout.strip()
    except:
        pass
    if not pid:
        return False

    # Method 1: dumpsys — check floating layer windows from Roblox
    try:
        r = subprocess.run([adb, '-s', serial, 'shell', 'dumpsys', 'window', 'windows'],
            capture_output=True, text=True, timeout=10)
        out = r.stdout.lower()
        if 'com.roblox.client' not in out:
            return False
        for line in out.split('\n'):
            if 'mIsFloatingLayer=true' in line and 'com.roblox.client' in line:
                return True
    except:
        pass

    # Method 2: uiautomator dump (--compressed, /data/local/tmp/ — no storage permission needed)
    try:
        subprocess.run([adb, '-s', serial, 'shell', 'uiautomator', 'dump', '--compressed', '/data/local/tmp/ui.xml'],
            capture_output=True, timeout=20)
        r = subprocess.run([adb, '-s', serial, 'shell', 'cat', '/data/local/tmp/ui.xml 2>/dev/null || echo empty'],
            capture_output=True, text=True, timeout=10)
        subprocess.run([adb, '-s', serial, 'shell', 'rm', '-f', '/data/local/tmp/ui.xml'], capture_output=True, timeout=5)
        text = r.stdout.lower()
        kick_words = ['kicked', 'you were kicked', 'you have been kicked', 'removed from the game',
                      'your save data', 'disconnected', 'please rejoin', 'connection lost']
        if any(k in text for k in kick_words):
            return True
    except:
        pass

    # Method 3: proactive dismiss — tap common dialog areas as safety net
    # (always runs to dismiss any stray dialogs; detection is only from methods 1 & 2)
    try:
        for _ in range(3):
            subprocess.run([adb, '-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_BACK'],
                capture_output=True, timeout=3)
            time.sleep(0.3)
        tap_points = [(540, 960), (540, 500), (540, 1400), (100, 100), (1000, 100)]
        for x, y in tap_points:
            subprocess.run([adb, '-s', serial, 'shell', 'input', 'tap', str(x), str(y)],
                capture_output=True, timeout=3)
            time.sleep(0.2)
    except:
        pass

    return False

def adb_screenshot(serial):
    adb = find_adb()
    if not adb: return None
    try:
        r = subprocess.run([adb, '-s', serial.strip(), 'exec-out', 'screencap', '-p'],
            capture_output=True, timeout=15)
        if r.returncode == 0 and len(r.stdout) > 100:
            return r.stdout
    except:
        pass
    return None

def adb_check_in_game(serial):
    adb = find_adb()
    if not adb: return None
    try:
        r = subprocess.run(
            [adb, '-s', serial, 'shell', 'dumpsys', 'window', 'windows'],
            capture_output=True, text=True, timeout=10
        )
        out = r.stdout
        if 'com.roblox.client' not in out:
            return None
        # Check mCurrentFocus / mFocusedApp
        focus_line = ''
        for line in out.split('\n'):
            if 'mCurrentFocus' in line or 'mFocusedApp' in line:
                focus_line = line.lower()
                break
        if focus_line:
            if 'mainactivity' in focus_line:
                return False
            if 'com.roblox.client' in focus_line:
                # Check if it's a dialog-like activity (not the actual game)
                if any(x in focus_line for x in ['dialog', 'alert', 'popup', 'notification']):
                    return False
                return True
        # Fallback: check if any Roblox window is visible
        has_window = False
        for line in out.split('\n'):
            if 'com.roblox.client' in line and ('window' in line.lower() or 'activity' in line.lower()):
                if 'mIsFloatingLayer=true' in line:
                    return False  # dialog on top = not in-game
                has_window = True
        return True if has_window else None
    except:
        return None

def send_join_intent(acc, serial):
    sv = next((s for s in servers if s['id'] == acc.get('server_id')), None)
    if not sv and servers:
        sv = servers[0]
    if not sv:
        return False
    link = build_join_link(sv)
    if not link:
        return False
    adb_force_stop_roblox(serial)
    time.sleep(3)
    code, _ = adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'", '-p', 'com.roblox.client'], serial)
    time.sleep(20)
    adb_dismiss_dialogs(serial)
    time.sleep(2)
    adb_dismiss_dialogs(serial)
    if code == 0:
        now = time.time()
        acc['last_join_time'] = now
        acc['status'] = 'connected'
        acc['last_joined'] = time.strftime('%H:%M:%S')
        save_data()
        return True
    return False

monitor_state = {}
JOIN_COOLDOWN = 120

def should_join(st):
    return time.time() - st.get('last_intent', 0) >= JOIN_COOLDOWN

def monitor_loop():
    global monitor_running
    while monitor_running:
        try:
            interval = settings.get('monitor_interval', 5)
            rejoin_interval = settings.get('rejoin_interval', 2400)
            now = time.time()
            for acc in accounts:
                if not acc.get('auto_join') or not acc.get('cookie'):
                    continue
                acc_id = acc.get('id', '')
                instance = acc.get('mumu_instance', 0)
                serial = get_serial(instance)
                if not serial:
                    continue
                ok, msg = adb_connect(serial)
                if not ok:
                    if settings.get('auto_restart_vm', True) and instance not in user_shutdown_instances:
                        ensure_vm_running(serial, instance)
                    continue
                user_shutdown_instances.discard(instance)
                running = adb_check_roblox(serial)
                was_active = acc.get('status') in ('connected', 'monitoring', 'active')

                if running and not was_active:
                    acc['status'] = 'monitoring'
                    acc['active'] = True
                    save_data()
                    st = monitor_state.setdefault(acc_id, {})
                    st['last_intent'] = time.time()
                    st['in_game'] = False
                    st['tc_history'] = []

                if not running and was_active:
                    acc['status'] = 'disconnected'
                    acc['active'] = False
                    save_data()
                    st = monitor_state.setdefault(acc_id, {})
                    st['last_intent'] = time.time()
                    st['in_game'] = False
                    log_account(acc_id, acc['name'], 'Roblox exited, rejoining...')
                    send_webhook(
                        f'🔄 {acc["name"]} — Roblox Closed',
                        f'Auto-rejoin aktif\n**Instance:** MuMu-{acc.get("mumu_instance", "?")}',
                        0x3498db,
                        acc.get('verified_avatar')
                    )
                    sv = next((s for s in servers if s['id'] == acc.get('server_id')), None)
                    if not sv and servers:
                        sv = servers[0]
                    if sv:
                        link = build_join_link(sv)
                        if link:
                            threading.Thread(target=launch_mumu, args=(acc, link, sv), daemon=True).start()
                    continue

                if running and was_active:
                    st = monitor_state.setdefault(acc_id, {})
                    was_in_game = st.get('in_game', True)
                    tc = adb_get_thread_count(serial)

                    if tc is not None:
                        st['last_tc'] = tc
                        in_game = tc >= 80
                        history = st.setdefault('tc_history', [])
                        history.append(tc)
                        if len(history) > 10:
                            history.pop(0)
                        game_start = st.get('in_game_since', 0)
                        if in_game and game_start == 0:
                            st['in_game_since'] = now
                        elif not in_game:
                            st['in_game_since'] = 0

                        # Periodic dialog dismiss safety net every 30s
                        if (now - st.get('last_dismiss_check', 0)) >= 30:
                            st['last_dismiss_check'] = now
                            adb_dismiss_dialogs(serial)

                        last_act = st.get('last_activity_check', 0)
                        if in_game and (now - last_act) >= 15:
                            st['last_activity_check'] = now
                            if adb_check_in_game(serial) is False:
                                log_account(acc_id, acc['name'], 'activity check: not in game, rejoining...')
                                in_game = False

                        if (now - st.get('last_kicked_check', 0)) >= 15:
                            st['last_kicked_check'] = now
                            if adb_detect_kicked_dialog(serial):
                                log_account(acc_id, acc['name'], 'kicked dialog detected, dismissing & rejoining')
                                send_webhook(f'⚠️ {acc["name"]} — Kicked Dialog', 'Kicked dialog detected via UI dump', 0xffaa00, acc.get('verified_avatar'))
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()
                                st['in_game'] = False
                                st['in_game_since'] = 0
                                continue

                        # Stuck detection: thread count stuck in 80-130 for 3+ minutes
                        stuck_threshold = 180
                        if in_game and game_start > 0 and (now - game_start) >= stuck_threshold:
                            if len(history) >= 5:
                                avg_tc = sum(history[-5:]) / len(history[-5:])
                                if 80 <= avg_tc <= 130:
                                    log_account(acc_id, acc['name'], f'stuck/kick detected (avg tc={avg_tc:.0f}, {stuck_threshold}s), rejoining...')
                                    adb_force_stop_roblox(serial)
                                    send_join_intent(acc, serial)
                                    st['last_intent'] = time.time()
                                    st['in_game'] = False
                                    st['in_game_since'] = 0
                                    continue

                        if in_game:
                            if not was_in_game and not st.get('in_game_notified', False):
                                st['in_game_notified'] = True
                                log_account(acc_id, acc['name'], 'in-game detected')
                                send_webhook(f'✅ {acc["name"]} — In Game', 'Account berhasil masuk ke game', 0x43e97b, acc.get('verified_avatar'))
                            st['in_game'] = True
                        elif was_in_game:
                            st['in_game_notified'] = False
                            if should_join(st):
                                log_account(acc_id, acc['name'], f'home screen (threads={tc}), rejoining...')
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()
                            st['in_game'] = False
                        else:
                            last_rejoin = st.get('last_intent', 0)
                            if now - last_rejoin >= 120:
                                log_account(acc_id, acc['name'], f'still home (threads={tc}), rejoining...')
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()


                    else:
                        last_rejoin = st.get('last_intent', 0)
                        if was_active and (now - last_rejoin) >= 600:
                            log_account(acc_id, acc['name'], 'fallback rejoin (threads unknown for 10min)')
                            send_join_intent(acc, serial)
                            st['last_intent'] = time.time()
                        elif not was_active and (now - last_rejoin) >= 120:
                            log_account(acc_id, acc['name'], 'fallback rejoin (threads unknown)')
                            send_join_intent(acc, serial)
                            st['last_intent'] = time.time()

                last_join = acc.get('last_join_time', 0)
                if running and rejoin_interval > 0 and (now - last_join) >= rejoin_interval:
                    log_account(acc_id, acc['name'], f'rejoin periodik ({int(rejoin_interval//60)} menit)')
                    send_join_intent(acc, serial)
                    st['last_intent'] = time.time()
                    st['in_game_since'] = 0

            time.sleep(interval)
        except:
            time.sleep(5)

def start_monitor():
    global monitor_running, monitor_thread
    if monitor_running:
        return
    monitor_running = True
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

def stop_monitor():
    global monitor_running
    monitor_running = False

def load_data():
    global accounts, servers, settings
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                accounts = data.get('accounts', [])
                for acc in accounts:
                    if not acc.get('server_ids') and acc.get('server_id'):
                        acc['server_ids'] = [acc['server_id']]
                servers = data.get('servers', [])
                settings.update(data.get('settings', {}))
                ri = settings.get('rejoin_interval', 2400)
                if ri < 60:
                    settings['rejoin_interval'] = ri * 60
                saved_logs = data.get('account_logs', {})
                if saved_logs:
                    acc_logs.update(saved_logs)
                if not accounts and not servers and os.path.exists(DATA_FILE + '.bak'):
                    print('[WARN] data.json kosong tapi data.json.bak ditemukan!')
                    print('[WARN] Buka Settings > Restore from Backup untuk mengembalikan.')
        except Exception:
            pass

def save_data():
    if os.path.exists(DATA_FILE) and accounts:
        import shutil
        shutil.copy2(DATA_FILE, DATA_FILE + '.bak')
    with open(DATA_FILE, 'w') as f:
        json.dump({
            'accounts': accounts,
            'servers': servers,
            'settings': settings,
            'account_logs': {k: v[:100] for k, v in acc_logs.items()}
        }, f, indent=2)

def log_activity(msg, level='info'):
    entry = {
        'time': time.strftime('%H:%M:%S'),
        'msg': msg,
        'level': level
    }
    activity_log.insert(0, entry)
    if len(activity_log) > 200:
        activity_log.pop()
    return entry

def log_account(acc_id, name, msg, level='info'):
    entry = {
        'time': time.strftime('%H:%M:%S'),
        'msg': msg,
        'level': level
    }
    acc_logs.setdefault(acc_id, []).insert(0, entry)
    if len(acc_logs[acc_id]) > 200:
        acc_logs[acc_id].pop()
    return entry

def find_adb():
    if settings.get('adb_path') and os.path.isfile(settings['adb_path']):
        return settings['adb_path']
    candidates = [
        os.path.expandvars(r'%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe'),
        r'C:\Program Files\MuMu\emulator\MuMuPlayer\shell\adb.exe',
        r'C:\Program Files\MuMu\emulator\MuMuPlayerGlobal\shell\adb.exe',
        r'C:\Program Files\Nox\bin\adb.exe',
        r'C:\Program Files (x86)\Nox\bin\adb.exe',
        'adb.exe',
    ]
    for c in candidates:
        try:
            r = subprocess.run([c, '--version'], capture_output=True, timeout=5)
            if r.returncode == 0:
                settings['adb_path'] = c
                save_data()
                return c
        except Exception:
            pass
    return None

def get_serial(instance_idx=0):
    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    if instance_idx < 0 or instance_idx >= len(serials):
        instance_idx = 0
    s = serials[instance_idx]
    if not s or not s.strip():
        return None
    return s.strip()

def adb_cmd(args, serial=None):
    adb = find_adb()
    if not adb:
        return None, 'ADB not found'
    if serial:
        full_cmd = [adb, '-s', serial] + args
    else:
        full_cmd = [adb] + args
    try:
        r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip() or r.stderr.strip()
    except subprocess.TimeoutExpired:
        return None, 'ADB command timed out'
    except Exception as e:
        return None, str(e)

def adb_connect(serial):
    adb = find_adb()
    if not adb:
        return False, 'ADB not found'
    try:
        r = subprocess.run([adb, 'connect', serial], capture_output=True, text=True, timeout=10)
        ok = 'connected' in r.stdout.lower() or 'already connected' in r.stdout.lower()
        return ok, r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        return False, str(e)

load_data()

AUTH_PASSWORD_KEY = 'dashboard_password'
PUBLIC_ROUTES = {'/login', '/api/login', '/api/auth-status', '/static/style.css', '/static/script.js'}

@app.before_request
def check_auth():
    password = settings.get(AUTH_PASSWORD_KEY, '')
    if not password:
        return
    if request.path in PUBLIC_ROUTES or request.path.startswith('/static/'):
        return
    if not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return render_template('login.html')

@app.route('/login', methods=['GET'])
def login_page():
    if session.get('authenticated'):
        return render_template('index.html')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    pwd = settings.get(AUTH_PASSWORD_KEY, '')
    if not pwd:
        session['authenticated'] = True
        return jsonify({'success': True})
    if data.get('password') == pwd:
        session['authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'error': 'Wrong password'}), 403

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('authenticated', None)
    return jsonify({'success': True})

@app.route('/api/auth-status', methods=['GET'])
def api_auth_status():
    password = settings.get(AUTH_PASSWORD_KEY, '')
    return jsonify({
        'authenticated': session.get('authenticated', False),
        'has_password': bool(password)
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/summary', methods=['GET'])
def get_summary():
    total = len(accounts)
    online = sum(1 for a in accounts if a.get('status') in ('connected', 'monitoring', 'active'))
    error = sum(1 for a in accounts if a.get('status') == 'error')
    idle = total - online - error
    verified = sum(1 for a in accounts if a.get('verified_username'))
    total_robux = sum(a.get('verified_robux', 0) or 0 for a in accounts)
    running_vms = 0
    try:
        code, out = mumu_vm_cmd(['list', 'runningvms'])
        if code == 0:
            running_vms = len([l for l in out.split('\n') if l.strip()])
    except:
        pass
    return jsonify({
        'total_accounts': total,
        'online': online,
        'error': error,
        'idle': idle,
        'verified': verified,
        'total_robux': total_robux,
        'running_vms': running_vms,
        'total_vms': 5
    })

@app.route('/api/accounts', methods=['GET'])
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
            a['next_rejoin_in'] = None
        # show default rejoin interval for quick preview
        if a['next_rejoin_in'] is None:
            a['next_rejoin_in'] = int(ri)
        result.append(a)
    return jsonify(result)

@app.route('/api/accounts', methods=['POST'])
def add_account():
    data = request.json
    server_id = data.get('server_id', '')
    server_ids = data.get('server_ids', [])
    if not server_ids and server_id:
        server_ids = [server_id]
    acc = {
        'id': str(int(time.time() * 1000)),
        'name': data.get('name', ''),
        'cookie': data.get('cookie', ''),
        'active': False,
        'status': 'idle',
        'last_joined': None,
        'server_id': server_id,
        'server_ids': server_ids,
        'mumu_instance': data.get('mumu_instance', 0),
        'auto_join': data.get('auto_join', False),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    accounts.append(acc)
    save_data()
    log_activity(f'Account "{acc["name"]}" ditambahkan')
    return jsonify(acc), 201

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

@app.route('/api/accounts/verify-all', methods=['POST'])
def verify_all_accounts():
    results = []
    for acc in accounts:
        cookie = acc.get('cookie', '')
        if not cookie:
            results.append({'id': acc['id'], 'name': acc['name'], 'valid': False, 'error': 'No cookie'})
            continue
        result = verify_cookie(cookie)
        if result['valid']:
            acc['verified_username'] = result['username']
            acc['verified_robux'] = result['robux']
            acc['verified_avatar'] = result['avatar']
            results.append({'id': acc['id'], 'name': acc['name'], 'valid': True, 'username': result['username'], 'robux': result['robux']})
        else:
            results.append({'id': acc['id'], 'name': acc['name'], 'valid': False, 'error': result.get('error', 'unknown')})
    save_data()
    return jsonify({'results': results})

@app.route('/api/accounts/<acc_id>/auto-join', methods=['POST'])
def toggle_auto_join(acc_id):
    data = request.json
    enabled = data.get('auto_join')
    server_id = data.get('server_id')
    for acc in accounts:
        if acc['id'] == acc_id:
            if enabled is not None:
                acc['auto_join'] = enabled
                log_activity(f'Auto-Join {"ON" if enabled else "OFF"} untuk "{acc["name"]}"')
            if server_id:
                acc['server_id'] = server_id
                log_activity(f'[{acc["name"]}] Auto-join target: {next((s["name"] for s in servers if s["id"]==server_id), server_id)}')
            save_data()
            return jsonify({'auto_join': acc.get('auto_join', False), 'server_id': acc.get('server_id', '')})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/accounts/<acc_id>', methods=['PUT'])
def update_account(acc_id):
    data = request.json
    for acc in accounts:
        if acc['id'] == acc_id:
            acc['name'] = data.get('name', acc['name'])
            acc['cookie'] = data.get('cookie', acc['cookie'])
            acc['server_id'] = data.get('server_id', acc['server_id'])
            acc['server_ids'] = data.get('server_ids', acc.get('server_ids', []))
            if not acc['server_ids'] and acc['server_id']:
                acc['server_ids'] = [acc['server_id']]
            acc['mumu_instance'] = data.get('mumu_instance', acc.get('mumu_instance', 0))
            aj = data.get('auto_join')
            if aj is not None:
                acc['auto_join'] = aj
            if data.get('auto_join_server_id'):
                acc['server_id'] = data['auto_join_server_id']
                log_activity(f'[{acc["name"]}] Auto-join server diubah')
            save_data()
            log_activity(f'Account "{acc["name"]}" diperbarui')
            return jsonify(acc)
    return jsonify({'error': 'Account not found'}), 404

@app.route('/api/accounts/<acc_id>', methods=['DELETE'])
def delete_account(acc_id):
    global accounts
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    accounts = [a for a in accounts if a['id'] != acc_id]
    save_data()
    if acc:
        log_activity(f'Account "{acc["name"]}" dihapus')
    return jsonify({'success': True})

@app.route('/api/servers', methods=['GET'])
def get_servers():
    return jsonify(servers)

@app.route('/api/servers', methods=['POST'])
def add_server():
    data = request.json
    sv = {
        'id': str(int(time.time() * 1000)),
        'name': data.get('name', ''),
        'type': data.get('type', 'public'),
        'place_id': data.get('place_id', ''),
        'server_code': data.get('server_code', ''),
        'link': data.get('link', ''),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    servers.append(sv)
    save_data()
    log_activity(f'Server "{sv["name"]}" ditambahkan')
    return jsonify(sv), 201

@app.route('/api/servers/<sv_id>', methods=['PUT'])
def update_server(sv_id):
    data = request.json
    for sv in servers:
        if sv['id'] == sv_id:
            sv['name'] = data.get('name', sv['name'])
            sv['type'] = data.get('type', sv['type'])
            sv['place_id'] = data.get('place_id', sv['place_id'])
            sv['server_code'] = data.get('server_code', sv['server_code'])
            sv['link'] = data.get('link', sv['link'])
            save_data()
            log_activity(f'Server "{sv["name"]}" diperbarui')
            return jsonify(sv)
    return jsonify({'error': 'Server not found'}), 404

@app.route('/api/servers/<sv_id>', methods=['DELETE'])
def delete_server(sv_id):
    global servers
    sv = next((s for s in servers if s['id'] == sv_id), None)
    servers = [s for s in servers if s['id'] != sv_id]
    save_data()
    if sv:
        log_activity(f'Server "{sv["name"]}" dihapus')
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    s = dict(settings)
    s.pop('dashboard_password', None)
    s['_has_password'] = bool(settings.get('dashboard_password', ''))
    s['_adb_found'] = find_adb() is not None
    s['vm_display_names'] = load_vm_display_names()
    return jsonify(s)

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    data = request.json
    keys = ['auto_join_enabled', 'rejoin_delay', 'max_retries',
            'monitor_interval', 'rejoin_interval', 'theme', 'adb_path', 'mumu_serials',
            'webhook_url', 'webhook_enabled', 'auto_restart_vm', 'dashboard_password']
    for k in keys:
        if k in data:
            settings[k] = data[k]
    save_data()
    if settings.get(AUTH_PASSWORD_KEY):
        session['authenticated'] = True
    log_activity('Pengaturan diperbarui')
    return jsonify(settings)

BACKUP_FILE = DATA_FILE + '.bak'

@app.route('/api/restore-data', methods=['POST'])
def restore_data():
    global accounts, servers
    bak = BACKUP_FILE
    if not os.path.exists(bak):
        return jsonify({'error': 'No backup file found'}), 404
    try:
        with open(bak, 'r') as f:
            data = json.load(f)
        bak_accounts = data.get('accounts', [])
        bak_servers = data.get('servers', [])
        if not bak_accounts and not bak_servers:
            return jsonify({'error': 'Backup file is also empty'}), 400
        accounts = bak_accounts
        servers = bak_servers
        for acc in accounts:
            if not acc.get('server_ids') and acc.get('server_id'):
                acc['server_ids'] = [acc['server_id']]
        save_data()
        log_activity(f'Data restored from backup ({len(accounts)} accounts, {len(servers)} servers)')
        return jsonify({'success': True, 'accounts': len(accounts), 'servers': len(servers)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/activity', methods=['GET'])
def get_activity():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(activity_log[:limit])

@app.route('/api/accounts/<acc_id>/verify', methods=['POST'])
def verify_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    cookie = acc.get('cookie', '')
    if not cookie:
        return jsonify({'valid': False, 'error': 'No cookie'})
    result = verify_cookie(cookie)
    if result['valid']:
        acc['verified_username'] = result['username']
        acc['verified_robux'] = result['robux']
        acc['verified_avatar'] = result['avatar']
        save_data()
        return jsonify(result)
    return jsonify({'valid': False, 'error': result.get('error', 'Unknown')})

@app.route('/api/accounts/<acc_id>/inject', methods=['POST'])
def inject_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    cookie = acc.get('cookie', '')
    if not cookie:
        return jsonify({'success': False, 'error': 'No cookie'})
    instance = acc.get('mumu_instance', 0)
    serial = get_serial(instance)
    if not serial:
        return jsonify({'success': False, 'error': f'Instance {instance}: serial kosong'})

    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'success': False, 'error': msg})

    methods_tried = []
    adb = find_adb()
    try:
        subprocess.run([adb, '-s', serial, 'shell', 'pm', 'clear', 'com.roblox.client'], capture_output=True, timeout=15)
        methods_tried.append('pm clear')
        time.sleep(2)

        auth_xml = f'<?xml version="1.0" encoding="utf-8"?><map><string name="ROBLOSECURITY">{cookie}</string></map>'
        injected = False
        written_path = None

        root_paths = [
            '/data/data/com.roblox.client/shared_prefs/roblox.xml',
            '/data/data/com.roblox.client/shared_prefs/AuthInfo.xml'
        ]

        for path in root_paths:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
                    f.write(auth_xml)
                    tmp = f.name
                subprocess.run([adb, '-s', serial, 'push', tmp, path], capture_output=True, timeout=10)
                os.unlink(tmp)
                r = subprocess.run([adb, '-s', serial, 'shell', 'chmod', '600', path], capture_output=True, timeout=5)
                if r.returncode == 0:
                    injected = True
                    written_path = path
                    methods_tried.append(f'push {path}')
                    break
            except:
                try: os.unlink(tmp)
                except: pass
                continue

        if not injected:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
                    f.write(auth_xml)
                    tmp = f.name
                subprocess.run([adb, '-s', serial, 'push', tmp, '/data/local/tmp/roblox.xml'], capture_output=True, timeout=10)
                r = subprocess.run([adb, '-s', serial, 'shell', 'su', '-c',
                    'cp /data/local/tmp/roblox.xml /data/data/com.roblox.client/shared_prefs/roblox.xml && chmod 600 /data/data/com.roblox.client/shared_prefs/roblox.xml'],
                    capture_output=True, timeout=10)
                os.unlink(tmp)
                if r.returncode == 0:
                    injected = True
                    written_path = '/data/data/com.roblox.client/shared_prefs/roblox.xml'
                    methods_tried.append('su')
            except:
                try: os.unlink(tmp)
                except: pass

        if not injected:
            try:
                subprocess.run([adb, '-s', serial, 'shell', 'am', 'start',
                    '-n', 'com.roblox.client/.AccountLogin'], capture_output=True, timeout=10)
                methods_tried.append('open login (manual)')
                log_account(acc['id'], acc['name'], f'Cookie injection requires root/debug on {serial}')
            except:
                pass
            return jsonify({'success': False, 'error': 'No root access - cannot inject cookie',
                           'methods_tried': methods_tried, 'note': 'Roblox login opened manually'})

        subprocess.run([adb, '-s', serial, 'shell', 'am', 'start',
            '-n', 'com.roblox.client/.RobloxApp'], capture_output=True, timeout=10)

        log_account(acc['id'], acc['name'], f'Cookie injected to instance {instance} ({serial})')
        return jsonify({'success': True, 'methods_tried': methods_tried})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/accounts/<acc_id>/join', methods=['POST'])
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
    acc['status'] = 'joining'
    acc['active'] = True
    save_data()
    log_account(acc['id'], acc['name'], f'Joining server "{sv["name"]}"')
    threading.Thread(target=launch_mumu, args=(acc, link, sv), daemon=True).start()
    return jsonify({'status': 'joining', 'link': link})

@app.route('/api/join-all', methods=['POST'])
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
            acc['status'] = 'joining'
            acc['active'] = True
            threading.Thread(target=launch_mumu, args=(acc, link, sv), daemon=True).start()
            count += 1
    save_data()
    log_activity(f'Join all: {count} accounts starting')
    return jsonify({'status': 'joining', 'count': count})

@app.route('/api/accounts/<acc_id>/disconnect', methods=['POST'])
def disconnect_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if acc:
        acc['active'] = False
        acc['status'] = 'idle'
        save_data()
        log_account(acc['id'], acc['name'], 'Disconnected')
    return jsonify({'success': True})

def find_mumu_vmm():
    path = r'C:\Program Files\MuMuVMMvbox\Hypervisor\MuMuVMMManage.exe'
    if os.path.isfile(path):
        return path
    path2 = r'C:\Program Files\MuMu\emulator\MuMuPlayer\shell\MuMuVMMManage.exe'
    if os.path.isfile(path2):
        return path2
    return None

def mumu_vm_cmd(args):
    vmm = find_mumu_vmm()
    if not vmm:
        return None, 'MuMuVMM not found'
    try:
        r = subprocess.run([vmm] + args, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip() or r.stderr.strip()
    except subprocess.TimeoutExpired:
        return None, 'Command timed out'
    except Exception as e:
        return None, str(e)

def load_vm_display_names():
    names = {}
    base = 'G:\\MuMuPlayerGlobal\\vms'
    for i in range(5):
        path = os.path.join(base, f'MuMuPlayerGlobal-12.0-{i}', 'configs', 'extra_config.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                dn = data.get('playerName', '')
                if dn:
                    names[f'MuMuPlayerGlobal-12.0-{i}'] = dn
        except:
            pass
    return names

def ensure_vm_running(serial, instance):
    vm_name = f'MuMuPlayerGlobal-12.0-{instance}'
    ok, msg = adb_connect(serial)
    if ok:
        return True
    code, out = mumu_vm_cmd(['list', 'runningvms'])
    if code == 0 and vm_name in out:
        return False
    log_activity(f'[AutoRestart] VM {vm_name} down, starting...')
    c, o = mumu_vm_cmd(['startvm', vm_name, '--type', 'headless'])
    if c != 0:
        log_activity(f'[AutoRestart] Failed to start {vm_name}: {o}', 'error')
        return False
    for attempt in range(30):
        time.sleep(4)
        ok, _ = adb_connect(serial)
        if ok:
            log_activity(f'[AutoRestart] VM {vm_name} started successfully')
            send_webhook(f'🟢 VM Auto-Restart: {vm_name}', f'Instance {instance} has been restarted successfully', 0x43e97b)
            return True
        code2, out2 = mumu_vm_cmd(['list', 'runningvms'])
        if code2 == 0 and vm_name in out2:
            log_activity(f'[AutoRestart] VM {vm_name} running (waiting ADB)')
    log_activity(f'[AutoRestart] VM {vm_name} start timed out', 'error')
    send_webhook(f'🔴 VM Auto-Restart Failed: {vm_name}', f'Instance {instance} failed to start after 2 minutes', 0xff4444)
    return False

@app.route('/api/mumu/vms', methods=['GET'])
def mumu_list_vms():
    code, out = mumu_vm_cmd(['list', 'vms'])
    if code is None:
        return jsonify({'vmm_found': False, 'vms': []})
    vms = []
    display_names = load_vm_display_names()
    for line in out.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('{')
        name = parts[0].strip().strip('"')
        uid = '{' + parts[1] if len(parts) > 1 else ''
        display = display_names.get(name, name)
        vms.append({'name': name, 'display_name': display, 'uuid': uid, 'running': False})

    code2, out2 = mumu_vm_cmd(['list', 'runningvms'])
    if code2 == 0:
        for line in out2.split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split('{')
            name = parts[0].strip().strip('"')
            for vm in vms:
                if vm['name'] == name:
                    vm['running'] = True

    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    for vm in vms:
        m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', vm['name'])
        if m:
            idx = int(m.group(1))
            if idx < len(serials) and serials[idx]:
                s = serials[idx]
                adb_connect(s)
                vm['roblox_running'] = adb_check_roblox(s)
            else:
                vm['roblox_running'] = False
        else:
            vm['roblox_running'] = False
    return jsonify({'vmm_found': True, 'vmm_path': find_mumu_vmm(), 'vms': vms})

@app.route('/api/mumu/vms/<vm_name>/restart', methods=['POST'])
def mumu_restart_vm(vm_name):
    log_activity(f'Restarting MuMu VM "{vm_name}"...')
    stop_resp = mumu_stop_vm(vm_name)
    if stop_resp[1] != 200:
        return stop_resp
    time.sleep(5)
    return mumu_start_vm(vm_name)

@app.route('/api/mumu/vms/<vm_name>/start', methods=['POST'])
def mumu_start_vm(vm_name):
    m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', vm_name)
    if m:
        user_shutdown_instances.discard(int(m.group(1)))
    code, out = mumu_vm_cmd(['startvm', vm_name, '--type', 'headless'])
    if code == 0:
        log_activity(f'MuMu VM "{vm_name}" started')
        return jsonify({'success': True, 'message': out})
    return jsonify({'success': False, 'message': out}), 500

@app.route('/api/mumu/vms/<vm_name>/stop', methods=['POST'])
def mumu_stop_vm(vm_name):
    m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', vm_name)
    if m:
        user_shutdown_instances.add(int(m.group(1)))
    log_activity(f'Stopping MuMu VM "{vm_name}"...')
    for attempt in range(5):
        code, out = mumu_vm_cmd(['controlvm', vm_name, 'acpipowerbutton'])
        time.sleep(4)
        code2, out2 = mumu_vm_cmd(['list', 'runningvms'])
        if code2 == 0 and vm_name not in out2 and '"' + vm_name + '"' not in out2:
            log_activity(f'MuMu VM "{vm_name}" stopped')
            return jsonify({'success': True, 'message': 'VM stopped via ACPI'})
    log_activity(f'ACPI failed, forcing poweroff for VM "{vm_name}"')
    code, out = mumu_vm_cmd(['controlvm', vm_name, 'poweroff'])
    if code == 0:
        time.sleep(2)
        log_activity(f'MuMu VM "{vm_name}" force stopped')
        return jsonify({'success': True, 'message': 'VM force stopped'})
    return jsonify({'success': False, 'message': out or 'VM did not stop'}), 500

def build_join_link(sv):
    base = sv.get('place_id', '')
    if sv['type'] == 'private':
        if sv.get('link'):
            return sv['link']
        code = sv.get('server_code', '')
        if code:
            return f'https://www.roblox.com/share?code={urllib.parse.quote(code)}&type=Server'
    return f'roblox://placeId={base}'

def launch_mumu(acc, link, sv):
    max_retries = settings.get('max_retries', 5)
    delay = settings.get('rejoin_delay', 3)
    instance = acc.get('mumu_instance', 0)
    serial = get_serial(instance)

    if not serial:
        log_account(acc['id'], acc['name'], f'Instance {instance}: serial kosong', 'error')
        acc['status'] = 'error'
        acc['active'] = False
        save_data()
        return

    ok, msg = adb_connect(serial)
    if not ok:
        log_account(acc['id'], acc['name'], f'{serial} gagal: {msg}', 'error')
        acc['status'] = 'error'
        acc['active'] = False
        save_data()
        return

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(delay)
            url = build_join_link(sv)
            adb_force_stop_roblox(serial)
            time.sleep(3)
            code, out = adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{url}'", '-p', 'com.roblox.client'], serial)
            time.sleep(20)
            adb_dismiss_dialogs(serial)
            if code != 0 and code is not None:
                log_account(acc['id'], acc['name'], f'ADB: {out}', 'warning')
            acc['status'] = 'connected'
            acc['last_joined'] = time.strftime('%H:%M:%S')
            acc['last_join_time'] = time.time()
            log_account(acc['id'], acc['name'], f'Join via {serial} berhasil')
            save_data()
            return
        except Exception as e:
            log_account(acc['id'], acc['name'], f'Error: {str(e)}', 'error')
            acc['status'] = 'error'
    acc['active'] = False
    acc['status'] = 'error'
    save_data()

@app.route('/api/mumu/start-all-and-join', methods=['POST'])
def mumu_start_all_and_join():
    code, out = mumu_vm_cmd(['list', 'runningvms'])
    running_names = []
    if code == 0:
        for line in out.split('\n'):
            line = line.strip()
            if line:
                running_names.append(line.split('{')[0].strip().strip('"'))
    all_vms = [{'name': f'MuMuPlayerGlobal-12.0-{i}', 'running': False} for i in range(5)]
    for vm in all_vms:
        if vm['name'] in running_names:
            vm['running'] = True
    results = []
    for idx, vm in enumerate(all_vms):
        serials = settings.get('mumu_serials', [])
        serial = serials[idx] if idx < len(serials) else None
        result = {'instance': idx, 'name': vm['name'], 'running': vm['running'], 'serial': serial, 'status': 'ok', 'message': ''}
        if not vm['running']:
            log_activity(f'[StartAll] Starting {vm["name"]}...')
            c, o = mumu_vm_cmd(['startvm', vm['name'], '--type', 'headless'])
            if c != 0:
                result['status'] = 'error'
                result['message'] = o
                results.append(result)
                continue
            booted = False
            for attempt in range(24):
                time.sleep(5)
                code2, out2 = mumu_vm_cmd(['list', 'runningvms'])
                if code2 == 0 and vm['name'] in out2:
                    booted = True
                    break
                if serial:
                    ok, _ = adb_connect(serial)
                    if ok:
                        booted = True
                        break
            if not booted:
                result['status'] = 'error'
                result['message'] = 'Timed out waiting for boot'
                results.append(result)
                continue
        if serial:
            ok, msg = adb_connect(serial)
            if not ok:
                result['status'] = 'error'
                result['message'] = f'ADB connect failed: {msg}'
                results.append(result)
                continue
            accounts_for_idx = [a for a in accounts if a.get('mumu_instance') == idx and a.get('cookie')]
            if accounts_for_idx:
                acc = accounts_for_idx[0]
                sv = None
                if acc.get('server_id'):
                    sv = next((s for s in servers if s['id'] == acc['server_id']), None)
                if not sv and servers:
                    sv = servers[0]
                if sv:
                    link = build_join_link(sv)
                    adb_force_stop_roblox(serial)
                    time.sleep(3)
                    adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'", '-p', 'com.roblox.client'], serial)
                    acc['status'] = 'connected'
                    acc['active'] = True
                    acc['last_joined'] = time.strftime('%H:%M:%S')
                    result['message'] = f'Joined {sv["name"]}'
                    log_account(acc['id'], acc['name'], f'Joined {sv["name"]} on {vm["name"]}')
                else:
                    result['message'] = 'No server configured'
            else:
                result['message'] = 'No account for this instance'
        results.append(result)
    save_data()
    return jsonify({'results': results})

@app.route('/api/quick-join-instance/<int:instance_idx>/<place_id>', methods=['POST'])
def quick_join_instance(instance_idx, place_id):
    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    if instance_idx < 0 or instance_idx >= len(serials):
        return jsonify({'status': 'error', 'message': 'Invalid instance index'}), 400
    serial = serials[instance_idx]
    if not serial or not serial.strip():
        return jsonify({'status': 'error', 'message': 'No serial for this instance'}), 400
    ok, msg = adb_connect(serial.strip())
    if not ok:
        return jsonify({'status': 'error', 'message': msg}), 500
    link = f'roblox://placeId={place_id}'
    adb_force_stop_roblox(serial.strip())
    time.sleep(3)
    adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'", '-p', 'com.roblox.client'], serial.strip())
    time.sleep(20)
    adb_dismiss_dialogs(serial.strip())
    log_activity(f'[QuickJoin] Instance {instance_idx} opened place {place_id}')
    return jsonify({'status': 'ok', 'instance': instance_idx, 'serial': serial.strip()})

@app.route('/api/quick-join/<place_id>', methods=['POST'])
def quick_join(place_id):
    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    results = []
    for idx, serial in enumerate(serials):
        if not serial or not serial.strip():
            results.append({'instance': idx, 'status': 'skipped', 'message': 'No serial'})
            continue
        ok, msg = adb_connect(serial.strip())
        if not ok:
            results.append({'instance': idx, 'status': 'error', 'message': msg})
            continue
        link = f'roblox://placeId={place_id}'
        adb_force_stop_roblox(serial.strip())
        time.sleep(3)
        adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'", '-p', 'com.roblox.client'], serial.strip())
        time.sleep(20)
        adb_dismiss_dialogs(serial.strip())
        results.append({'instance': idx, 'status': 'ok', 'serial': serial.strip(), 'message': f'Opening {place_id}'})
        log_activity(f'[QuickJoin] Instance {idx} opened place {place_id}')
    return jsonify({'results': results, 'place_id': place_id})

@app.route('/api/mumu/test', methods=['POST'])
def mumu_test():
    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    adb = find_adb()
    results = []
    for i, s in enumerate(serials):
        if not s or not s.strip():
            results.append({'instance': i, 'serial': '', 'connected': False, 'message': 'Kosong'})
        else:
            ok, msg = adb_connect(s.strip())
            results.append({'instance': i, 'serial': s.strip(), 'connected': ok, 'message': msg})
    return jsonify({
        'adb_found': adb is not None,
        'adb_path': adb or '',
        'instances': results
    })

@app.route('/api/mumu/<int:instance>/screenshot', methods=['GET'])
def mumu_screenshot(instance):
    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    if instance < 0 or instance >= len(serials):
        return 'Invalid instance', 404
    serial = serials[instance]
    if not serial or not serial.strip():
        return 'No serial', 404
    data = adb_screenshot(serial)
    if data is None:
        return 'Screenshot failed', 500
    return Response(data, mimetype='image/png',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate', 'Pragma': 'no-cache'})

@app.route('/api/webhook/test', methods=['POST'])
def test_webhook():
    url = request.json.get('url', '')
    if not url:
        return jsonify({'success': False, 'error': 'URL kosong'})
    if not url.startswith('http'):
        return jsonify({'success': False, 'error': f'URL harus http(s), received: "{url[:50]}"'})
    try:
        import urllib.request
        data = json.dumps({
            'embeds': [{
                'title': '✅ Test Notifikasi Dashboard Roblox',
                'description': 'Webhook berfungsi dengan baik!',
                'color': 0x43e97b,
                'footer': {'text': 'Dashboard Roblox'}
            }]
        }).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'DashboardRoblox/1.0'})
        urllib.request.urlopen(req, timeout=10)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': f'{type(e).__name__}: {str(e)[:200]}'})

@app.route('/api/mumu/scan', methods=['GET'])
def mumu_scan():
    adb = find_adb()
    vm_base = 'G:\\MuMuPlayerGlobal\\vms'
    mac_to_idx = {}
    for i in range(5):
        mac_path = os.path.join(vm_base, f'MuMuPlayerGlobal-12.0-{i}', 'macaddress')
        try:
            with open(mac_path, 'r') as f:
                mac = f.read().strip().lower().replace(':', '').replace('-', '')
                mac_to_idx[mac] = i
        except:
            pass

    ip_to_mac = {}
    try:
        r = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=10)
        for line in r.stdout.split('\n'):
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0].count('.') == 3:
                ip = parts[0]
                mac_raw = parts[1].replace('-', '').lower()
                ip_to_mac[ip] = mac_raw
    except:
        pass

    adb_ips = {}
    if adb:
        try:
            r = subprocess.run([adb, 'devices'], capture_output=True, text=True, timeout=10)
            for l in r.stdout.strip().split('\n')[1:]:
                parts = l.strip().split('\t')
                if len(parts) >= 2 and parts[1] == 'device':
                    ip_port = parts[0]
                    ip = ip_port.split(':')[0]
                    adb_ips[ip] = ip_port
        except:
            pass

    serials = settings.get('mumu_serials', ['', '', '', '', ''])
    for ip, mac in ip_to_mac.items():
        if mac in mac_to_idx and ip in adb_ips:
            idx = mac_to_idx[mac]
            serials[idx] = adb_ips[ip]

    settings['mumu_serials'] = serials
    save_data()

    found = []
    for idx, s in enumerate(serials):
        dn = load_vm_display_names().get(f'MuMuPlayerGlobal-12.0-{idx}', f'VM-{idx}')
        if s:
            found.append({'instance': idx, 'name': dn, 'serial': s})
    return jsonify({'devices': found, 'mumu_serials': serials})

@app.route('/api/status', methods=['POST'])
def receive_status():
    data = request.json
    acc_name = data.get('account', 'unknown')
    status = data.get('status', 'unknown')
    msg = data.get('message', '')
    for acc in accounts:
        if acc['name'] == acc_name:
            old_status = acc.get('status', '')
            acc['status'] = status
            if status in ('monitoring', 'active', 'connected'):
                acc['active'] = True
            elif status in ('kicked', 'left', 'disconnected', 'error'):
                acc['active'] = False
                if status in ('kicked', 'error') and status != old_status:
                    send_webhook(
                        f'⚠️ {acc_name} — {status.upper()}',
                        f'**Server:** {msg or "N/A"}\n**Instance:** MuMu-{acc.get("mumu_instance", "?")}',
                        0xff4444 if status == 'error' else 0xffaa00,
                        acc.get('verified_avatar')
                    )
            save_data()
            break
    log_activity(f'[{acc_name}] {msg}', 'info' if status != 'error' else 'error')
    return jsonify({'success': True})

@app.route('/api/activity', methods=['DELETE'])
def clear_activity_api():
    global activity_log
    activity_log = []
    return jsonify({'success': True})

@app.route('/api/accounts/<acc_id>/logs', methods=['GET'])
def get_account_logs(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    name = acc['name'] if acc else '?'
    logs = acc_logs.get(acc_id, [])
    return jsonify({'logs': logs, 'name': name})

def make_script_for(place_id, server_code, name, delay, retries):
    return f'''--[[ Roblox Auto-Join Monitor - {name} ]]
local Players=game:GetService("Players")
local TeleportService=game:GetService("TeleportService")
local HttpService=game:GetService("HttpService")
local StarterGui=game:GetService("StarterGui")
local LocalPlayer=Players.LocalPlayer
local PLACE_ID={place_id}
local SERVER_CODE="{server_code}"
local REJOIN_DELAY={delay}
local MAX_RETRIES={retries}
local URL="http://localhost:5000"
local NAME="{name}"
local rejoining=false
local function n(t,d)pcall(function()StarterGui:SetCore("SendNotification",{{Title="Auto-Join",Text=t,Duration=d or 5}})end)end
local function s(st,msg)pcall(function()HttpService:PostAsync(URL.."/api/status",HttpService:JSONEncode({{account=NAME,status=st,message=msg}}),Enum.HttpContentType.ApplicationJson)end)end
local function r()if rejoining then return end rejoining=true n("Rejoining in "..REJOIN_DELAY.."s...",REJOIN_DELAY)
for a=1,MAX_RETRIES do local ok,err=pcall(function()if SERVER_CODE~="" then TeleportService:TeleportToPrivateServer(PLACE_ID,SERVER_CODE,{{LocalPlayer}})else TeleportService:Teleport(PLACE_ID,LocalPlayer)end end)
if ok then rejoining=false s("rejoined","OK")return end n("Retry "..a.."/"..MAX_RETRIES,2)if a<MAX_RETRIES then task.wait(REJOIN_DELAY)end end rejoining=false s("error","Max retries")end
LocalPlayer.OnKick:Connect(function(m)s("kicked",m)task.wait(REJOIN_DELAY)r()end)
Players.PlayerRemoving:Connect(function(p)if p==LocalPlayer then s("left","Left")task.wait(REJOIN_DELAY)r()end end)
TeleportService.TeleportInitFailed:Connect(function(p,st,m)if p==LocalPlayer then s("teleport_failed",m)task.wait(REJOIN_DELAY)r()end end)
s("monitoring","Aktif")n("Monitor ready!",5)
while task.wait(30)do s("active","Monitoring...")end'''

@app.route('/api/generate-script', methods=['GET'])
def generate_script():
    first_sv = servers[0] if servers else None
    place_id = first_sv['place_id'] if first_sv else 'PLACE_ID_HERE'
    server_code = first_sv['server_code'] if first_sv and first_sv.get('server_code') else ''
    delay = settings.get('rejoin_delay', 3)
    retries = settings.get('max_retries', 5)
    script = make_script_for(place_id, server_code, 'Account-1', delay, retries)
    return jsonify({'script': script, 'filename': 'AutoJoinMonitor.luau'})

@app.route('/api/accounts/<acc_id>/push-script', methods=['POST'])
def push_script(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    sv = next((s for s in servers if s['id'] == acc.get('server_id')), None)
    if not sv and servers:
        sv = servers[0]
    if not sv:
        return jsonify({'error': 'No server assigned'}), 400
    place_id = sv.get('place_id', '')
    server_code = sv.get('server_code', '') if sv.get('type') == 'private' else ''
    if not place_id:
        return jsonify({'error': 'Server has no place ID'}), 400
    delay = settings.get('rejoin_delay', 3)
    retries = settings.get('max_retries', 5)
    name = acc.get('name', 'Account')
    script = make_script_for(place_id, server_code, name, delay, retries)

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
        code, out = adb_cmd(['push', tmp, '/sdcard/Delta/Autoexecute/monitor.luau'], serial)
        if code != 0:
            return jsonify({'error': f'ADB push failed: {out}'}), 500
        if acc:
            log_account(acc_id, name, 'Script pushed to Delta Autoexecute')
        return jsonify({'success': True, 'message': 'Script pushed to Delta Autoexecute on VM'})
    finally:
        try: os.remove(tmp)
        except: pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    serials = settings.get('mumu_serials', [])
    info = ', '.join([f'#{i}:{s or "?"}' for i, s in enumerate(serials)])
    print(f'Dashboard Roblox running on http://localhost:{port}')
    print(f'ADB: {find_adb() or "not found"}')
    print(f'Instances: {info}')
    start_monitor()
    print(f'Monitor thread started (interval: {settings.get("monitor_interval", 5)}s)')
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
