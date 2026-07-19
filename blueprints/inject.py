import os, json, time, tempfile, subprocess

from flask import Blueprint, request, jsonify

from models import accounts, settings, log_activity, log_account, save_data, decrypt_cookie, make_script_for
from services.adb import find_adb, get_serial, adb_connect, adb_cmd

inject_bp = Blueprint('inject', __name__)

@inject_bp.route('/api/accounts/<acc_id>/inject', methods=['POST'])
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

        auth_xml = '<?xml version="1.0" encoding="utf-8"?><map><string name="ROBLOSECURITY">' + cookie + '</string></map>'
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

@inject_bp.route('/api/accounts/<acc_id>/push-script', methods=['POST'])
def push_script(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    name = acc.get('name', 'Account')
    package = acc.get('package_name', '')
    url = settings.get('dashboard_url', 'http://localhost:5000')
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
