import os, json, time, base64

from config import DATA_FILE, PACKAGE_MAP, IS_TERMUX
from core.state import (
    accounts, servers, settings, schedules, schedule_history,
    activity_log, acc_logs, inventory_data, harvested_fruits_data,
    _data_lock
)


def encrypt_cookie(cookie):
    if not cookie:
        return cookie
    return base64.b64encode(cookie.encode()).decode()


def decrypt_cookie(cookie):
    if not cookie:
        return cookie
    try:
        return base64.b64decode(cookie.encode()).decode()
    except:
        return cookie


def get_package_name(instance_idx):
    pkgs = settings.get('active_packages', PACKAGE_MAP)
    return pkgs.get(instance_idx, 'com.roblox.client')


def _try_load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict) and (data.get('accounts') or data.get('servers')):
                return data
    except:
        pass
    return None


def load_data():
    global accounts, servers
    data = _try_load_json(DATA_FILE)
    if not data:
        print('[WARN] data.json kosong atau corrupt, mencoba restore dari backup...')
        data = _try_load_json(DATA_FILE + '.bak')
    if not data:
        print('[WARN] data.json.bak juga corrupt, mencoba dari .bak2...')
        data = _try_load_json(DATA_FILE + '.bak2')
    if data:
        accounts.clear()
        for acc in data.get('accounts', []):
            if not acc.get('server_ids') and acc.get('server_id'):
                acc['server_ids'] = [acc['server_id']]
            accounts.append(acc)
        servers.clear()
        servers.extend(data.get('servers', []))
        settings.update(data.get('settings', {}))
        ri = settings.get('rejoin_interval', 2400)
        if ri < 60:
            settings['rejoin_interval'] = ri * 60
        saved_logs = data.get('account_logs', {})
        if saved_logs:
            acc_logs.update(saved_logs)
        saved_hf = data.get('harvested_fruits_data', {})
        if saved_hf:
            harvested_fruits_data.update(saved_hf)
        schedules.clear()
        schedules.extend(data.get('schedules', []))
        schedule_history.clear()
        schedule_history.extend(data.get('schedule_history', []))
        print(f'[OK] Loaded {len(accounts)} accounts, {len(servers)} servers, {len(schedules)} schedules')
    else:
        print('[ERROR] Tidak ada data yang bisa di-load!')


def save_data():
    with _data_lock:
        import shutil
        if os.path.exists(DATA_FILE):
            if os.path.exists(DATA_FILE + '.bak'):
                try:
                    shutil.copy2(DATA_FILE + '.bak', DATA_FILE + '.bak2')
                except:
                    pass
            try:
                shutil.copy2(DATA_FILE, DATA_FILE + '.bak')
            except:
                pass
        snap_accounts = list(accounts)
        snap_servers = list(servers)
        snap_settings = dict(settings)
        snap_logs = {k: v[:100] for k, v in acc_logs.items()}
        snap_hf = {k: v for k, v in harvested_fruits_data.items()}
        snap_schedules = list(schedules)
        snap_history = list(schedule_history[-500:])
        tmp = DATA_FILE + '.tmp'
        try:
            with open(tmp, 'w') as f:
                json.dump({
                    'accounts': snap_accounts,
                    'servers': snap_servers,
                    'settings': snap_settings,
                    'account_logs': snap_logs,
                    'harvested_fruits_data': snap_hf,
                    'schedules': snap_schedules,
                    'schedule_history': snap_history
                }, f, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception as e:
            print(f'[ERROR] save_data failed: {e}')
            try:
                os.remove(tmp)
            except:
                pass


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


def discover_roblox_packages_on_start(serial=None):
    if not IS_TERMUX:
        return
    try:
        from services.adb import find_adb, adb_cmd, adb_connect
        if serial:
            adb_connect(serial)
        r = adb_cmd(['shell', 'pm', 'list', 'packages'], serial)
        if r and r[0] == 0 and r[1]:
            found = []
            for line in r[1].split('\n'):
                pkg = line.replace('package:', '').strip()
                if 'roblox' in pkg.lower():
                    found.append(pkg)
            found.sort()
            if found:
                pkgs = dict(PACKAGE_MAP)
                for i, pkg in enumerate(found[:5]):
                    pkgs[i] = pkg
                settings['active_packages'] = pkgs
                print(f'[TERMUX] Discovered {len(found)} Roblox packages: {found}')
    except Exception as e:
        print(f'[TERMUX] Package discovery failed: {e}')
