import re, os, json, time, uuid, urllib.request, urllib.parse

from flask import Blueprint, render_template, request, jsonify

from models import accounts, servers, settings, activity_log, acc_logs, inventory_data, _data_lock, log_activity, log_account, save_data, schedules, schedule_history
from services.adb import find_adb, get_serial, adb_connect, adb_cmd, adb_screenshot, auto_push_script_to_vm
from services.mumu import mumu_vm_cmd, load_vm_display_names
from services.webhook import send_webhook
from config import DATA_FILE, BACKUP_FILE
from core.script_generator import make_script_for
from core.scheduler import start_scheduler, check_schedules, calculate_next_run

misc_bp = Blueprint('misc', __name__)

@misc_bp.route('/')
def index():
    return render_template('index.html')

@misc_bp.route('/api/summary', methods=['GET'])
def get_summary():
    total = len(accounts)
    running_vms = 0
    running_instances = set()
    try:
        code, out = mumu_vm_cmd(['list', 'runningvms'])
        if code == 0:
            lines = [l for l in out.split('\n') if l.strip()]
            running_vms = len(lines)
            for line in lines:
                m = re.search(r'MuMuPlayerGlobal-12\.0-(\d+)', line)
                if m:
                    running_instances.add(int(m.group(1)))
    except:
        pass

    if running_instances:
        online = sum(1 for a in accounts
            if a.get('status') in ('connected', 'monitoring', 'active')
            and a.get('mumu_instance') in running_instances)
    else:
        online = sum(1 for a in accounts if a.get('status') in ('connected', 'monitoring', 'active'))
    error = sum(1 for a in accounts if a.get('status') == 'error')
    idle = total - online - error
    verified = sum(1 for a in accounts if a.get('verified_username'))
    total_robux = sum(a.get('verified_robux', 0) or 0 for a in accounts)
    total_sheckles = sum(inventory_data.get(a.get('name', ''), {}).get('sheckles', 0) for a in accounts)

    price_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'item_sell_prices.json')
    sell_prices = {}
    try:
        with open(price_file, 'r') as f:
            sell_prices = json.load(f)
    except:
        pass

    total_inventory_value = 0
    for a in accounts:
        inv = inventory_data.get(a.get('name', ''), {})
        for item in inv.get('items', []):
            price = sell_prices.get(item.get('name', ''), 0)
            total_inventory_value += price * item.get('count', 0)

    return jsonify({
        'total_accounts': total, 'online': online, 'error': error, 'idle': idle,
        'verified': verified, 'total_robux': total_robux,
        'total_sheckles': total_sheckles, 'total_inventory_value': total_inventory_value,
        'running_vms': running_vms, 'total_vms': len(settings.get('mumu_serials', [])) or 1
    })

@misc_bp.route('/api/games/search', methods=['GET'])
def search_games():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})
    try:
        session = str(uuid.uuid4())
        url = f'https://apis.roblox.com/search-api/omni-search?searchQuery={urllib.parse.quote(q)}&pageToken=&sessionId={session}'
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        results = []
        for sr in data.get('searchResults', []):
            if sr.get('contentGroupType') != 'Game':
                continue
            for g in sr.get('contents', []):
                pid = str(g.get('rootPlaceId', ''))
                if not pid or not pid.isdigit():
                    continue
                results.append({'place_id': pid, 'name': g.get('name', 'Unknown'), 'player_count': g.get('playerCount', 0), 'thumbnail': g.get('thumbnailUrl', '')})
        return jsonify({'results': results[:15]})
    except Exception as e:
        return jsonify({'results': [], 'error': str(e)[:200]})

@misc_bp.route('/api/webhook/test', methods=['POST'])
def test_webhook():
    url = request.json.get('url', '')
    if not url:
        return jsonify({'success': False, 'error': 'URL kosong'})
    if not url.startswith('https://'):
        return jsonify({'success': False, 'error': 'URL harus https:// (HTTP tidak diizinkan)'})
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    blocked_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '10.', '172.', '192.168.', '::1']
    for pattern in blocked_patterns:
        if hostname.startswith(pattern) or hostname == pattern:
            return jsonify({'success': False, 'error': 'Internal URLs tidak diizinkan'})
    try:
        data = json.dumps({'embeds': [{'title': '✅ Test Notifikasi Dashboard Roblox', 'description': 'Webhook berfungsi dengan baik!', 'color': 0x43e97b, 'footer': {'text': 'Dashboard Roblox'}}]}).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'DashboardRoblox/1.0'})
        urllib.request.urlopen(req, timeout=10)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@misc_bp.route('/api/activity', methods=['GET'])
def get_activity():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(activity_log[:limit])

@misc_bp.route('/api/activity', methods=['DELETE'])
def clear_activity_api():
    account_id = request.args.get('account_id')
    if account_id:
        acc_logs[account_id] = []
        return jsonify({'success': True, 'account': account_id})
    activity_log.clear()
    return jsonify({'success': True})

@misc_bp.route('/api/restore-data', methods=['POST'])
def restore_data():
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
        with _data_lock:
            accounts.clear()
            for acc in bak_accounts:
                if not acc.get('server_ids') and acc.get('server_id'):
                    acc['server_ids'] = [acc['server_id']]
                accounts.append(acc)
            servers.clear()
            servers.extend(bak_servers)
        save_data()
        log_activity(f'Data restored from backup ({len(accounts)} accounts, {len(servers)} servers)')
        return jsonify({'success': True, 'accounts': len(accounts), 'servers': len(servers)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@misc_bp.route('/api/status', methods=['POST'])
def receive_status():
    data = request.json
    acc_name = data.get('account', 'unknown')
    status = data.get('status', 'unknown')
    msg = data.get('message', '')
    for acc in accounts:
        if acc['name'].lower() == acc_name.lower():
            old_status = acc.get('status', '')
            acc['status'] = status
            if status in ('monitoring', 'active', 'connected'):
                acc['active'] = True
            elif status in ('kicked', 'left', 'disconnected', 'error'):
                acc['active'] = False
                if status in ('kicked', 'error') and status != old_status:
                    send_webhook(f'⚠️ {acc_name} — {status.upper()}', f'**Server:** {msg or "N/A"}\n**Instance:** MuMu-{acc.get("mumu_instance", "?")}', 0xff4444 if status == 'error' else 0xffaa00, acc.get('verified_avatar'))
            save_data()
            break
    log_activity(f'[{acc_name}] {msg}', 'info' if status != 'error' else 'error')
    return jsonify({'success': True})

def _auto_rejoin(acc, reason=''):
    try:
        acc_name = acc.get('name', '?')
        serial = acc.get('serial') or ''
        instance = acc.get('mumu_instance')
        if not serial and instance is not None:
            serials = settings.get('mumu_serials', [])
            if instance < len(serials):
                serial = serials[instance]
        if not serial:
            log_activity(f'[{acc_name}] Auto-rejoin skipped: no serial')
            return
        delay = settings.get('rejoin_delay', 3)
        log_activity(f'[{acc_name}] Auto-rejoin in {delay}s (reason: {reason})')
        time.sleep(delay)
        from services.adb import adb_force_stop_roblox
        adb_force_stop_roblox(serial)
        time.sleep(2)
        from services.roblox import build_join_link
        sv = next((s for s in servers if acc.get('server_ids') and s['id'] in acc.get('server_ids')), None)
        if sv:
            link = build_join_link(sv)
            if link:
                adb_connect(serial)
                import subprocess
                subprocess.run(['adb', '-s', serial, 'shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', link], capture_output=True, timeout=15)
                log_activity(f'[{acc_name}] Auto-rejoin: sent join link')
                acc['status'] = 'rejoining'
                save_data()
            else:
                log_activity(f'[{acc_name}] Auto-rejoin failed: no join link')
        else:
            log_activity(f'[{acc_name}] Auto-rejoin failed: no server assigned')
    except Exception as e:
        log_activity(f'[{acc_name}] Auto-rejoin error: {e}')

@misc_bp.route('/api/push-all-active', methods=['POST'])
def push_script_to_all_active():
    from services.adb import adb_check_roblox, auto_push_script_to_vm
    results = []
    serials = settings.get('mumu_serials', [])
    code, out = mumu_vm_cmd(['list', 'runningvms'])
    running_vms = set()
    if code == 0:
        for line in out.split('\n'):
            line = line.strip()
            if line:
                parts = line.split('{')
                name = parts[0].strip().strip('"')
                running_vms.add(name)
    for idx, serial in enumerate(serials):
        if not serial or not serial.strip():
            results.append({'instance': idx, 'serial': '', 'status': 'skipped', 'message': 'No serial'})
            continue
        vm_name = f'MuMuPlayerGlobal-12.0-{idx}'
        if vm_name not in running_vms:
            results.append({'instance': idx, 'serial': serial, 'status': 'skipped', 'message': 'VM not running'})
            continue
        ok, msg = adb_connect(serial.strip())
        if not ok:
            results.append({'instance': idx, 'serial': serial, 'status': 'error', 'message': f'ADB: {msg}'})
            continue
        if not adb_check_roblox(serial.strip()):
            results.append({'instance': idx, 'serial': serial, 'status': 'skipped', 'message': 'Roblox not running'})
            continue
        acc = next((a for a in accounts if a.get('mumu_instance') == idx and a.get('cookie')), None)
        if not acc:
            results.append({'instance': idx, 'serial': serial, 'status': 'skipped', 'message': 'No account'})
            continue
        success, result_msg = auto_push_script_to_vm(acc, serial.strip())
        if success:
            results.append({'instance': idx, 'serial': serial, 'status': 'ok', 'message': 'Script pushed', 'account': acc.get('name', '?')})
        else:
            results.append({'instance': idx, 'serial': serial, 'status': 'error', 'message': result_msg})
    ok_count = sum(1 for r in results if r['status'] == 'ok')
    return jsonify({'success': True, 'results': results, 'pushed': ok_count, 'total': len(results)})

@misc_bp.route('/api/generate-script', methods=['GET'])
def generate_script():
    url = settings.get('dashboard_url', 'http://localhost:5000')
    script = make_script_for('Account-1', url)
    return jsonify({'script': script, 'filename': 'DashboardReporter.luau'})

@misc_bp.route('/api/generate-mailbox-script', methods=['GET'])
def generate_mailbox_script():
    target_id = request.args.get('target_id', '0')
    target_name = request.args.get('target_name', 'Player')
    batch_size = request.args.get('batch_size', '25')
    delay = request.args.get('delay', '8')

    script = f'''-- Mailbox Send Script (Bypass 20-item limit)
-- Target: {target_name} (ID: {target_id})
-- Batch Size: {batch_size} | Delay: {delay}s

local Players = game:GetService("Players")
local StarterGui = game:GetService("StarterGui")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local LP = Players.LocalPlayer

local TARGET_USER_ID = {target_id}
local BATCH_SIZE = {batch_size}
local DELAY_BETWEEN_BATCHES = {delay}

local function notify(t, d)
    pcall(function() StarterGui:SetCore("SendNotification", {{Title="Mailbox", Text=t, Duration=d or 5}}) end)
end

local function getInventory()
    local items = {{}}
    local invFrame = LP.PlayerGui:FindFirstChild("MailboxUI")
    if not invFrame then
        notify("MailboxUI not found!", 5)
        return items
    end
    local frame = invFrame.Frame.SendingFrame.ItemSendFrame.ScrollingFrames.InventoryFrame
    if not frame then
        notify("Inventory frame not found!", 5)
        return items
    end
    for _, child in ipairs(frame:GetChildren()) do
        if child:IsA("Frame") and child.Name ~= "ItemFrameTemplate" then
            local cat, key = child.Name:match("^Inv_(.+):(.+)$")
            if cat and key then
                table.insert(items, {{category = cat, itemKey = key, name = child.Name}})
            end
        end
    end
    return items
end

local function sendBatch(items, batchNum)
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    local batch = {{}}
    for i, item in ipairs(items) do
        table.insert(batch, {{Category = item.category, ItemKey = item.itemKey, Count = 1}})
    end
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(TARGET_USER_ID, batch, "Batch " .. batchNum)
    end)
    return ok, success, msg
end

notify("Loading inventory...", 3)
local allItems = getInventory()
notify("Found " .. #allItems .. " items", 3)
if #allItems == 0 then notify("No items to send!", 5) return end

local batches = {{}}
for i = 1, #allItems, BATCH_SIZE do
    local batch = {{}}
    for j = i, math.min(i + BATCH_SIZE - 1, #allItems) do
        table.insert(batch, allItems[j])
    end
    table.insert(batches, batch)
end

notify("Sending " .. #batches .. " batches...", 5)
local successCount = 0
local failCount = 0
for i, batch in ipairs(batches) do
    if i > 1 then task.wait(DELAY_BETWEEN_BATCHES) end
    notify("Sending batch " .. i .. "/" .. #batches .. " (" .. #batch .. " items)", 3)
    local ok, success, msg = sendBatch(batch, i)
    if ok and success then successCount = successCount + 1 else failCount = failCount + 1 end
end
local summary = "Done! " .. successCount .. " ok, " .. failCount .. " failed"
notify(summary, 10)
print("[Mailbox] " .. summary)
print("[Mailbox] Total items sent: " .. #allItems)
'''

    return jsonify({'script': script, 'filename': f'MailboxSend_{target_name}_{target_id}.luau', 'target_id': target_id, 'target_name': target_name, 'batch_size': batch_size, 'delay': delay})

@misc_bp.route('/api/generate-mailbox-batch-script', methods=['POST'])
def generate_mailbox_batch_script():
    data = request.json or {}
    target_id = data.get('target_id', 0)
    target_name = data.get('target_name', 'Player')
    items = data.get('items', [])
    note = data.get('note', '')
    batch_size = data.get('batch_size', 25)
    delay = data.get('delay', 8)

    if not target_id:
        return jsonify({'error': 'target_id required'}), 400

    items_lua = []
    for item in items:
        cat = item.get('category', '')
        key = item.get('itemKey', '')
        items_lua.append(f'{{Category="{cat}", ItemKey="{key}", Count=1}}')
    items_table = '{' + ','.join(items_lua) + '}'
    note_escaped = note.replace('"', '\\"').replace('\n', '\\n')

    script = f'''-- Mailbox Batch Send Script
-- Target: {target_name} (ID: {target_id})
-- Items: {len(items)} | Batch Size: {batch_size}

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local Players = game:GetService("Players")

local function notify(t, d)
    pcall(function() StarterGui:SetCore("SendNotification", {{Title="Mailbox", Text=t, Duration=d or 5}}) end)
end

local networking = require(ReplicatedStorage.SharedModules.Networking)
local mailbox = networking.Mailbox

local TARGET_ID = {target_id}
local ITEMS = {items_table}
local BATCH_SIZE = {batch_size}
local DELAY = {delay}
local NOTE = "{note_escaped}"

local batches = {{}}
for i = 1, #ITEMS, BATCH_SIZE do
    local batch = {{}}
    for j = i, math.min(i + BATCH_SIZE - 1, #ITEMS) do
        table.insert(batch, ITEMS[j])
    end
    table.insert(batches, batch)
end

notify("Sending " .. #batches .. " batches to {target_name}...", 5)
print("[Mailbox] Target: {target_name} ({target_id})")
print("[Mailbox] Total items: " .. #ITEMS)
print("[Mailbox] Batches: " .. #batches)

local successCount = 0
local failCount = 0
for i, batch in ipairs(batches) do
    if i > 1 then task.wait(DELAY) end
    notify("Batch " .. i .. "/" .. #batches, 3)
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(TARGET_ID, batch, NOTE ~= "" and NOTE or ("Batch " .. i))
    end)
    if ok and success then successCount = successCount + 1 else failCount = failCount + 1 end
end
notify("Done! " .. successCount .. " ok, " .. failCount .. " failed", 10)
print("[Mailbox] SUMMARY: " .. successCount .. " success, " .. failCount .. " failed")
'''
    return jsonify({'script': script, 'filename': f'MailboxBatch_{target_name}_{target_id}.luau'})

@misc_bp.route('/api/batch/push-script', methods=['POST'])
def batch_push_script():
    serials = settings.get('mumu_serials', [''])
    serial = serials[0] if serials else ''
    if not serial:
        return jsonify({'error': 'No ADB serial configured'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500
    results = []
    for acc in accounts:
        pkg = acc.get('package_name', '')
        success, result_msg = auto_push_script_to_vm(acc, serial)
        results.append({'account': acc['name'], 'package': pkg, 'success': success, 'message': result_msg})
    ok_count = sum(1 for r in results if r['success'])
    return jsonify({'success': True, 'results': results, 'pushed': ok_count, 'total': len(results)})

@misc_bp.route('/api/batch/screenshot', methods=['GET'])
def batch_screenshot():
    import base64
    serials = settings.get('mumu_serials', [''])
    serial = serials[0] if serials else ''
    if not serial:
        return jsonify({'error': 'No ADB serial configured'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500
    screenshots = {}
    for acc in accounts:
        data = adb_screenshot(serial)
        if data:
            screenshots[acc['name']] = {'image': base64.b64encode(data).decode()}
    return jsonify({'screenshots': screenshots, 'count': len(screenshots)})

@misc_bp.route('/api/batch/auto-login', methods=['POST'])
def batch_auto_login():
    results = []
    for acc in accounts:
        cookie = acc.get('cookie', '')
        if not cookie:
            results.append({'account': acc['name'], 'success': False, 'error': 'No cookie'})
            continue
        instance = acc.get('mumu_instance', 0)
        package = acc.get('package_name', '')
        serial = get_serial(instance)
        if not serial:
            results.append({'account': acc['name'], 'success': False, 'error': 'No serial'})
            continue
        ok, msg = adb_connect(serial)
        if not ok:
            results.append({'account': acc['name'], 'success': False, 'error': msg})
            continue
        try:
            adb = find_adb()
            if not adb:
                results.append({'account': acc['name'], 'success': False, 'error': 'ADB not found'})
                continue
            subprocess.run([adb, '-s', serial, 'shell', 'pm', 'clear', package], capture_output=True, timeout=15)
            time.sleep(2)
            auth_xml = f'<?xml version="1.0" encoding="utf-8"?><map><string name="ROBLOSECURITY">{cookie}</string></map>'
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), f'login_{acc["id"]}.xml')
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(auth_xml)
            path = f'/data/data/{package}/shared_prefs/roblox.xml'
            r = subprocess.run([adb, '-s', serial, 'push', tmp, path], capture_output=True, timeout=10)
            os.unlink(tmp)
            if r.returncode == 0:
                subprocess.run([adb, '-s', serial, 'shell', 'chmod', '600', path], capture_output=True, timeout=5)
                subprocess.run([adb, '-s', serial, 'shell', 'am', 'start', '-n', f'{package}/.RobloxApp'], capture_output=True, timeout=10)
                results.append({'account': acc['name'], 'success': True, 'package': package})
                log_account(acc['id'], acc['name'], f'Auto-login: cookie injected to {package}')
            else:
                results.append({'account': acc['name'], 'success': False, 'error': 'Push failed'})
        except Exception as e:
            results.append({'account': acc['name'], 'success': False, 'error': str(e)})
    ok_count = sum(1 for r in results if r['success'])
    return jsonify({'success': True, 'results': results, 'logged_in': ok_count, 'total': len(results)})

@misc_bp.route('/api/batch/auto-grid', methods=['POST'])
def batch_auto_grid():
    serials = settings.get('mumu_serials', [''])
    serial = serials[0] if serials else ''
    if not serial:
        return jsonify({'error': 'No ADB serial configured'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500
    packages = [a.get('package_name', '') for a in accounts if a.get('package_name')]
    if not packages:
        return jsonify({'error': 'No accounts configured'}), 400
    r = adb_cmd(['shell', 'wm', 'size'], serial)
    if r and r[0] == 0 and r[1]:
        m = re.search(r'(\d+)x(\d+)', r[1])
        if m:
            screen_w, screen_h = int(m.group(1)), int(m.group(2))
        else:
            screen_w, screen_h = 1080, 1920
    else:
        screen_w, screen_h = 1080, 1920
    n = len(packages)
    cols = int(n ** 0.5)
    if cols * cols < n:
        cols += 1
    rows = (n + cols - 1) // cols
    cell_w = screen_w // cols
    cell_h = screen_h // rows
    adb = find_adb()
    results = []
    for i, pkg in enumerate(packages):
        row = i // cols
        col = i % cols
        try:
            subprocess.run([adb, '-s', serial, 'shell', 'am', 'start', '-n', f'{pkg}/.Activity', '--windowingMode', '6'], capture_output=True, timeout=10)
            time.sleep(0.5)
            results.append({'package': pkg, 'position': {'x': col * cell_w, 'y': row * cell_h, 'w': cell_w, 'h': cell_h}, 'success': True})
        except Exception as e:
            results.append({'package': pkg, 'success': False, 'error': str(e)})
    return jsonify({'success': True, 'grid': f'{cols}x{rows}', 'screen': {'w': screen_w, 'h': screen_h}, 'cell': {'w': cell_w, 'h': cell_h}, 'results': results})

# ==================== AUTO SEND SCHEDULE ROUTES ====================
@misc_bp.route('/api/schedule/list', methods=['GET'])
def schedule_list():
    return jsonify({'schedules': schedules, 'history': schedule_history[-50:]})

@misc_bp.route('/api/schedule/create', methods=['POST'])
def schedule_create():
    data = request.json or {}
    account = data.get('account', '')
    target = data.get('target', '')
    items = data.get('items', [])
    schedule_time = data.get('time', '12:00')
    repeat = data.get('repeat', 'daily')
    if not account or not target:
        return jsonify({'error': 'account and target required'}), 400
    if not items:
        return jsonify({'error': 'items required'}), 400
    schedule_entry = {
        'id': f"sched_{int(time.time() * 1000)}",
        'account': account, 'target': target, 'items': items,
        'time': schedule_time, 'repeat': repeat, 'enabled': True,
        'last_run': None,
        'next_run': calculate_next_run({'time': schedule_time, 'repeat': repeat}),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with _data_lock:
        schedules.append(schedule_entry)
    save_data()
    log_activity(f'Schedule created: {account} → {target} at {schedule_time} ({repeat})')
    return jsonify({'success': True, 'schedule': schedule_entry})

@misc_bp.route('/api/schedule/<sched_id>', methods=['PUT'])
def schedule_update(sched_id):
    data = request.json or {}
    with _data_lock:
        sched = next((s for s in schedules if s['id'] == sched_id), None)
        if not sched:
            return jsonify({'error': 'Schedule not found'}), 404
        for k in ('account', 'target', 'items', 'time', 'repeat', 'enabled'):
            if k in data:
                sched[k] = data[k]
        sched['next_run'] = calculate_next_run(sched)
    save_data()
    log_activity(f'Schedule updated: {sched_id}')
    return jsonify({'success': True, 'schedule': sched})

@misc_bp.route('/api/schedule/<sched_id>', methods=['DELETE'])
def schedule_delete(sched_id):
    with _data_lock:
        sched = next((s for s in schedules if s['id'] == sched_id), None)
        if not sched:
            return jsonify({'error': 'Schedule not found'}), 404
        schedules.remove(sched)
    save_data()
    log_activity(f'Schedule deleted: {sched_id}')
    return jsonify({'success': True})

@misc_bp.route('/api/schedule/toggle', methods=['POST'])
def schedule_toggle():
    data = request.json or {}
    sched_id = data.get('id', '')
    enabled = data.get('enabled', True)
    with _data_lock:
        sched = next((s for s in schedules if s['id'] == sched_id), None)
        if not sched:
            return jsonify({'error': 'Schedule not found'}), 404
        sched['enabled'] = enabled
    save_data()
    return jsonify({'success': True, 'enabled': enabled})

@misc_bp.route('/api/schedule/history', methods=['GET'])
def schedule_history_list():
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'history': schedule_history[-limit:]})
