#!/usr/bin/env python3
"""
Dashboard Roblox - Remote Monitor (Root Mode)
Jalankan di Termux (Redfinger) untuk auto-rejoin via su commands.
Connect ke PC dashboard via HTTP.

Cara pakai:
    python remote_monitor.py --url https://dashboard.aavpanel.my.id
"""

import argparse
import json
import os
import sys
import time
import subprocess
import threading
import urllib.request
import urllib.error
import re


class RootMonitor:
    def __init__(self, dashboard_url, poll_interval=5):
        self.dashboard_url = dashboard_url.rstrip('/')
        self.poll_interval = poll_interval
        self.packages = []
        self.account_map = {}
        self.running = False
        self.settings = {}
        self.has_root = self._check_root()
        self.device_id = self._generate_device_id()
        print(f'[DEVICE] Device ID: {self.device_id}')

    def _generate_device_id(self):
        import socket
        try:
            hostname = socket.gethostname()
            if hostname and hostname != 'localhost':
                return f"rf-{hostname}"
        except:
            pass
        code, out = self.su_cmd('settings get secure android_id')
        if code == 0 and out and out.strip() and out.strip() != 'null':
            return f"rf-{out.strip()[:12]}"
        return f"rf-{int(time.time()) % 100000}"

    def _check_root(self):
        try:
            r = subprocess.run(['su', '-c', 'echo ok'],
                capture_output=True, text=True, timeout=5)
            ok = r.returncode == 0 and 'ok' in r.stdout
            if ok:
                print('[ROOT] Root access: OK')
            else:
                print('[ROOT] Root access: FAILED')
            return ok
        except Exception as e:
            print(f'[ROOT] Root check error: {e}')
            return False

    def su_cmd(self, command, timeout=15):
        try:
            r = subprocess.run(['su', '-c', command],
                capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout.strip() or r.stderr.strip()
        except subprocess.TimeoutExpired:
            return None, 'timeout'
        except Exception as e:
            return None, str(e)

    def check_roblox(self, package='com.roblox.client'):
        code, out = self.su_cmd(f'pidof {package}')
        if code == 0 and out:
            pids = out.split()
            return bool(pids and pids[0].isdigit())
        return False

    def get_pid(self, package='com.roblox.client'):
        code, out = self.su_cmd(f'pidof {package}')
        if code == 0 and out:
            pid = out.split()[0]
            if pid.isdigit():
                return pid
        return None

    def get_thread_count(self, package='com.roblox.client'):
        pid = self.get_pid(package)
        if not pid:
            return None
        code, out = self.su_cmd(f'cat /proc/{pid}/status')
        if code == 0:
            for line in out.split('\n'):
                if 'Threads' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except:
                            pass
        return None

    def force_stop(self, package='com.roblox.client'):
        self.su_cmd(f'am force-stop {package}')

    def start_app(self, package='com.roblox.client'):
        self.su_cmd(f'am start -n {package}/.RobloxApp')

    def start_join_intent(self, package, link):
        self.force_stop(package)
        time.sleep(3)
        cmd = f"am start -a android.intent.action.VIEW -d '{link}' -p {package}"
        code, out = self.su_cmd(cmd)
        return code == 0

    def detect_kicked(self, package='com.roblox.client'):
        pid = self.get_pid(package)
        if not pid:
            return None
        code, out = self.su_cmd('dumpsys window windows')
        if code == 0:
            for line in out.split('\n'):
                if 'mIsFloatingLayer=true' in line and package in line:
                    return 'floating_dialog'
                if package in line.lower() and any(k in line.lower() for k in
                    ['disconnected', 'kicked', 'reconnecting', 'connection lost']):
                    return 'kicked_dialog'
        return None

    def dismiss_dialogs(self):
        for _ in range(3):
            self.su_cmd('input keyevent KEYCODE_BACK')
            time.sleep(0.2)
        for xy in [('540', '960'), ('540', '800')]:
            self.su_cmd(f'input tap {xy[0]} {xy[1]}')
            time.sleep(0.2)

    def discover_packages(self):
        code, out = self.su_cmd('pm list packages')
        if code == 0 and out:
            found = []
            for line in out.split('\n'):
                pkg = line.replace('package:', '').strip()
                if 'roblox' in pkg.lower():
                    found.append(pkg)
            return sorted(found)
        return []

    def get_app_label(self, package):
        code, out = self.su_cmd(f'pm path {package}')
        if code == 0 and out:
            apk = out.replace('package:', '').strip()
            code2, out2 = self.su_cmd(f'aapt dump badging {apk} 2>/dev/null | grep "application-label:"')
            if code2 == 0 and out2:
                label = out2.replace('application-label:', '').strip().strip("'")
                if label:
                    return label
        return package.split('.')[-1]

    def get_screen_size(self):
        code, out = self.su_cmd('wm size')
        if code == 0:
            m = re.search(r'(\d+)x(\d+)', out)
            if m:
                return int(m.group(1)), int(m.group(2))
        return 1080, 1920

    def get_uptime(self):
        code, out = self.su_cmd('cat /proc/uptime')
        if code == 0 and out:
            parts = out.split()
            if parts:
                secs = float(parts[0])
                days = int(secs // 86400)
                hrs = int((secs % 86400) // 3600)
                mins = int((secs % 3600) // 60)
                return {'seconds': int(secs), 'formatted': f'{days}d {hrs}h {mins}m' if days else f'{hrs}h {mins}m'}
        return None

    def get_memory_info(self):
        code, out = self.su_cmd('cat /proc/meminfo')
        if code == 0:
            total = available = None
            for line in out.split('\n'):
                if 'MemTotal:' in line:
                    total = int(line.split()[1])
                if 'MemAvailable:' in line:
                    available = int(line.split()[1])
            if total and available and total > 0:
                used = total - available
                return {
                    'total_mb': round(total / 1024),
                    'used_mb': round(used / 1024),
                    'available_mb': round(available / 1024),
                    'used_percent': round(used / total * 100, 1)
                }
        return None

    def get_storage_info(self):
        code, out = self.su_cmd('df /data')
        if code == 0:
            lines = out.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    total = int(parts[1]) * 1024
                    used = int(parts[2]) * 1024
                    avail = int(parts[3]) * 1024
                    return {
                        'total_gb': round(total / (1024*1024*1024), 1),
                        'used_gb': round(used / (1024*1024*1024), 1),
                        'available_gb': round(avail / (1024*1024*1024), 1),
                        'used_percent': round(used / total * 100, 1) if total > 0 else 0
                    }
        return None

    def get_battery_info(self):
        code, out = self.su_cmd('dumpsys battery')
        if code == 0:
            level = temperature = voltage = status = None
            for line in out.split('\n'):
                line = line.strip()
                if 'level:' in line:
                    try: level = int(line.split(':')[1].strip())
                    except: pass
                if 'temperature:' in line:
                    try: temperature = int(line.split(':')[1].strip()) / 10
                    except: pass
                if 'voltage:' in line:
                    try: voltage = int(line.split(':')[1].strip())
                    except: pass
                if 'status:' in line:
                    try: status = int(line.split(':')[1].strip())
                    except: pass
            if level is not None:
                status_map = {1: 'Unknown', 2: 'Charging', 3: 'Discharging', 4: 'Not charging', 5: 'Full'}
                return {
                    'level': level,
                    'temperature_c': temperature,
                    'voltage_mv': voltage,
                    'status': status_map.get(status, 'Unknown')
                }
        return None

    def get_device_health(self):
        return {
            'device_id': self.device_id,
            'uptime': self.get_uptime(),
            'memory': self.get_memory_info(),
            'storage': self.get_storage_info(),
            'battery': self.get_battery_info(),
            'root': self.has_root,
            'timestamp': time.time()
        }

    def report_health(self):
        health = self.get_device_health()
        return self.http_post('/api/remote/health', {
            'device_id': self.device_id,
            'health': health
        })

    def reset_app(self, package):
        print(f'[RESET] Clearing data for {package}...')
        self.su_cmd(f'am force-stop {package}')
        time.sleep(1)
        code, out = self.su_cmd(f'pm clear {package}')
        if code == 0:
            print(f'[RESET] {package} cleared successfully')
            return True
        print(f'[RESET] Failed to clear {package}: {out}')
        return False

    def delta_get_link_from_ui(self, package='com.roblox.client'):
        code, out = self.su_cmd('uiautomator dump --compressed /data/local/tmp/delta_ui.xml 2>/dev/null; cat /data/local/tmp/delta_ui.xml 2>/dev/null; rm -f /data/local/tmp/delta_ui.xml')
        if code == 0 and out:
            urls = re.findall(r'https?://[^\s"\'<>]+', out)
            for u in urls:
                low = u.lower()
                if any(k in low for k in ['key', 'verify', 'delta', 'linkvertise', 'the model', 'bypass', 'executor']):
                    return u
            if urls:
                return urls[0]
        return None

    def delta_get_link_from_logcat(self, package='com.roblox.client'):
        code, out = self.su_cmd('logcat -d 2>/dev/null')
        if code == 0:
            urls = set()
            for line in out.split('\n'):
                for u in re.findall(r'https?://[^\s"\'<>)]+', line):
                    low = u.lower()
                    if any(k in low for k in ['key', 'verify', 'delta', 'linkvertise', 'the model', 'bypass', 'executor']):
                        return u
                    if 'roblox' not in low:
                        urls.add(u)
            for u in sorted(urls, key=len):
                return u
        return None

    def delta_capture_url(self, package='com.roblox.client'):
        for fn in [self.delta_get_link_from_ui, self.delta_get_link_from_logcat]:
            url = fn(package)
            if url:
                return url
        return None

    def delta_find_button(self, label):
        code, out = self.su_cmd('uiautomator dump --compressed /data/local/tmp/delta_btn.xml 2>/dev/null; cat /data/local/tmp/delta_btn.xml 2>/dev/null; rm -f /data/local/tmp/delta_btn.xml')
        if code == 0 and out:
            label_lower = label.lower()
            for node in re.finditer(r'<node\s+([^>]+?)/?\s*>', out):
                attrs = node.group(1)
                text = re.search(r'text="([^"]*)"', attrs)
                cd = re.search(r'content-desc="([^"]*)"', attrs)
                txt = ((text.group(1) if text else '') + ' ' + (cd.group(1) if cd else '')).lower()
                if label_lower not in txt:
                    continue
                bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', attrs)
                if bounds:
                    cx = (int(bounds.group(1)) + int(bounds.group(3))) // 2
                    cy = (int(bounds.group(2)) + int(bounds.group(4))) // 2
                    return cx, cy
        return None

    def delta_inject_key(self, key):
        pt = self.delta_find_button('Enter key')
        if not pt:
            pt = self.delta_find_button('KEY')
        if not pt:
            pt = self.delta_find_button('enter')
        if pt:
            self.su_cmd(f'input tap {pt[0]} {pt[1]}')
        else:
            self.su_cmd('input tap 540 960')
        time.sleep(1)
        key_part = key[:20]
        self.su_cmd(f'input text {key_part}')
        if len(key) > 20:
            time.sleep(0.3)
            self.su_cmd(f'input text {key[20:]}')
        time.sleep(1)
        verify_pt = self.delta_find_button('Continue')
        if not verify_pt:
            verify_pt = self.delta_find_button('VERIFY')
        if not verify_pt:
            verify_pt = self.delta_find_button('SUBMIT')
        if verify_pt:
            self.su_cmd(f'input tap {verify_pt[0]} {verify_pt[1]}')
        return True

    def find_delta_package(self):
        code, out = self.su_cmd('pm list packages')
        if code == 0 and out:
            for line in out.split('\n'):
                pkg = line.replace('package:', '').strip()
                if 'delta' in pkg.lower():
                    return pkg
        candidates = [
            'com.delta.executor',
            'delta.executor',
            'com.delta.app',
            'com.delta.lua',
            'com.delta',
        ]
        for c in candidates:
            code2, _ = self.su_cmd(f'pm path {c} 2>/dev/null')
            if code2 == 0:
                return c
        return 'com.delta.executor'

    def delta_launch_and_capture_url(self, delta_pkg):
        print(f'[DELTA] Launching {delta_pkg}...')
        self.su_cmd(f'am force-stop {delta_pkg}')
        time.sleep(1)
        self.su_cmd(f'monkey -p {delta_pkg} 1')
        time.sleep(8)

        disp_w, disp_h = 720, 1280
        code, out = self.su_cmd('wm size')
        if code == 0:
            m = re.search(r'(\d+)x(\d+)', out)
            if m:
                pw, ph = int(m.group(1)), int(m.group(2))
                code2, out2 = self.su_cmd('dumpsys display')
                if code2 == 0:
                    ov = re.search(r'OverrideDisplayInfo.*?real (\d+) x (\d+)', out2, re.DOTALL)
                    if ov:
                        disp_w, disp_h = int(ov.group(1)), int(ov.group(2))
                    elif 'orientation=1' in out2 or 'orientation=3' in out2:
                        disp_w, disp_h = ph, pw
                    else:
                        disp_w, disp_h = pw, ph
                else:
                    disp_w, disp_h = pw, ph

        print(f'[DELTA] Screen: {disp_w}x{disp_h}')

        self.su_cmd('logcat -c 2>/dev/null')

        receive_key_pt = self.delta_find_button('Receive Key')
        if not receive_key_pt:
            receive_key_pt = self.delta_find_button('receive')
        if not receive_key_pt:
            receive_key_pt = self.delta_find_button('key')
        if receive_key_pt:
            print(f'[DELTA] Found "Receive Key" button at ({receive_key_pt[0]},{receive_key_pt[1]})')
        else:
            print(f'[DELTA] Button not found via UI dump, using coordinate fallback')
            rx, ry = int(disp_w * 0.835), int(disp_h * 0.365)
            receive_key_pt = (rx, ry)
            print(f'[DELTA] Fallback tap at ({rx},{ry})')

        self.su_cmd(f'input tap {receive_key_pt[0]} {receive_key_pt[1]}')
        print(f'[DELTA] Tapped "Receive Key"')
        time.sleep(3)

        url = None
        for attempt in range(8):
            code, out = self.su_cmd('logcat -d -s ActivityTaskManager 2>/dev/null')
            if code == 0 and out:
                for line in out.split('\n'):
                    if 'ACTION_VIEW' in line and 'http' in line:
                        for u in re.findall(r'https?://[^\s"\'<>)]+', line.replace('...', '')):
                            low = u.lower()
                            if any(k in low for k in [
                                'linkvertise', 'lootlabs', 'gateway', 'bypass', 'key',
                                'verify', 'delta', 'executor', 'platorelay', 'auth.',
                                'notification', 'fluxus', 'weaken', 'survey'
                            ]):
                                url = u
                                print(f'[DELTA] URL from logcat intent: {u[:150]}')
                                break
                        if url:
                            break
            if url:
                break
            time.sleep(1)

        if not url:
            print('[DELTA] Scanning full logcat...')
            code, out = self.su_cmd('logcat -d 2>/dev/null')
            if code == 0 and out:
                for line in out.split('\n'):
                    if 'http' in line.lower() and 'ACTION_VIEW' in line:
                        for u in re.findall(r'https?://[^\s"\'<>)]+', line.replace('...', '')):
                            low = u.lower()
                            if any(k in low for k in [
                                'linkvertise', 'lootlabs', 'gateway', 'bypass',
                                'key', 'verify', 'delta', 'executor', 'platorelay',
                                'auth.', 'notification', 'fluxus'
                            ]):
                                url = u
                                print(f'[DELTA] URL from full logcat: {u[:150]}...')
                                break
                        if url:
                            break

        if not url:
            print('[DELTA] Scanning dumpsys recents...')
            code, out = self.su_cmd('dumpsys activity recents 2>/dev/null')
            if code == 0 and out:
                for u in re.findall(r'https?://[^\s"\'<>)]+', out):
                    low = u.lower()
                    if any(k in low for k in [
                        'linkvertise', 'lootlabs', 'gateway', 'bypass', 'key',
                        'verify', 'delta', 'executor', 'platorelay', 'auth.',
                        'notification', 'fluxus'
                    ]):
                        url = u
                        print(f'[DELTA] URL from dumpsys: {u[:150]}...')
                        break

        if not url:
            print('[DELTA] Scanning UI dump...')
            url = self.delta_get_link_from_ui()

        if url:
            print(f'[DELTA] URL captured: {url[:150]}...')
            self.su_cmd('am force-stop com.android.chrome 2>/dev/null')
            time.sleep(1)
            return url

        print('[DELTA] No URL found - Delta key overlay may not have loaded')
        return None

    def delta_auto_get_key(self, package=None):
        delta_pkg = self.find_delta_package()
        print(f'[DELTA] Delta package: {delta_pkg}')
        print(f'[DELTA] Opening Delta and capturing key URL...')
        url = self.delta_launch_and_capture_url(delta_pkg)
        if url:
            print(f'[DELTA] Closing Chrome to prevent intercept...')
            self.su_cmd('am force-stop com.android.chrome 2>/dev/null')
            time.sleep(1)
        if not url:
            print(f'[DELTA] No URL found via launch method, trying passive capture...')
            url = self.delta_capture_url()
        if not url:
            return None, 'No key URL found'
        print(f'[DELTA] URL: {url[:80]}...')
        result = self.http_post('/api/remote/delta-key-bypass', {
            'device_id': self.device_id,
            'package': package or delta_pkg,
            'url': url
        })
        if result and result.get('key'):
            key = result['key']
            print(f'[DELTA] Key received: {key[:20]}...')
            self.delta_inject_key(key)
            print(f'[DELTA] Key injected successfully')
            return key, None
        if result and result.get('redirect'):
            print(f'[DELTA] Redirect to: {result["redirect"]}')
            return None, result.get('redirect')
        return None, result.get('error', 'Bypass failed')

    def extract_cookie(self, package='com.roblox.client'):
        paths = [
            f'/data/data/{package}/shared_prefs/roblox.xml',
            f'/data/data/{package}/shared_prefs/AuthInfo.xml',
        ]
        for path in paths:
            code, out = self.su_cmd(f'cat {path}')
            if code == 0 and out:
                m = re.search(r'<string name="ROBLOSECURITY">([^<]+)</string>', out)
                if m:
                    cookie = m.group(1)
                    if cookie.startswith('_|'):
                        return cookie
        code, out = self.su_cmd(f'ls /data/data/{package}/shared_prefs/')
        if code == 0 and out:
            for f in out.split('\n'):
                f = f.strip()
                if not f.endswith('.xml'):
                    continue
                code2, out2 = self.su_cmd(f'cat /data/data/{package}/shared_prefs/{f}')
                if code2 == 0 and out2:
                    m = re.search(r'<string name="ROBLOSECURITY">([^<]+)</string>', out2)
                    if m:
                        cookie = m.group(1)
                        if cookie.startswith('_|'):
                            return cookie
        code, out = self.su_cmd(f'sqlite3 /data/data/{package}/app_webview/Default/Cookies "SELECT value FROM cookies WHERE name=\'.ROBLOSECURITY\'"')
        if code == 0 and out and out.startswith('_|'):
            return out.strip()
        return None

    def send_cookie(self, package, cookie):
        return self.http_post('/api/remote/cookie', {
            'package': package,
            'cookie': cookie
        })

    def extract_all_cookies(self):
        results = []
        for pkg in self.packages:
            cookie = self.extract_cookie(pkg)
            if cookie:
                result = self.send_cookie(pkg, cookie)
                success = result and result.get('success')
                print(f'[{pkg}] Cookie extracted and sent: {"OK" if success else "FAILED"}')
                results.append({'package': pkg, 'success': success, 'has_cookie': True})
            else:
                print(f'[{pkg}] Cookie not found')
                results.append({'package': pkg, 'success': False, 'has_cookie': False})
        return results

    def push_script_to_all(self):
        script_resp = self.http_get('/api/generate-script')
        if not script_resp or not script_resp.get('script'):
            print('[SCRIPT] Failed to get script from dashboard')
            return []
        script = script_resp['script'].replace('http://localhost:5000', self.dashboard_url)
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), 'monitor.luau')
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(script)
        results = []
        for pkg in self.packages:
            dest_paths = [
                f'/sdcard/Delta/Autoexecute/monitor.luau',
                f'/sdcard/Android/data/{pkg}/files/Delta/Autoexecute/monitor.luau',
            ]
            success = False
            for dest in dest_paths:
                code, out = self.su_cmd(f'mkdir -p "$(dirname {dest})" && cp {tmp} {dest}')
                if code == 0:
                    success = True
                    print(f'[{pkg}] Push script: OK -> {dest}')
                    break
            if not success:
                print(f'[{pkg}] Push script: FAILED')
            results.append({'package': pkg, 'success': success})
        try: os.remove(tmp)
        except: pass
        return results

    def http_get(self, path):
        url = f'{self.dashboard_url}{path}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'RemoteMonitor/1.0')
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f'[HTTP] GET {path} failed: {e}')
            return None

    def http_post(self, path, data):
        url = f'{self.dashboard_url}{path}'
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(url, data=body,
                headers={'Content-Type': 'application/json', 'User-Agent': 'RemoteMonitor/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f'[HTTP] POST {path} failed: {e}')
            return None

    def register(self):
        packages_data = []
        for i, pkg in enumerate(self.packages):
            label = self.get_app_label(pkg)
            print(f'[MONITOR] Package: {pkg} → {label}')
            packages_data.append({'idx': i, 'name': pkg, 'label': label})
        data = {
            'device_id': self.device_id,
            'serial': 'root',
            'packages': packages_data
        }
        result = self.http_post('/api/remote/register', data)
        if result and result.get('success'):
            print(f'[MONITOR] Registered to dashboard ({len(self.packages)} packages)')
            self.account_map = result.get('account_map', {})
            return True
        print(f'[MONITOR] Register failed: {result}')
        return False

    def get_config(self):
        result = self.http_get('/api/remote/config')
        if result:
            self.settings = result
            self.poll_interval = result.get('monitor_interval', 5)
        return result

    def report_status(self, account_name, package, status, tc=None, kicked=None):
        data = {
            'account_name': account_name,
            'package': package,
            'status': status,
            'thread_count': tc,
            'kicked': kicked
        }
        return self.http_post('/api/remote/status', data)

    def get_commands(self, account_name):
        return self.http_get(f'/api/remote/commands?account={account_name}')

    def complete_command(self, cmd_id, success, message=''):
        return self.http_post(f'/api/remote/commands/{cmd_id}/complete', {
            'success': success,
            'message': message
        })

    def run(self):
        print(f'[MONITOR] Starting remote monitor (root mode)...')
        print(f'[MONITOR] Dashboard: {self.dashboard_url}')

        if not self.has_root:
            print('[MONITOR] ERROR: Root access required!')
            return

        self.packages = self.discover_packages()
        if not self.packages:
            print('[MONITOR] ERROR: No Roblox packages found')
            print('[MONITOR] Make sure Roblox apps are installed')
            return
        print(f'[MONITOR] Found packages: {self.packages}')

        if not self.register():
            print('[MONITOR] ERROR: Failed to register to dashboard')
            return

        print('[MONITOR] Pushing scripts to all packages...')
        self.push_script_to_all()

        self.running = True
        self._last_rejoin = {}
        self._last_health_report = 0
        print(f'[MONITOR] Monitor started! Polling every {self.poll_interval}s...')

        while self.running:
            try:
                self.get_config()
                rejoin_interval = self.settings.get('rejoin_interval', 2400)
                thread_threshold = self.settings.get('thread_threshold', 80)
                auto_join_global = self.settings.get('auto_join_enabled', True)
                account_settings = self.settings.get('account_settings', {})
                now = time.time()

                if now - self._last_health_report >= 60:
                    try:
                        self.report_health()
                        self._last_health_report = now
                    except Exception as e:
                        print(f'[HEALTH] Report failed: {e}')

                for pkg in self.packages:
                    if not self.running:
                        break

                    account_name = self.account_map.get(pkg, f'Unknown-{pkg}')
                    settings_key = f'{self.device_id}:{pkg}'
                    auto_join_acc = account_settings.get(settings_key, account_settings.get(pkg, {})).get('auto_join', True)

                    if not auto_join_global or not auto_join_acc:
                        self.report_status(account_name, pkg, 'paused')
                        continue

                    running = self.check_roblox(pkg)
                    if not running:
                        last = self._last_rejoin.get(pkg, 0)
                        if now - last < 60:
                            print(f'[{account_name}] COOLDOWN ({int(60 - (now - last))}s left), skipping')
                            self.report_status(account_name, pkg, 'cooldown')
                            continue
                        self.report_status(account_name, pkg, 'disconnected')
                        print(f'[{account_name}] NOT RUNNING ({pkg})')
                        link = self._get_join_link(account_name)
                        if link:
                            print(f'[{account_name}] → JOINING: {link[:80]}...')
                            self.start_join_intent(pkg, link)
                            self.report_status(account_name, pkg, 'rejoining')
                            self._last_rejoin[pkg] = now
                        else:
                            print(f'[{account_name}] → NO JOIN LINK!')
                        continue

                    tc = self.get_thread_count(pkg)
                    kicked = self.detect_kicked(pkg)

                    last = self._last_rejoin.get(pkg, 0)
                    if now - last < 60 and tc is not None and tc < thread_threshold:
                        print(f'[{account_name}] LOADING (tc={tc}), waiting...')
                        self.report_status(account_name, pkg, 'loading', tc=tc)
                        continue

                    if kicked:
                        print(f'[{account_name}] KICKED ({kicked}), rejoining...')
                        self.report_status(account_name, pkg, 'kicked', tc=tc, kicked=kicked)
                        link = self._get_join_link(account_name)
                        if link:
                            print(f'[{account_name}] → JOINING: {link[:80]}...')
                            self.start_join_intent(pkg, link)
                            self.report_status(account_name, pkg, 'rejoining')
                            self._last_rejoin[pkg] = now
                        else:
                            print(f'[{account_name}] → NO JOIN LINK!')
                        continue

                    if tc is not None and tc >= thread_threshold:
                        print(f'[{account_name}] IN-GAME (tc={tc})')
                        self.report_status(account_name, pkg, 'in_game', tc=tc)
                        self._last_rejoin[pkg] = now
                    elif tc is not None:
                        print(f'[{account_name}] HOME SCREEN (tc={tc})')
                        self.report_status(account_name, pkg, 'monitoring', tc=tc)
                        last = self._last_rejoin.get(pkg, 0)
                        if now - last >= 60:
                            link = self._get_join_link(account_name)
                            if link:
                                print(f'[{account_name}] → JOINING: {link[:80]}...')
                                self.start_join_intent(pkg, link)
                                self.report_status(account_name, pkg, 'rejoining')
                                self._last_rejoin[pkg] = now
                            if tc < 10:
                                self.dismiss_dialogs()
                    else:
                        print(f'[{account_name}] RUNNING (tc=unknown)')
                        self.report_status(account_name, pkg, 'monitoring', tc=None)
                        last = self._last_rejoin.get(pkg, 0)
                        if now - last >= 60:
                            link = self._get_join_link(account_name)
                            if link:
                                print(f'[{account_name}] → JOINING (fallback): {link[:80]}...')
                                self.start_join_intent(pkg, link)
                                self.report_status(account_name, pkg, 'rejoining')
                                self._last_rejoin[pkg] = now

                    last_rejoin = self._last_rejoin.get(pkg, 0)
                    if rejoin_interval > 0 and (now - last_rejoin) >= rejoin_interval:
                        print(f'[{account_name}] PERIODIC REJOIN ({int(rejoin_interval//60)} min)')
                        link = self._get_join_link(account_name)
                        if link:
                            self.start_join_intent(pkg, link)
                            self._last_rejoin[pkg] = now

                    self._check_mailbox_commands(account_name)

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                print('\n[MONITOR] Stopped by user')
                self.running = False
                break
            except Exception as e:
                print(f'[MONITOR] Error: {e}')
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _get_join_link(self, account_name=None):
        config = self.settings or {}
        servers = config.get('servers', [])
        account_settings = config.get('account_settings', {})
        server = config.get('current_server', {})
        if account_name and servers:
            pkg = None
            for p, info in self.account_map.items():
                if info == account_name:
                    pkg = p
                    break
            if pkg:
                settings_key = f'{self.device_id}:{pkg}'
                acct = account_settings.get(settings_key, account_settings.get(pkg, {}))
                target_id = acct.get('server_id', '')
                if target_id:
                    for s in servers:
                        if s.get('id') == target_id:
                            server = s
                            break
        place_id = server.get('place_id', '')
        server_code = server.get('server_code', '')
        link = server.get('link', '')
        if link:
            return link
        if not place_id:
            if servers:
                for s in servers:
                    if s.get('server_code'):
                        server = s
                        place_id = s.get('place_id', '')
                        server_code = s.get('server_code', '')
                        break
                if not place_id:
                    server = servers[0]
                    place_id = server.get('place_id', '')
                    server_code = server.get('server_code', '')
            if not place_id:
                return None
        if server_code:
            import urllib.parse
            return f'roblox://experiences/start?placeId={place_id}&linkCode={urllib.parse.quote(server_code)}'
        return f'roblox://placeId={place_id}'

    def _check_mailbox_commands(self, account_name):
        result = self.get_commands(account_name)
        if not result or not result.get('commands'):
            return
        for cmd in result['commands']:
            cmd_id = cmd.get('id', '')
            cmd_type = cmd.get('type', '')
            print(f'[{account_name}] Executing: {cmd_type} ({cmd_id})')
            try:
                if cmd_type == 'join':
                    self._execute_join_command(account_name, cmd)
                elif cmd_type == 'send_mail':
                    self._execute_mailbox_send(account_name, cmd)
                elif cmd_type == 'send_gift':
                    self._execute_gift(account_name, cmd)
                elif cmd_type == 'reset_app':
                    self._execute_reset_command(account_name, cmd)
                elif cmd_type == 'delta_key':
                    self._execute_delta_key_command(account_name, cmd)
                elif cmd_type == 'detect_autoexec':
                    self._execute_detect_autoexec(account_name, cmd)
                self.complete_command(cmd_id, True, 'Executed')
            except Exception as e:
                self.complete_command(cmd_id, False, str(e))

    def _execute_join_command(self, account_name, cmd):
        package = cmd.get('package', '')
        link = cmd.get('link', '')
        if not package or not link:
            print(f'[{account_name}] Join command missing package or link')
            return
        print(f'[{account_name}] JOIN → {link[:80]}...')
        self.start_join_intent(package, link)
        self.report_status(account_name, package, 'rejoining')

    def _execute_mailbox_send(self, account_name, cmd):
        target_id = cmd.get('target_id', 0)
        items = cmd.get('items', [])
        if not target_id or not items:
            return
        print(f'[{account_name}] Sending {len(items)} items to {cmd.get("target", "?")} (ID: {target_id})')

    def _execute_gift(self, account_name, cmd):
        target_id = cmd.get('target_id', 0)
        item_id = cmd.get('item_id', '')
        if not target_id or not item_id:
            return
        print(f'[{account_name}] Gifting {item_id} to {cmd.get("target", "?")} (ID: {target_id})')

    def _execute_reset_command(self, account_name, cmd):
        package = cmd.get('package', '')
        if not package:
            print(f'[{account_name}] Reset command missing package')
            return
        success = self.reset_app(package)
        if success:
            print(f'[{account_name}] App reset complete, waiting before rejoin...')
            time.sleep(3)
            link = self._get_join_link(account_name)
            if link:
                self.start_join_intent(package, link)
                self.report_status(account_name, package, 'rejoining')
                print(f'[{account_name}] Rejoin after reset → {link[:80]}...')
        else:
            print(f'[{account_name}] App reset failed')

    def _execute_delta_key_command(self, account_name, cmd):
        package = cmd.get('package', '')
        if not package:
            print(f'[{account_name}] Delta key command missing package')
            return
        print(f'[{account_name}] Getting Delta key for {package}...')
        key, err = self.delta_auto_get_key(package)
        if key:
            print(f'[{account_name}] Delta key obtained: {key[:20]}...')
            self.http_post(f'/api/remote/delta-key/{self.device_id}/{package}/report', {
                'success': True,
                'key_preview': key[:12] + '...',
                'message': 'Key injected'
            })
        else:
            print(f'[{account_name}] Delta key failed: {err}')
            self.http_post(f'/api/remote/delta-key/{self.device_id}/{package}/report', {
                'success': False,
                'key_preview': '',
                'message': str(err)
            })

    def _execute_detect_autoexec(self, account_name, cmd):
        """Detect auto-execute folders on this cloudphone device."""
        package = cmd.get('package', '')
        scan_id = cmd.get('scan_id', '')
        print(f'[{account_name}] Detecting autoexec folders (pkg={package or "all"}, scan={scan_id})...')

        # Build candidate paths
        candidates = [
            '/sdcard/Delta/Autoexecute',
            '/sdcard/Delta/autoexec',
            '/sdcard/Delta/AutoExecute',
            '/storage/emulated/0/Delta/Autoexecute',
            '/storage/emulated/0/Delta/autoexec',
        ]
        pkgs = [package] if package else self.packages
        for pkg in pkgs:
            candidates += [
                f'/data/data/{pkg}/files/Delta/Autoexecute',
                f'/data/data/{pkg}/files/Delta/autoexec',
                f'/data/data/{pkg}/files/delta/autoexecute',
                f'/data/data/{pkg}/files/delta/autoexec',
                f'/sdcard/Android/data/{pkg}/files/Delta/Autoexecute',
                f'/sdcard/Android/data/{pkg}/files/Delta/autoexec',
                f'/sdcard/Android/data/{pkg}/files/delta/autoexecute',
                f'/sdcard/Android/data/{pkg}/files/delta/autoexec',
                f'/storage/emulated/0/Android/data/{pkg}/files/Delta/Autoexecute',
                f'/storage/emulated/0/Android/data/{pkg}/files/Delta/autoexec',
                f'/storage/emulated/0/Android/data/{pkg}/files/delta/autoexecute',
                f'/storage/emulated/0/Android/data/{pkg}/files/delta/autoexec',
            ]

        found = []
        for path in candidates:
            code, out = self.su_cmd(f'test -d "{path}" && echo EXISTS || echo MISSING')
            if code != 0 or 'EXISTS' not in (out or ''):
                continue
            _, count_out = self.su_cmd(f'ls -1 "{path}" 2>/dev/null | wc -l')
            file_count = 0
            try:
                file_count = int((count_out or '0').strip())
            except (ValueError, TypeError):
                pass
            _, ls_out = self.su_cmd(f'ls -1 "{path}" 2>/dev/null | head -20')
            file_names = [f.strip() for f in (ls_out or '').split('\n') if f.strip()][:20]
            _, w_out = self.su_cmd(f'test -w "{path}" && echo W_OK || echo W_NO')
            writable = 'W_OK' in (w_out or '')
            found.append({
                'path': path,
                'files': file_count,
                'file_names': file_names,
                'writable': writable,
            })

        print(f'[{account_name}] Found {len(found)} autoexec folders')
        self.http_post('/api/remote/autoexec/report', {
            'device_id': self.device_id,
            'scan_id': scan_id,
            'package': package,
            'found': found,
        })


CONFIG_PATH = '/sdcard/Download/dashboard_config.json'

def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def main():
    saved_config = load_config()
    default_url = saved_config.get('domain', '')

    parser = argparse.ArgumentParser(description='Dashboard Roblox - Remote Monitor (Root)')
    parser.add_argument('--url', default=default_url, help='PC Dashboard URL')
    parser.add_argument('--interval', type=int, default=5, help='Poll interval in seconds (default: 5)')
    args = parser.parse_args()

    if not args.url:
        print('[ERROR] Dashboard URL required!')
        print(f'[INFO] Set domain in {CONFIG_PATH}')
        print('[INFO] Or run: python remote_monitor.py --url https://your-domain.com')
        return

    monitor = RootMonitor(
        dashboard_url=args.url,
        poll_interval=args.interval
    )
    monitor.run()


if __name__ == '__main__':
    main()
