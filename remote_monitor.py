#!/usr/bin/env python3
"""
Dashboard Roblox - Remote Monitor Script
Jalankan di Termux (Redfinger) untuk auto-rejoin via ADB.
Connect ke PC dashboard via HTTP.

Cara pakai:
    python remote_monitor.py --url https://dashboard.aavpanel.my.id --serial 127.0.0.1:5000
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


class ADBMonitor:
    def __init__(self, serial, dashboard_url, poll_interval=5):
        self.serial = serial
        self.dashboard_url = dashboard_url.rstrip('/')
        self.poll_interval = poll_interval
        self.adb = self._find_adb()
        self.packages = []
        self.account_map = {}
        self.running = False
        self.settings = {}

    def _find_adb(self):
        candidates = [
            '/data/data/com.termux/files/usr/bin/adb',
            os.path.expanduser('~/.termux/bin/adb'),
            'adb',
        ]
        for c in candidates:
            try:
                r = subprocess.run([c, '--version'], capture_output=True, timeout=5)
                if r.returncode == 0:
                    print(f'[ADB] Found: {c}')
                    return c
            except:
                pass
        print('[ADB] ERROR: adb not found!')
        return None

    def adb_cmd(self, args, timeout=15):
        if not self.adb:
            return None, ''
        cmd = [self.adb, '-s', self.serial] + args
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout.strip() or r.stderr.strip()
        except subprocess.TimeoutExpired:
            return None, 'timeout'
        except Exception as e:
            return None, str(e)

    def adb_connect(self):
        if not self.adb:
            return False
        try:
            r = subprocess.run([self.adb, 'connect', self.serial],
                capture_output=True, text=True, timeout=10)
            ok = 'connected' in r.stdout.lower() or 'already connected' in r.stdout.lower()
            if not ok:
                print(f'[ADB] Connect failed: {r.stdout.strip()} {r.stderr.strip()}')
            return ok
        except Exception as e:
            print(f'[ADB] Connect error: {e}')
            return False

    def check_roblox(self, package='com.roblox.client'):
        code, out = self.adb_cmd(['shell', 'pidof', package])
        if code == 0 and out:
            pids = out.split()
            return bool(pids and pids[0].isdigit())
        return False

    def get_thread_count(self, package='com.roblox.client'):
        code, out = self.adb_cmd(['shell', 'pidof', package])
        if code != 0 or not out:
            return None
        pid = out.split()[0]
        if not pid.isdigit():
            return None
        code2, out2 = self.adb_cmd(['shell', 'cat', f'/proc/{pid}/status'])
        if code2 == 0:
            for line in out2.split('\n'):
                if 'Threads' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except:
                            pass
        return None

    def force_stop(self, package='com.roblox.client'):
        self.adb_cmd(['shell', 'am', 'force-stop', package])

    def start_join_intent(self, package, link):
        self.force_stop(package)
        time.sleep(3)
        code, out = self.adb_cmd([
            'shell', 'am', 'start', '-a', 'android.intent.action.VIEW',
            '-d', f"'{link}'", '-p', package
        ])
        return code == 0

    def detect_kicked(self, package='com.roblox.client'):
        code, out = self.adb_cmd(['shell', 'pidof', package])
        if code != 0 or not out:
            return None
        code2, out2 = self.adb_cmd(['shell', 'dumpsys', 'window', 'windows'])
        if code2 == 0:
            for line in out2.split('\n'):
                if 'mIsFloatingLayer=true' in line and package in line:
                    return 'floating_dialog'
                if package in line.lower() and any(k in line.lower() for k in
                    ['disconnected', 'kicked', 'reconnecting', 'connection lost']):
                    return 'kicked_dialog'
        return None

    def dismiss_dialogs(self):
        for _ in range(3):
            self.adb_cmd(['shell', 'input', 'keyevent', 'KEYCODE_BACK'])
            time.sleep(0.2)
        for xy in [('540', '960'), ('540', '800')]:
            self.adb_cmd(['shell', 'input', 'tap', xy[0], xy[1]])
            time.sleep(0.2)

    def discover_packages(self):
        code, out = self.adb_cmd(['shell', 'pm', 'list', 'packages'])
        if code == 0 and out:
            found = []
            for line in out.split('\n'):
                pkg = line.replace('package:', '').strip()
                if 'roblox' in pkg.lower():
                    found.append(pkg)
            return sorted(found)
        return []

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
            'serial': self.serial,
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
        print(f'[MONITOR] Starting remote monitor...')
        print(f'[MONITOR] Dashboard: {self.dashboard_url}')
        print(f'[MONITOR] ADB Serial: {self.serial}')

        if not self.adb:
            print('[MONITOR] ERROR: ADB not found')
            return

        if not self.adb_connect():
            print('[MONITOR] ERROR: ADB connect failed')
            return

        self.packages = self.discover_packages()
        if not self.packages:
            print('[MONITOR] ERROR: No Roblox packages found')
            return
        print(f'[MONITOR] Found packages: {self.packages}')

        if not self.register():
            print('[MONITOR] ERROR: Failed to register to dashboard')
            return

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
                        print(f'[{account_name}] Roblox not running ({pkg}), rejoining...')
                        link = self._get_join_link()
                        if link:
                            self.start_join_intent(pkg, link)
                            self.report_status(account_name, pkg, 'rejoining')
                        continue

                    tc = self.get_thread_count(pkg)
                    kicked = self.detect_kicked(pkg)

                    if kicked:
                        print(f'[{account_name}] Kicked detected ({kicked}), rejoining...')
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
                            print(f'[{account_name}] Low thread count ({tc}), may need rejoin')
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
            print(f'[{account_name}] Executing command: {cmd_type} ({cmd_id})')
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
    parser = argparse.ArgumentParser(description='Dashboard Roblox - Remote Monitor')
    parser.add_argument('--url', required=True, help='PC Dashboard URL (e.g. https://dashboard.aavpanel.my.id)')
    parser.add_argument('--serial', default='127.0.0.1:5000', help='ADB serial (default: 127.0.0.1:5000)')
    parser.add_argument('--interval', type=int, default=5, help='Poll interval in seconds (default: 5)')
    args = parser.parse_args()

    monitor = ADBMonitor(
        serial=args.serial,
        dashboard_url=args.url,
        poll_interval=args.interval
    )
    monitor.run()


if __name__ == '__main__':
    main()
