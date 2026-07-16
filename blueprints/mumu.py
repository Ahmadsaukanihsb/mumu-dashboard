import os, time, subprocess, re, json

from flask import Blueprint, request, jsonify, Response

from models import settings, accounts, servers, _data_lock, log_activity, log_account, save_data
from services.adb import find_adb, adb_connect, adb_check_roblox, adb_force_stop_roblox, adb_cmd, adb_screenshot, adb_check_join_failed, adb_dismiss_dialogs
from services.mumu import find_mumu_vmm, mumu_vm_cmd, load_vm_display_names, ensure_vm_running, find_mumu_vms_dir
from services.roblox import build_join_link  # Bug #9 fix: import dari sumber tunggal services/roblox.py
from services.webhook import send_webhook

mumu_bp = Blueprint('mumu', __name__)

@mumu_bp.route('/api/mumu/vms', methods=['GET'])
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

    serials = settings.get('mumu_serials', [])
    for vm in vms:
        if not vm['running']:
            vm['roblox_running'] = False
            continue
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

@mumu_bp.route('/api/mumu/vms/<vm_name>/restart', methods=['POST'])
def mumu_restart_vm_route(vm_name):
    log_activity(f'Restarting MuMu VM "{vm_name}"...')
    from models import user_shutdown_instances
    m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', vm_name)
    if m:
        user_shutdown_instances.discard(int(m.group(1)))
    code, out = mumu_vm_cmd(['stopvm', vm_name])
    time.sleep(5)
    code2, out2 = mumu_vm_cmd(['startvm', vm_name, '--type', 'headless'])
    if code2 == 0:
        log_activity(f'MuMu VM "{vm_name}" restarted')
        return jsonify({'success': True, 'message': out2})
    return jsonify({'success': False, 'message': out2 or 'VM did not restart'}), 500

@mumu_bp.route('/api/mumu/vms/<vm_name>/start', methods=['POST'])
def mumu_start_vm(vm_name):
    from models import user_shutdown_instances
    m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', vm_name)
    if m:
        user_shutdown_instances.discard(int(m.group(1)))
    code, out = mumu_vm_cmd(['startvm', vm_name, '--type', 'headless'])
    if code == 0:
        log_activity(f'MuMu VM "{vm_name}" started')
        return jsonify({'success': True, 'message': out})
    return jsonify({'success': False, 'message': out}), 500

@mumu_bp.route('/api/mumu/vms/<vm_name>/stop', methods=['POST'])
def mumu_stop_vm(vm_name):
    from models import user_shutdown_instances
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

@mumu_bp.route('/api/mumu/start-all-and-join', methods=['POST'])
def mumu_start_all_and_join():
    score, out = mumu_vm_cmd(['list', 'runningvms'])
    running_names = []
    if score == 0:
        for line in out.split('\n'):
            line = line.strip()
            if line:
                running_names.append(line.split('{')[0].strip().strip('"'))
    serials = settings.get('mumu_serials', [])
    all_vms = [{'name': f'MuMuPlayerGlobal-12.0-{i}', 'running': False} for i in range(len(serials) or 1)]
    for vm in all_vms:
        if vm['name'] in running_names:
            vm['running'] = True
    results = []
    for idx, vm in enumerate(all_vms):
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

@mumu_bp.route('/api/quick-join-instance/<int:instance_idx>/<place_id>', methods=['POST'])
def quick_join_instance(instance_idx, place_id):
    serials = settings.get('mumu_serials', [])
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
    for _ in range(4):
        time.sleep(5)
        if adb_check_join_failed(serial.strip()) is True:
            adb_dismiss_dialogs(serial.strip())
            break
    log_activity(f'[QuickJoin] Instance {instance_idx} opened place {place_id}')
    return jsonify({'status': 'ok', 'instance': instance_idx, 'serial': serial.strip()})

@mumu_bp.route('/api/quick-join/<place_id>', methods=['POST'])
def quick_join(place_id):
    serials = settings.get('mumu_serials', [])
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
        for _ in range(4):
            time.sleep(5)
            if adb_check_join_failed(serial.strip()) is True:
                adb_dismiss_dialogs(serial.strip())
                break
        results.append({'instance': idx, 'status': 'ok', 'serial': serial.strip(), 'message': f'Opening {place_id}'})
        log_activity(f'[QuickJoin] Instance {idx} opened place {place_id}')
    return jsonify({'results': results, 'place_id': place_id})

@mumu_bp.route('/api/mumu/test', methods=['POST'])
def mumu_test():
    serials = settings.get('mumu_serials', [])
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

@mumu_bp.route('/api/mumu/<int:instance>/screenshot', methods=['GET'])
def mumu_screenshot(instance):
    serials = settings.get('mumu_serials', [])
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

@mumu_bp.route('/api/mumu/health', methods=['GET'])
def mumu_health():
    serials = settings.get('mumu_serials', [])
    display_names = load_vm_display_names()
    health = []
    for idx, serial in enumerate(serials):
        vm_key = f'MuMuPlayerGlobal-12.0-{idx}'
        info = {'instance': idx, 'serial': serial, 'connected': False,
                'uptime': None, 'mem_used_pct': None, 'display_name': display_names.get(vm_key, f'MuMu-{idx}')}
        if not serial:
            health.append(info)
            continue
        try:
            code, _ = adb_cmd(['shell', 'echo', 'ok'], serial=serial)
            if code != 0:
                health.append(info)
                continue
            info['connected'] = True
        except:
            health.append(info)
            continue
        try:
            code, out = adb_cmd(['shell', 'cat', '/proc/uptime'], serial=serial)
            if code == 0:
                secs = float(out.split()[0])
                days = int(secs // 86400)
                hrs = int((secs % 86400) // 3600)
                mins = int((secs % 3600) // 60)
                info['uptime'] = f'{days}d {hrs}h {mins}m' if days else f'{hrs}h {mins}m'
        except:
            pass
        try:
            code, out = adb_cmd(['shell', 'cat', '/proc/meminfo'], serial=serial)
            if code == 0:
                total = available = None
                for line in out.split('\n'):
                    if 'MemTotal:' in line: total = int(line.split()[1])
                    if 'MemAvailable:' in line: available = int(line.split()[1])
                if total and available and total > 0:
                    info['mem_used_pct'] = round((1 - available / total) * 100, 1)
        except:
            pass
        health.append(info)
    return jsonify({'health': health})

@mumu_bp.route('/api/mumu/scan', methods=['GET'])
def mumu_scan():
    adb = find_adb()
    
    # Get list of ALL MuMu VMs
    code, out = mumu_vm_cmd(['list', 'vms'])
    all_vms = []
    if code == 0:
        for line in out.split('\n'):
            line = line.strip()
            if 'MuMuPlayerGlobal' in line:
                parts = line.split('{')
                if len(parts) > 1:
                    vm_name = parts[0].strip().strip('"')
                    uid = '{' + parts[1]
                    m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', vm_name)
                    if m:
                        idx = int(m.group(1))
                        all_vms.append({'name': vm_name, 'uid': uid, 'index': idx})
    
    # Get running VMs
    running_vms = set()
    code2, out2 = mumu_vm_cmd(['list', 'runningvms'])
    if code2 == 0:
        for line in out2.split('\n'):
            line = line.strip()
            if 'MuMuPlayerGlobal' in line:
                m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', line)
                if m:
                    running_vms.add(int(m.group(1)))
    
    # Read MAC addresses from MuMu VM config
    vm_base = find_mumu_vms_dir()
    mac_to_idx = {}
    if os.path.isdir(vm_base):
        for entry in os.listdir(vm_base):
            m2 = re.match(r'MuMuPlayerGlobal-12\.0-(\d+)$', entry)
            if not m2:
                continue
            mac_path = os.path.join(vm_base, entry, 'macaddress')
            try:
                with open(mac_path, 'r') as f:
                    mac = f.read().strip().lower().replace(':', '').replace('-', '')
                    mac_to_idx[mac] = m2.group(1)
            except:
                pass
    
    # Get ARP table (IP -> MAC mapping)
    ip_to_mac = {}
    try:
        r = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].count('.') == 3:
                ip = parts[0]
                mac = parts[1].replace('-', '').lower()
                ip_to_mac[ip] = mac
    except:
        pass
    
    # Get ADB devices
    adb_devices = {}
    if adb:
        try:
            r = subprocess.run([adb, 'devices'], capture_output=True, text=True, timeout=5)
            for l in r.stdout.strip().split('\n')[1:]:
                parts = l.strip().split('\t')
                if len(parts) >= 2 and parts[1] == 'device':
                    ip_port = parts[0]
                    ip = ip_port.split(':')[0]
                    adb_devices[ip] = ip_port
        except:
            pass
    
    # Setup serials
    max_idx = max([vm['index'] for vm in all_vms], default=5) if all_vms else 5
    serials = list(settings.get('mumu_serials', []))
    while len(serials) <= max_idx:
        serials.append('')
    
    # Match MAC to IP using ARP table
    for ip, mac in ip_to_mac.items():
        if mac in mac_to_idx:
            idx = int(mac_to_idx[mac])
            if idx < len(serials) and ip in adb_devices:
                serials[idx] = adb_devices[ip]
    
    # Try to connect to running VMs that don't have serials yet
    if adb:
        for vm in all_vms:
            idx = vm['index']
            if idx in running_vms and (idx >= len(serials) or not serials[idx]):
                # Try common MuMu ports
                for port in range(7555, 7561):
                    serial = f'127.0.0.1:{port}'
                    try:
                        conn = subprocess.run([adb, 'connect', serial], capture_output=True, text=True, timeout=3)
                        if 'connected' in conn.stdout.lower():
                            check = subprocess.run([adb, '-s', serial, 'shell', 'echo', 'ok'], capture_output=True, text=True, timeout=3)
                            if check.returncode == 0 and 'ok' in check.stdout.lower():
                                # Check if this serial is already used by another VM
                                if serial not in serials:
                                    serials[idx] = serial
                                    break
                    except:
                        pass
    
    # Save to settings
    settings['mumu_serials'] = serials
    save_data()
    
    # Return ALL VMs with their status
    found = []
    for vm in all_vms:
        idx = vm['index']
        is_running = idx in running_vms
        serial = serials[idx] if idx < len(serials) else ''
        vm_key = f'MuMuPlayerGlobal-12.0-{idx}'
        dn = load_vm_display_names().get(vm_key, f'VM-{idx}')
        found.append({
            'instance': idx,
            'name': dn,
            'vm_name': vm['name'],
            'serial': serial,
            'running': is_running,
            'connected': bool(serial)
        })
    
    return jsonify({
        'devices': found,
        'mumu_serials': serials,
        'total_vms': len(all_vms),
        'running_vms': len(running_vms)
    })

@mumu_bp.route('/api/mumu/discover-packages', methods=['GET'])
def discover_packages():
    """Scan semua Roblox packages yang terinstall"""
    from services.adb import discover_roblox_packages
    serials = settings.get('mumu_serials', [''])
    serial = serials[0] if serials else ''
    if not serial:
        return jsonify({'error': 'No ADB serial configured', 'packages': []}), 400
    ok, msg = adb_connect(serial.strip())
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}', 'packages': []}), 500
    packages = discover_roblox_packages(serial.strip())
    return jsonify({'packages': packages, 'count': len(packages), 'serial': serial})
