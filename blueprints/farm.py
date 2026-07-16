import os, json, threading, time
from flask import Blueprint, jsonify, request
from models import settings

farm_bp = Blueprint('farm', __name__)

farm_thread = None
farm_running = False

FARM_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bloxy_farm_config.json')

def load_farm_config():
    if os.path.exists(FARM_CONFIG_PATH):
        try:
            with open(FARM_CONFIG_PATH, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_farm_config(cfg):
    try:
        with open(FARM_CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=4)
        return True
    except:
        return False

@farm_bp.route('/api/farm/config', methods=['GET'])
def get_farm_config():
    cfg = load_farm_config()
    return jsonify({
        'config': cfg,
        'running': farm_running
    })

@farm_bp.route('/api/farm/config', methods=['POST'])
def update_farm_config():
    data = request.json or {}
    cfg = load_farm_config()
    for key in ['packages', 'ps_url', 'ps_urls', 'mask_username',
                'delay_launch', 'delay_relaunch', 'webhook',
                'status_update_interval', 'scheduled_restart_interval',
                'auto_clear_cache', 'auto_captcha', 'captcha_timeout',
                'auto_inject', 'scripts', 'license_key']:
        if key in data:
            cfg[key] = data[key]
    save_farm_config(cfg)
    return jsonify({'success': True})

@farm_bp.route('/api/farm/status', methods=['GET'])
def farm_status():
    cfg = load_farm_config()
    packages = cfg.get('packages', [])
    statuses = {}
    for pkg in packages:
        try:
            import subprocess
            pid = subprocess.check_output(
                ['su', '-c', f'pidof {pkg}'],
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            statuses[pkg] = 'Online' if pid else 'Offline'
        except:
            statuses[pkg] = 'Offline'
    return jsonify({
        'running': farm_running,
        'packages': packages,
        'statuses': statuses
    })

@farm_bp.route('/api/farm/start', methods=['POST'])
def start_farm():
    global farm_thread, farm_running
    if farm_running:
        return jsonify({'error': 'Farm sudah berjalan'}), 400
    cfg = load_farm_config()
    if not cfg.get('packages'):
        return jsonify({'error': 'Tidak ada package dikonfigurasi'}), 400
    farm_running = True
    farm_thread = threading.Thread(target=_run_farm_loop, args=(cfg,), daemon=True)
    farm_thread.start()
    return jsonify({'success': True, 'message': f"Farm started with {len(cfg['packages'])} packages"})

@farm_bp.route('/api/farm/stop', methods=['POST'])
def stop_farm():
    global farm_running
    farm_running = False
    cfg = load_farm_config()
    for pkg in cfg.get('packages', []):
        try:
            import subprocess
            subprocess.run(['su', '-c', f'am force-stop {pkg}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    return jsonify({'success': True, 'message': 'Farm stopped'})

@farm_bp.route('/api/farm/inject', methods=['POST'])
def inject_scripts():
    cfg = load_farm_config()
    packages = cfg.get('packages', [])
    if not packages:
        return jsonify({'error': 'No packages'}), 400
    try:
        from bloxy_farm import auto_inject_script
        for pkg in packages:
            auto_inject_script(pkg, cfg)
        return jsonify({'success': True, 'message': f'Injected into {len(packages)} packages'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@farm_bp.route('/api/farm/clear-cache', methods=['POST'])
def clear_cache():
    try:
        import subprocess
        subprocess.run(['su', '-c', 'rm -rf /data/data/com.roblox.*/cache/*'])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _run_farm_loop(cfg):
    global farm_running
    try:
        from bloxy_farm import (
            optimize_system, kill_app, start_app, is_app_running,
            tile_all_windows, get_grid_bounds, send_webhook, load_config, save_config
        )
    except ImportError:
        farm_running = False
        return

    packages = cfg.get('packages', [])
    if not packages:
        farm_running = False
        return

    optimize_system()

    delay_launch = cfg.get('delay_launch', 15)
    delay_relaunch = cfg.get('delay_relaunch', 60)
    scheduled_restart = cfg.get('scheduled_restart_interval', 0) * 60
    status_interval = cfg.get('status_update_interval', 0) * 60
    webhook_url = cfg.get('webhook', '')

    for pkg in packages:
        kill_app(pkg)
    time.sleep(2)

    bounds_map = {}
    for i, pkg in enumerate(packages):
        bounds_map[pkg] = get_grid_bounds(i, len(packages))

    start_time = time.time()
    last_status_time = time.time()

    while farm_running:
        current = time.time()

        if scheduled_restart > 0 and (current - start_time) > scheduled_restart:
            send_webhook(webhook_url, "Scheduled Restart", "Restarting all apps...", 16711680)
            for pkg in packages:
                kill_app(pkg)
            start_time = current
            time.sleep(5)

        if status_interval > 0 and (current - last_status_time) > status_interval:
            online = sum(1 for p in packages if is_app_running(p))
            send_webhook(webhook_url, "Status Update", f"{online}/{len(packages)} online", 65280)
            last_status_time = current

        for pkg in packages:
            if not farm_running:
                break
            if not is_app_running(pkg):
                start_app(pkg, cfg, bounds_map.get(pkg))
                time.sleep(delay_launch)

        tile_all_windows(packages)
        time.sleep(delay_relaunch / max(len(packages), 1))

    farm_running = False
