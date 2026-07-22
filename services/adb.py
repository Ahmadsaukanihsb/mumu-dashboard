import os, time, subprocess, threading, re

from models import settings, save_data
from models import _serial_locks, _adb_global_lock
from config import IS_TERMUX, IS_ARM

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
    if IS_TERMUX:
        candidates = [
            '/data/data/com.termux/files/usr/bin/adb',
            os.path.expanduser('~/.termux/bin/adb'),
            os.path.expanduser('$PREFIX/bin/adb'),
            'adb',
        ] + candidates
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
    serials = settings.get('mumu_serials', [])
    if not serials or instance_idx < 0 or instance_idx >= len(serials):
        return None
    s = serials[instance_idx]
    if not s or not s.strip():
        return None
    return s.strip()

def _serial_lock(serial):
    with _adb_global_lock:
        if serial not in _serial_locks:
            _serial_locks[serial] = threading.Lock()
    return _serial_locks[serial]

def _adb_run(cmd, serial=None, **kwargs):
    if serial:
        lock = _serial_lock(serial)
        lock.acquire()
    else:
        lock = None
    try:
        kwargs.setdefault('capture_output', True)
        kwargs.setdefault('timeout', 10)
        r = subprocess.run(cmd, **kwargs)
        return r
    finally:
        if lock:
            lock.release()

def adb_cmd(args, serial=None):
    adb = find_adb()
    if not adb:
        return None, 'ADB not found'
    if serial:
        full_cmd = [adb, '-s', serial] + args
        lock = _serial_lock(serial)
    else:
        full_cmd = [adb] + args
        lock = None
    if lock:
        lock.acquire()
    try:
        r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip() or r.stderr.strip()
    except subprocess.TimeoutExpired:
        return None, 'ADB command timed out'
    except Exception as e:
        return None, str(e)
    finally:
        if lock:
            lock.release()

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

def adb_check_roblox(serial, package='com.roblox.client'):
    adb = find_adb()
    if not adb: return False
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'pidof', package],
            serial=serial, capture_output=True, text=True, timeout=10)
        pid = r.stdout.strip()
        return bool(pid and pid.split()[0].isdigit())
    except Exception as e:
        print(f'[ADB] check_roblox error ({serial}, {package}): {e}')
        return False

def adb_get_thread_count(serial, package='com.roblox.client'):
    adb = find_adb()
    if not adb: return None
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'pidof', package],
            serial=serial, capture_output=True, text=True, timeout=10)
        pid_str = r.stdout.strip()
        if not pid_str:
            return None
        pid = pid_str.split()[0]
        if not pid.isdigit():
            return None
        r = _adb_run([adb, '-s', serial, 'shell', 'cat', f'/proc/{pid}/status'],
            serial=serial, capture_output=True, text=True, timeout=10)
        for line in r.stdout.split('\n'):
            if 'Threads' in line:
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1])
        return None
    except:
        return None

def adb_force_stop_roblox(serial, package='com.roblox.client'):
    adb = find_adb()
    if not adb: return
    try:
        _adb_run([adb, '-s', serial, 'shell', 'am', 'force-stop', package],
            serial=serial, capture_output=True, timeout=10)
    except:
        pass

def adb_dismiss_dialogs(serial):
    adb = find_adb()
    if not adb: return
    try:
        for _ in range(3):
            _adb_run([adb, '-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_BACK'],
                serial=serial, capture_output=True, timeout=3)
            time.sleep(0.2)
        for xy in [('540', '960'), ('540', '800')]:
            _adb_run([adb, '-s', serial, 'shell', 'input', 'tap', xy[0], xy[1]],
                serial=serial, capture_output=True, timeout=3)
            time.sleep(0.2)
    except:
        pass

def adb_detect_kicked_dialog(serial, package='com.roblox.client'):
    adb = find_adb()
    if not adb: return None
    pid = None
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'pidof', package],
            serial=serial, capture_output=True, text=True, timeout=5)
        pid = r.stdout.strip()
    except Exception as e:
        print(f'[KICKED] pidof error ({serial}, {package}): {e}')
    if not pid:
        return None
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'dumpsys', 'window', 'windows'],
            serial=serial, capture_output=True, text=True, timeout=10)
        out = r.stdout.lower()
        if package not in out:
            return None
        for line in out.split('\n'):
            if 'mIsFloatingLayer=true' in line and package in line:
                return '1a_floating'
        for line in out.split('\n'):
            if package in line.lower() and any(k in line.lower() for k in
                ['disconnected', 'kicked', 'reconnecting', 'you were kicked',
                 'you have been kicked', 'connection lost']):
                return '1b_title:' + line.strip()[:60]
    except Exception as e:
        print(f'[KICKED] dumpsys error ({serial}, {package}): {e}')

    for compressed in [True, False]:
        try:
            cmd = ['uiautomator', 'dump']
            if compressed:
                cmd.append('--compressed')
            cmd.append('/data/local/tmp/ui.xml')
            _adb_run([adb, '-s', serial, 'shell'] + cmd, serial=serial, capture_output=True, timeout=15)
            r = _adb_run([adb, '-s', serial, 'shell', 'cat', '/data/local/tmp/ui.xml 2>/dev/null || echo empty'],
                serial=serial, capture_output=True, text=True, timeout=10)
            _adb_run([adb, '-s', serial, 'shell', 'rm', '-f', '/data/local/tmp/ui.xml'], serial=serial, capture_output=True, timeout=5)
            text = r.stdout.lower()
            kick_words = ['kicked', 'you were kicked', 'you have been kicked', 'removed from the game',
                          'your save data', 'disconnected', 'please rejoin', 'connection lost',
                          'reconnecting', 'an error occurred', 'failed to connect']
            if any(k in text for k in kick_words):
                return '2_uiautomator'
        except Exception as e:
            print(f'[KICKED] uiautomator error ({serial}): {e}')
    return None

def _adb_dumpsys(serial, args, timeout=10):
    adb = find_adb()
    if not adb: return None
    try:
        r = _adb_run([adb, '-s', serial.strip()] + args,
            serial=serial.strip(), capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except:
        return None

def _adb_get_focused(serial):
    out = _adb_dumpsys(serial, ['shell', 'dumpsys', 'window'])
    if not out:
        return None
    focus = None
    for line in out.split('\n'):
        if 'mCurrentFocus=' in line:
            val = line.split('mCurrentFocus=', 1)[1].strip()
            if val and val != 'null':
                focus = val.lower()
    return focus

def adb_check_in_game(serial, package='com.roblox.client'):
    if not find_adb(): return None
    try:
        focus = _adb_get_focused(serial)
        if focus is None:
            return None
        if package not in focus:
            return None
        if any(x in focus for x in ['dialog', 'alert', 'popup', 'notification']):
            pass
        rblx_windows = 0
        out = _adb_dumpsys(serial, ['shell', 'dumpsys', 'window', 'windows'])
        if out:
            for line in out.split('\n'):
                if line.startswith('  Window #') and package in line:
                    if 'mIsFloatingLayer=true' not in line:
                        rblx_windows += 1
        if rblx_windows >= 2:
            return True
        if rblx_windows == 0:
            return None
        return None
    except:
        return None

def adb_screenshot(serial):
    adb = find_adb()
    if not adb: return None
    try:
        r = _adb_run([adb, '-s', serial.strip(), 'exec-out', 'screencap', '-p'],
            serial=serial.strip(), capture_output=True, timeout=15)
        if r.returncode == 0 and len(r.stdout) > 100:
            return r.stdout
    except:
        pass
    return None

def adb_check_join_failed(serial, package='com.roblox.client'):
    adb = find_adb()
    if not adb: return None
    try:
        _adb_run([adb, '-s', serial.strip(), 'shell', 'uiautomator', 'dump', '--compressed', '/data/local/tmp/join.xml'],
            serial=serial.strip(), capture_output=True, timeout=10)
        r = _adb_run([adb, '-s', serial.strip(), 'shell', 'cat', '/data/local/tmp/join.xml 2>/dev/null || echo empty'],
            serial=serial.strip(), capture_output=True, text=True, timeout=5)
        _adb_run([adb, '-s', serial.strip(), 'shell', 'rm', '-f', '/data/local/tmp/join.xml'], serial=serial.strip(), capture_output=True, timeout=3)
        text = r.stdout.lower()
        fail_words = ['kicked', 'you were kicked', 'you have been kicked', 'removed from the game',
                      'your save data', 'disconnected', 'connection lost', 'reconnecting', 'please rejoin']
        if any(k in text for k in fail_words):
            return True
        return False
    except:
        return None

def adb_get_pid(serial, package='com.roblox.client'):
    code, out = adb_cmd(['shell', 'pidof', package], serial)
    if code == 0 and out:
        pid = out.split()[0]
        if pid.isdigit():
            return pid
    return None

def adb_check_in_foreground(serial, package='com.roblox.client'):
    code, out = adb_cmd(['shell', 'dumpsys', 'activity', 'activities'], serial)
    if code == 0 and out:
        for keyword in ['mResumedActivity', 'ResumedActivity', 'topResumedActivity']:
            if keyword in out:
                lines = out.split('\n')
                for line in lines:
                    if keyword in line and package in line:
                        return True
    return False

def adb_check_network_active(serial, package='com.roblox.client'):
    pid = adb_get_pid(serial, package)
    if not pid:
        return False
    code, out = adb_cmd(['shell', 'cat', f'/proc/{pid}/net/tcp'], serial)
    if code == 0 and out:
        established = [l for l in out.split('\n') if ' 0A ' in l]
        return len(established) > 2
    return False

def auto_push_script_to_vm(acc, serial):
    from blueprints.misc import make_script_for
    from models import settings, log_account as _log_account
    name = acc.get('name', 'Account')
    package = acc.get('package_name', '')
    url = settings.get('dashboard_url', 'http://localhost:5000')
    script = make_script_for(name, url)
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), f'auto_push_{acc.get("id","")}.luau')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(script)
        if package:
            script_path = f'/data/data/{package}/files/Delta/Autoexecute/monitor.luau'
        else:
            script_path = '/sdcard/Delta/Autoexecute/monitor.luau'
        code, out = adb_cmd(['push', tmp, script_path], serial)
        if code == 0:
            target = package if package else 'sdcard'
            _log_account(acc.get('id', ''), name, f'Script push ke {target} OK')
            return True, 'OK'
        return False, out
    except Exception as e:
        return False, str(e)
    finally:
        try: os.remove(tmp)
        except: pass


def push_custom_script_to_vm(script_content, filename, acc, serial):
    """Push a custom script to Delta Autoexecute folder on the VM."""
    from models import log_account as _log_account
    name = acc.get('name', 'Account')
    package = acc.get('package_name', '')
    import tempfile, os
    safe_filename = os.path.basename(filename)
    tmp = os.path.join(tempfile.gettempdir(), f'custom_push_{acc.get("id","")}_{safe_filename}')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(script_content)
        if package:
            script_path = f'/data/data/{package}/files/Delta/Autoexecute/{safe_filename}'
        else:
            script_path = f'/sdcard/Delta/Autoexecute/{safe_filename}'
        code, out = adb_cmd(['push', tmp, script_path], serial)
        if code == 0:
            target = package if package else 'sdcard'
            _log_account(acc.get('id', ''), name, f'Custom script "{safe_filename}" push ke {target} OK')
            return True, 'OK'
        return False, out
    except Exception as e:
        return False, str(e)
    finally:
        try: os.remove(tmp)
        except: pass


def detect_autoexec_folders(serial, package=''):
    """Detect auto-execute folders on a VM/device via ADB.

    Returns a dict:
        {
            'found': [ {path, files, file_names, writable} ],
            'checked': [paths checked],
            'error': None | str
        }
    """
    import os
    safe_pkg = package if package and re.match(r'^[a-zA-Z0-9._]+$', package) else ''

    # Candidate paths (Delta + generic autoexec)
    candidates = [
        '/sdcard/Delta/Autoexecute',
        '/sdcard/Delta/autoexec',
        '/sdcard/Delta/AutoExecute',
        '/storage/emulated/0/Delta/Autoexecute',
        '/storage/emulated/0/Delta/autoexec',
    ]
    if safe_pkg:
        candidates += [
            f'/data/data/{safe_pkg}/files/Delta/Autoexecute',
            f'/data/data/{safe_pkg}/files/Delta/autoexec',
            f'/data/data/{safe_pkg}/files/delta/autoexecute',
            f'/data/data/{safe_pkg}/files/delta/autoexec',
            f'/sdcard/Android/data/{safe_pkg}/files/Delta/Autoexecute',
            f'/sdcard/Android/data/{safe_pkg}/files/Delta/autoexec',
            f'/sdcard/Android/data/{safe_pkg}/files/delta/autoexecute',
            f'/sdcard/Android/data/{safe_pkg}/files/delta/autoexec',
            f'/storage/emulated/0/Android/data/{safe_pkg}/files/Delta/Autoexecute',
            f'/storage/emulated/0/Android/data/{safe_pkg}/files/Delta/autoexec',
            f'/storage/emulated/0/Android/data/{safe_pkg}/files/delta/autoexecute',
            f'/storage/emulated/0/Android/data/{safe_pkg}/files/delta/autoexec',
        ]

    found = []
    checked = []
    error = None

    for path in candidates:
        checked.append(path)
        code, out = adb_cmd(['shell', f'test -d "{path}" && echo EXISTS || echo MISSING'], serial)
        if code != 0:
            error = out or 'ADB command failed'
            continue
        if 'EXISTS' not in (out or ''):
            continue
        # Count files
        _, count_out = adb_cmd(['shell', f'ls -1 "{path}" 2>/dev/null | wc -l'], serial)
        file_count = 0
        try:
            file_count = int((count_out or '0').strip())
        except (ValueError, TypeError):
            pass
        # List file names (limit 20)
        _, ls_out = adb_cmd(['shell', f'ls -1 "{path}" 2>/dev/null | head -20'], serial)
        file_names = [f.strip() for f in (ls_out or '').split('\n') if f.strip()][:20]
        # Check writable
        _, w_out = adb_cmd(['shell', f'test -w "{path}" && echo W_OK || echo W_NO'], serial)
        writable = 'W_OK' in (w_out or '')

        found.append({
            'path': path,
            'files': file_count,
            'file_names': file_names,
            'writable': writable,
        })

    return {'found': found, 'checked': checked, 'error': error if not found else None}


def discover_roblox_packages(serial=None):
    adb = find_adb()
    if not adb: return []
    try:
        r = adb_cmd(['shell', 'pm', 'list', 'packages'], serial)
        if r and r[0] == 0 and r[1]:
            found = []
            for line in r[1].split('\n'):
                pkg = line.replace('package:', '').strip()
                if 'roblox' in pkg.lower():
                    found.append(pkg)
            return sorted(found)
    except:
        pass
    return []

def adb_set_freeform(serial, package):
    adb = find_adb()
    if not adb: return False
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'am', 'start', '-n', f'{package}/.Activity',
            '--windowingMode', '6'], serial=serial, capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except:
        return False

def adb_move_window(serial, package, x, y, w, h):
    adb = find_adb()
    if not adb: return False
    try:
        _adb_run([adb, '-s', serial, 'shell', 'am', 'start', '-n', f'{package}/.Activity',
            '--windowingMode', '6',
            '--eias', f'{x},{y},{x+w},{y+h}'],
            serial=serial, capture_output=True, timeout=10)
        return True
    except:
        return False

def adb_screenshot_package(serial, package='com.roblox.client'):
    data = adb_screenshot(serial)
    if data is None:
        return None
    return data
