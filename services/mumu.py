import os, json, time, subprocess, threading, re

from models import settings, accounts, servers, _data_lock, log_activity, log_account, save_data, get_package_name
from services.adb import find_adb, get_serial, adb_connect, adb_force_stop_roblox, adb_cmd, adb_dismiss_dialogs, adb_check_join_failed, adb_check_roblox, auto_push_script_to_vm
from services.webhook import send_webhook
from services.roblox import build_join_link
from config import IS_TERMUX

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

def find_mumu_vms_dir():
    candidates = ['G:\\MuMuPlayerGlobal\\vms', 'D:\\MuMuPlayerGlobal\\vms',
        os.path.expanduser('~\\MuMuPlayerGlobal\\vms'),
        'C:\\Program Files\\MuMuVMMvbox\\vms',
        'C:\\Program Files (x86)\\MuMuVMMvbox\\vms']
    for dr in ['G:', 'D:', 'E:', 'F:', 'C:']:
        p = os.path.join(dr, 'MuMuPlayerGlobal', 'vms')
        if os.path.isdir(p):
            candidates.insert(0, p)
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]

def load_vm_display_names():
    names = {}
    base = find_mumu_vms_dir()
    if not os.path.isdir(base):
        return names
    for entry in os.listdir(base):
        m = re.match(r'MuMuPlayerGlobal-12\.0-(\d+)$', entry)
        if not m:
            continue
        i = m.group(1)
        path = os.path.join(base, entry, 'configs', 'extra_config.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                dn = data.get('playerName', '')
                if dn:
                    names[entry] = dn
        except:
            pass
    return names

def ensure_vm_running(serial, instance):
    if IS_TERMUX:
        ok, msg = adb_connect(serial)
        return ok
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
            if settings.get('auto_push_script', True):
                try:
                    for a in accounts:
                        if a.get('mumu_instance') == instance and a.get('cookie'):
                            auto_push_script_to_vm(a, serial)
                except Exception as e:
                    log_activity(f'Auto-push script gagal ({vm_name}): {e}', 'warning')
            return True
        code2, out2 = mumu_vm_cmd(['list', 'runningvms'])
        if code2 == 0 and vm_name in out2:
            log_activity(f'[AutoRestart] VM {vm_name} running (waiting ADB)')
    log_activity(f'[AutoRestart] VM {vm_name} start timed out', 'error')
    send_webhook(f'🔴 VM Auto-Restart Failed: {vm_name}', f'Instance {instance} failed to start after 2 minutes', 0xff4444)
    return False

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
    code, _ = adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'"], serial)
    if code != 0:
        return False
    for attempt in range(3):
        got_valid = False
        for _ in range(4):
            time.sleep(5)
            failed = adb_check_join_failed(serial)
            if failed is True:
                log_account(acc.get('id', ''), acc.get('name', '?'), f'join failed (kick/disconnect detected via ui dump), retry #{attempt+1}')
                adb_dismiss_dialogs(serial)
                time.sleep(2)
                break
            elif failed is False:
                got_valid = True
                continue
            else:
                continue
        else:
            if not got_valid:
                log_account(acc.get('id', ''), acc.get('name', '?'), f'join: all ADB checks failed (no valid reading), retry #{attempt+1}')
                adb_dismiss_dialogs(serial)
                time.sleep(2)
                if attempt < 2:
                    adb_force_stop_roblox(serial)
                    time.sleep(3)
                    code, _ = adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'"], serial)
                    if code != 0:
                        return False
                continue
            adb_dismiss_dialogs(serial)
            time.sleep(2)
            adb_dismiss_dialogs(serial)
            now = time.time()
            acc['last_join_time'] = now
            acc['status'] = 'connected'
            acc['last_joined'] = time.strftime('%H:%M:%S')
            save_data()
            return True
        if attempt < 2:
            adb_force_stop_roblox(serial)
            time.sleep(3)
            code, _ = adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{link}'"], serial)
            if code != 0:
                return False
    log_account(acc.get('id', ''), acc.get('name', '?'), 'join failed after 3 retries')
    return False

def launch_mumu(acc, link, sv, acc_id=None):
    from models import _join_threads, _join_threads_lock
    try:
        _launch_mumu(acc, link, sv)
    finally:
        if acc_id:
            with _join_threads_lock:
                _join_threads.discard(acc_id)

def _launch_mumu(acc, link, sv):
    from services.delta import delta_refresh_key_for_acc
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
            code, out = adb_cmd(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', f"'{url}'"], serial)
            for _ in range(12):
                if adb_check_roblox(serial):
                    break
                time.sleep(2)
            adb_dismiss_dialogs(serial)
            if code != 0 and code is not None:
                log_account(acc['id'], acc['name'], f'ADB: {out}', 'warning')
            if not adb_check_roblox(serial):
                log_account(acc['id'], acc['name'], 'Roblox tidak terdeteksi setelah intent, retry...')
                continue
            acc['status'] = 'connected'
            acc['last_joined'] = time.strftime('%H:%M:%S')
            acc['last_join_time'] = time.time()
            log_account(acc['id'], acc['name'], f'Join via {serial} berhasil')
            save_data()
            if settings.get('delta_auto_key', False):
                time.sleep(5)
                try:
                    delta_refresh_key_for_acc(acc)
                except:
                    pass
            return
        except Exception as e:
            log_account(acc['id'], acc['name'], f'Error: {str(e)}', 'error')
            acc['status'] = 'error'
    acc['active'] = False
    acc['status'] = 'error'
    save_data()


