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
        code, out = self.su_cmd(
            f"am start -a android.intent.action.VIEW -d '{link}' -p {package}"
        )
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

    def get_screen_size(self):
        code, out = self.su_cmd('wm size')
        if code == 0:
            m = re.search(r'(\d+)x(\d+)', out)
            if m:
                return int(m.group(1)), int(m.group(2))
        return 1080, 1920

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
        data = {
            'serial': 'root',
            'packages': [{'idx': i, 'name': pkg} for i, pkg in enumerate(self.packages)]
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

        print('[MONITOR] Extracting cookies from device...')
        self.extract_all_cookies()

        self.running = True
        print(f'[MONITOR] Monitor started! Polling every {self.poll_interval}s...')

        while self.running:
            try:
                self.get_config()
                rejoin_interval = self.settings.get('rejoin_interval', 2400)
                thread_threshold = self.settings.get('thread_threshold', 80)

                for pkg in self.packages:
                    if not self.running:
                        break

                    account_name = self.account_map.get(pkg, f'Unknown-{pkg}')

                    running = self.check_roblox(pkg)
                    if not running:
                        self.report_status(account_name, pkg, 'disconnected')
                        print(f'[{account_name}] Not running ({pkg}), rejoining...')
                        link = self._get_join_link()
                        if link:
                            self.start_join_intent(pkg, link)
                            self.report_status(account_name, pkg, 'rejoining')
                        continue

                    tc = self.get_thread_count(pkg)
                    kicked = self.detect_kicked(pkg)

                    if kicked:
                        print(f'[{account_name}] Kicked ({kicked}), rejoining...')
                        self.report_status(account_name, pkg, 'kicked', tc=tc, kicked=kicked)
                        link = self._get_join_link()
                        if link:
                            self.start_join_intent(pkg, link)
                            self.report_status(account_name, pkg, 'rejoining')
                        continue

                    if tc is not None and tc >= thread_threshold:
                        self.report_status(account_name, pkg, 'in_game', tc=tc)
                    elif tc is not None:
                        self.report_status(account_name, pkg, 'monitoring', tc=tc)
                        if tc < 10:
                            print(f'[{account_name}] Low threads ({tc}), dismissing dialogs')
                            self.dismiss_dialogs()
                    else:
                        self.report_status(account_name, pkg, 'monitoring', tc=None)

                    self._check_mailbox_commands(account_name)

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                print('\n[MONITOR] Stopped by user')
                self.running = False
                break
            except Exception as e:
                print(f'[MONITOR] Error: {e}')
                time.sleep(5)

    def _get_join_link(self):
        config = self.settings or {}
        server = config.get('current_server', {})
        place_id = server.get('place_id', '')
        server_code = server.get('server_code', '')
        if not place_id:
            return None
        if server_code:
            import urllib.parse
            return f'https://www.roblox.com/share?code={urllib.parse.quote(server_code)}&type=Server'
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
                if cmd_type == 'send_mail':
                    self._execute_mailbox_send(account_name, cmd)
                elif cmd_type == 'send_gift':
                    self._execute_gift(account_name, cmd)
                self.complete_command(cmd_id, True, 'Executed')
            except Exception as e:
                self.complete_command(cmd_id, False, str(e))

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


def main():
    parser = argparse.ArgumentParser(description='Dashboard Roblox - Remote Monitor (Root)')
    parser.add_argument('--url', required=True, help='PC Dashboard URL (e.g. https://dashboard.aavpanel.my.id)')
    parser.add_argument('--interval', type=int, default=5, help='Poll interval in seconds (default: 5)')
    args = parser.parse_args()

    monitor = RootMonitor(
        dashboard_url=args.url,
        poll_interval=args.interval
    )
    monitor.run()


if __name__ == '__main__':
    main()
