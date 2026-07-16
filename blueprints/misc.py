import re, os, json, time, uuid, urllib.request, urllib.parse

from flask import Blueprint, render_template, request, jsonify

from models import accounts, servers, settings, activity_log, acc_logs, inventory_data, harvested_fruits_data, _data_lock, monitor_state, log_activity, log_account, save_data
from services.adb import find_adb, get_serial, adb_connect, adb_cmd, adb_force_stop_roblox, adb_check_join_failed, adb_dismiss_dialogs, adb_screenshot
from services.mumu import mumu_vm_cmd, load_vm_display_names, find_mumu_vmm, find_mumu_vms_dir, ensure_vm_running, launch_mumu
from services.roblox import verify_cookie, build_join_link
from services.webhook import send_webhook
from config import DATA_FILE, BACKUP_FILE
from fruit_values import FRUIT_VALUES, MUTATION_MULTIPLIERS

misc_bp = Blueprint('misc', __name__)

# Game state for weather/events
game_state = {
    'current_weather': None,
    'last_weather_update': None
}

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
    
    # Calculate total inventory value
    import json as json_mod
    price_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'item_sell_prices.json')
    sell_prices = {}
    try:
        with open(price_file, 'r') as f:
            sell_prices = json_mod.load(f)
    except:
        pass
    
    total_inventory_value = 0
    for a in accounts:
        inv = inventory_data.get(a.get('name', ''), {})
        for item in inv.get('items', []):
            price = sell_prices.get(item.get('name', ''), 0)
            total_inventory_value += price * item.get('count', 0)
    
    return jsonify({
        'total_accounts': total,
        'online': online,
        'error': error,
        'idle': idle,
        'verified': verified,
        'total_robux': total_robux,
        'total_sheckles': total_sheckles,
        'total_inventory_value': total_inventory_value,
        'running_vms': running_vms,
        'total_vms': len(settings.get('mumu_serials', [])) or 1
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
                results.append({
                    'place_id': pid,
                    'name': g.get('name', 'Unknown'),
                    'player_count': g.get('playerCount', 0),
                    'thumbnail': g.get('thumbnailUrl', ''),
                })
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
    
    # Block internal/private IPs to prevent SSRF
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    
    # Block private/internal IPs
    blocked_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '10.', '172.', '192.168.', '::1']
    for pattern in blocked_patterns:
        if hostname.startswith(pattern) or hostname == pattern:
            return jsonify({'success': False, 'error': 'Internal URLs tidak diizinkan'})
    
    try:
        data = json.dumps({
            'embeds': [{
                'title': '✅ Test Notifikasi Dashboard Roblox',
                'description': 'Webhook berfungsi dengan baik!',
                'color': 0x43e97b,
                'footer': {'text': 'Dashboard Roblox'}
            }]
        }).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'DashboardRoblox/1.0'})
        urllib.request.urlopen(req, timeout=10)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': f'{type(e).__name__}: {str(e)[:200]}'})

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
        if acc['name'] == acc_name:
            old_status = acc.get('status', '')
            acc['status'] = status
            if status in ('monitoring', 'active', 'connected'):
                acc['active'] = True
            elif status in ('kicked', 'left', 'disconnected', 'error'):
                acc['active'] = False
                if status in ('kicked', 'error') and status != old_status:
                    send_webhook(
                        f'⚠️ {acc_name} — {status.upper()}',
                        f'**Server:** {msg or "N/A"}\n**Instance:** MuMu-{acc.get("mumu_instance", "?")}',
                        0xff4444 if status == 'error' else 0xffaa00,
                        acc.get('verified_avatar')
                    )
                    
                    # Auto-rejoin jika enabled
                    if settings.get('auto_join_enabled', True) and status == 'kicked':
                        import threading
                        threading.Thread(target=_auto_rejoin, args=(acc, msg), daemon=True).start()
                        
            save_data()
            break
    log_activity(f'[{acc_name}] {msg}', 'info' if status != 'error' else 'error')
    return jsonify({'success': True})

def _auto_rejoin(acc, reason=''):
    """Auto-rejoin setelah kick/disconnect"""
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
        
        # Force stop Roblox
        from services.adb import adb_force_stop_roblox, adb_check_roblox, adb_connect
        adb_force_stop_roblox(serial)
        time.sleep(2)
        
        # Coba join
        from services.roblox import build_join_link
        sv = next((s for s in servers if acc.get('server_ids') and s['id'] in acc.get('server_ids')), None)
        if sv:
            link = build_join_link(sv)
            if link:
                # Buka link untuk join
                adb_connect(serial)
                import subprocess
                subprocess.run(['adb', '-s', serial, 'shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', link], 
                             capture_output=True, timeout=15)
                log_activity(f'[{acc_name}] Auto-rejoin: sent join link')
                acc['status'] = 'rejoining'
                save_data()
            else:
                log_activity(f'[{acc_name}] Auto-rejoin failed: no join link')
        else:
            log_activity(f'[{acc_name}] Auto-rejoin failed: no server assigned')
            
    except Exception as e:
        log_activity(f'[{acc_name}] Auto-rejoin error: {e}')

@misc_bp.route('/api/inventory', methods=['POST'])
def receive_inventory():
    data = request.json
    acc_name = data.get('account', '')
    items = data.get('items', [])
    sheckles = data.get('sheckles', 0)
    if not acc_name:
        return jsonify({'error': 'No account name'}), 400
    item_counts = {}
    for item in items:
        name = item.get('name', 'Unknown')
        count = item.get('count', 1)
        equipped = item.get('equipped', False)
        thumbnail = item.get('thumbnail', '')
        item_id = item.get('id', '')
        category = item.get('category', 'Other')
        # Always use name as key for consistent display
        key = name
        if key not in item_counts:
            item_counts[key] = {'name': name, 'id': item_id, 'count': 0, 'equipped': equipped, 'thumbnail': thumbnail, 'category': category}
        item_counts[key]['count'] += count
        if equipped:
            item_counts[key]['equipped'] = True
        if thumbnail and not item_counts[key]['thumbnail']:
            item_counts[key]['thumbnail'] = thumbnail
    inventory_data[acc_name] = {
        'items': list(item_counts.values()),
        'total': sum(i['count'] for i in item_counts.values()),
        'sheckles': sheckles,
        'updated_at': time.strftime('%H:%M:%S')
    }
    return jsonify({'success': True})

@misc_bp.route('/api/harvest-fruits', methods=['POST'])
def receive_harvest_fruits():
    from fruit_values import FRUIT_VALUES, MUTATION_MULTIPLIERS
    data = request.json
    acc_name = data.get('account', '')
    fruits = data.get('fruits', [])
    if not acc_name:
        return jsonify({'error': 'No account name'}), 400
    
    for f in fruits:
        name = f.get('fruitName', '')
        weight = float(f.get('weight', 0))
        mutation = f.get('mutation', 'None')
        base_info = FRUIT_VALUES.get(name, {})
        base_per_kg = base_info.get('value', 0) if isinstance(base_info, dict) else base_info
        mut_mult = MUTATION_MULTIPLIERS.get(mutation, 1)
        f['value'] = round(base_per_kg * weight * mut_mult)
        f['totalValue'] = f['value'] * f.get('count', 1)
    
    harvested_fruits_data[acc_name] = {
        'fruits': fruits,
        'total_value': sum(f.get('totalValue', f.get('value', 0)) for f in fruits),
        'total_count': sum(f.get('count', 1) for f in fruits),
        'unique_count': len(fruits),
        'updated_at': time.strftime('%H:%M:%S')
    }
    return jsonify({'success': True})

@misc_bp.route('/api/harvest-fruits', methods=['GET'])
def get_harvest_fruits():
    return jsonify(harvested_fruits_data)

@misc_bp.route('/api/inventory', methods=['GET'])
def get_inventory():
    return jsonify(inventory_data)

@misc_bp.route('/api/item-thumbnails', methods=['GET'])
def get_item_thumbnails():
    import json
    thumb_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'item_thumbnails.json')
    try:
        with open(thumb_file, 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@misc_bp.route('/api/item-sell-prices', methods=['GET'])
def get_item_sell_prices():
    import json
    price_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'item_sell_prices.json')
    try:
        with open(price_file, 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@misc_bp.route('/api/game-status', methods=['GET'])
def get_game_status():
    import json
    status_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'game_status_data.json')
    try:
        with open(status_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({
            'weather_events': data.get('weather_events', []),
            'mutations': data.get('mutations', []),
            'seasonal_events': data.get('seasonal_events', []),
            'current_weather': game_state.get('current_weather', None),
            'last_updated': game_state.get('last_weather_update', None)
        })
    except Exception as e:
        return jsonify({'weather_events': [], 'mutations': [], 'seasonal_events': [], 'error': str(e)})

@misc_bp.route('/api/set-weather', methods=['POST'])
def set_weather():
    data = request.json
    weather_name = data.get('weather', None)
    if weather_name:
        game_state['current_weather'] = weather_name
        game_state['last_weather_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        game_state['current_weather'] = None
        game_state['last_weather_update'] = None
    return jsonify({'success': True, 'current_weather': game_state['current_weather']})

@misc_bp.route('/api/push-all-active', methods=['POST'])
def push_script_to_all_active():
    from services.adb import find_adb, adb_connect, adb_check_roblox, auto_push_script_to_vm
    from services.mumu import mumu_vm_cmd
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

def make_script_for(name, url="http://localhost:5000"):
    return f'''-- Dashboard Monitor Script
-- Account: {name}
-- Auto-execute dari Delta Executor

local Players = game:GetService("Players")
local StarterGui = game:GetService("StarterGui")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local LP = Players.LocalPlayer
local URL = "{url}"

local function notify(t, d)
    pcall(function() StarterGui:SetCore("SendNotification", {{Title="Dashboard", Text=t, Duration=d or 5}}) end)
end

local function httpPost(url, data)
    local ok, result = pcall(function()
        if request then
            return request({{Url=url, Method="POST", Headers={{["Content-Type"]="application/json"}}, Body=data}})
        elseif http_request then
            return http_request({{Url=url, Method="POST", Headers={{["Content-Type"]="application/json"}}, Body=data}})
        else
            return HttpService:PostAsync(url, data, Enum.HttpContentType.ApplicationJson)
        end
    end)
    return ok
end

local function httpGet(url)
    local ok, result = pcall(function()
        if request then
            local resp = request({{Url=url, Method="GET"}})
            return resp and resp.Body or nil
        elseif http_request then
            local resp = http_request({{Url=url, Method="GET"}})
            return resp and resp.Body or nil
        else
            return HttpService:GetAsync(url)
        end
    end)
    if ok then return result end
    return nil
end

local function getThumbnail(tool)
    local tex = tool.TextureId or ""
    if tex ~= "" then
        local id = tex:match("%d+")
        if id then
            return "https://thumbnails.roblox.com/v1/assets?assetIds=" .. id .. "&size=150x150&format=Png"
        end
    end
    return ""
end

local function sendInventory()
    local items = {{}}
    
    -- Baca dari MailboxUI (semua items yang bisa dikirim)
    local pg = LP:FindFirstChild("PlayerGui")
    local mailboxUI = pg and pg:FindFirstChild("MailboxUI")
    local frame = mailboxUI and mailboxUI:FindFirstChild("Frame")
    local sendingFrame = frame and frame:FindFirstChild("SendingFrame")
    local itemSendFrame = sendingFrame and sendingFrame:FindFirstChild("ItemSendFrame")
    local scrollingFrames = itemSendFrame and itemSendFrame:FindFirstChild("ScrollingFrames")
    local invFrame = scrollingFrames and scrollingFrames:FindFirstChild("InventoryFrame")
    
    if invFrame then
        for _, child in ipairs(invFrame:GetChildren()) do
            if child:IsA("Frame") and child.Name ~= "ItemFrameTemplate" then
                local cat, key = child.Name:match("^Inv_(.+):(.+)$")
                if cat and key then
                    -- Cari count dan nama dari Backpack
                    local count = 1
                    local displayName = key
                    for _, tool in pairs(LP.Backpack:GetChildren()) do
                        if tool:IsA("Tool") then
                            if cat == "Pets" and tool:GetAttribute("Id") == key then
                                count = tool:GetAttribute("Count") or 1
                                displayName = tool.Name
                                break
                            elseif cat ~= "Pets" and tool.Name == key then
                                count = tool:GetAttribute("Count") or 1
                                displayName = tool.Name
                                break
                            end
                        end
                    end
                    table.insert(items, {{name=displayName, id=key, count=count, category=cat}})
                end
            end
        end
    end
    
    -- Fallback: baca dari Backpack jika MailboxUI tidak ada
    if #items == 0 then
        for _, tool in pairs(LP.Backpack:GetChildren()) do
            if tool:IsA("Tool") then
                local count = tool:GetAttribute("Count") or 1
                table.insert(items, {{name=tool.Name, id="", count=count}})
            end
        end
    end
    
    local sheckles = 0
    local ls = LP:FindFirstChild("leaderstats")
    if ls then
        local sv = ls:FindFirstChild("Sheckles")
        if sv then sheckles = sv.Value end
    end
    local data = HttpService:JSONEncode({{account=LP.Name, items=items, sheckles=sheckles}})
    return httpPost(URL .. "/api/inventory", data)
end

-- ==================== HARVESTED FRUITS SCANNER ====================
local function scanHarvestedFruits()
    local fruits = {{}}
    for _, tool in pairs(LP.Backpack:GetDescendants()) do
        if (tool:IsA("Tool") or tool:IsA("Configuration")) and tool:GetAttribute("HarvestedFruit") == true then
            local fruitName = tool:GetAttribute("FruitName") or tool:GetAttribute("Fruit") or tool.Name
            -- Bersihin nama dari format "[Mutation] [Weightkg]"
            local cleanName = fruitName:gsub("%s*%[.+%]%s*", ""):gsub("%s*%(.+kg%)%s*", ""):gsub("%s*$", "")
            local count = tool:GetAttribute("Count") or 1
            table.insert(fruits, {{
                name = tool.Name,
                fruitName = cleanName,
                mutation = tool:GetAttribute("Mutation") or "None",
                weight = tool:GetAttribute("Weight") or 0,
                id = tool:GetAttribute("Id") or "",
                count = count
            }})
        end
    end
    if #fruits > 0 then
        local data = HttpService:JSONEncode({{account=LP.Name, fruits=fruits}})
        httpPost(URL .. "/api/harvest-fruits", data)
    end
end

-- ==================== MAILBOX HELPER ====================
-- Fungsi ini bisa dipanggil manual dari executor
-- Contoh: _G.MailboxSend(1787101535, "Pets|uuid1,Pets|uuid2,Gnomes|Gnome")

_G.MailboxSend = function(targetId, itemsStr)
    if not targetId or targetId == 0 then
        notify("Target ID required!", 5)
        return
    end
    
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    
    -- Parse items dari string: "Category|Key,Category|Key"
    local items = {{}}
    for pair in itemsStr:gmatch("[^,]+") do
        local cat, key = pair:match("^(.+)|(.+)$")
        if cat and key then
            table.insert(items, {{Category=cat, ItemKey=key, Count=1}})
        end
    end
    
    if #items == 0 then
        notify("No valid items!", 5)
        return
    end
    
    notify("Sending " .. #items .. " items...", 3)
    
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(targetId, items, "Dashboard send")
    end)
    
    if ok and success then
        notify("Sent! " .. tostring(msg), 5)
    else
        notify("Failed: " .. tostring(msg), 5)
    end
    
    return ok, success, msg
end

-- Fungsi untuk kirim semua items dari MailboxUI
_G.MailboxSendAll = function(targetId, categoryFilter)
    if not targetId or targetId == 0 then
        notify("Target ID required!", 5)
        return
    end
    
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    
    -- Ambil items dari MailboxUI
    local allItems = {{}}
    local pg = LP:FindFirstChild("PlayerGui")
    if not pg then notify("No PlayerGui!", 5) return end
    
    local mailboxUI = pg:FindFirstChild("MailboxUI")
    if not mailboxUI then notify("No MailboxUI!", 5) return end
    
    local frame = mailboxUI:FindFirstChild("Frame")
    local sendingFrame = frame and frame:FindFirstChild("SendingFrame")
    local itemSendFrame = sendingFrame and sendingFrame:FindFirstChild("ItemSendFrame")
    local scrollingFrames = itemSendFrame and itemSendFrame:FindFirstChild("ScrollingFrames")
    local invFrame = scrollingFrames and scrollingFrames:FindFirstChild("InventoryFrame")
    
    if not invFrame then notify("No InventoryFrame!", 5) return end
    
    for _, child in ipairs(invFrame:GetChildren()) do
        if child:IsA("Frame") and child.Name ~= "ItemFrameTemplate" then
            local cat, key = child.Name:match("^Inv_(.+):(.+)$")
            if cat and key then
                -- Filter kategori jika ada
                if not categoryFilter or categoryFilter == "" or cat == categoryFilter then
                    table.insert(allItems, {{Category=cat, ItemKey=key, Count=1}})
                end
            end
        end
    end
    
    if #allItems == 0 then
        notify("No items found!", 5)
        return
    end
    
    notify("Sending " .. #allItems .. " items...", 5)
    
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(targetId, allItems, "Dashboard send all")
    end)
    
    if ok and success then
        notify("Sent " .. #allItems .. " items! " .. tostring(msg), 10)
    else
        notify("Failed: " .. tostring(msg), 5)
    end
    
    return ok, success, msg
end

-- Fungsi untuk kirim ke banyak target
_G.MailboxSendMulti = function(targets, itemsStr)
    if not targets or #targets == 0 then
        notify("No targets!", 5)
        return
    end
    
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    
    -- Parse items
    local items = {{}}
    for pair in itemsStr:gmatch("[^,]+") do
        local cat, key = pair:match("^(.+)|(.+)$")
        if cat and key then
            table.insert(items, {{Category=cat, ItemKey=key, Count=1}})
        end
    end
    
    if #items == 0 then
        notify("No valid items!", 5)
        return
    end
    
    local results = {{}}
    for i, target in ipairs(targets) do
        if i > 1 then task.wait(8) end  -- Rate limit
        
        notify("Sending to " .. target.name .. "...", 3)
        local ok, success, msg = pcall(function()
            return mailbox.SendBatch:Fire(target.id, items, "Multi-target send")
        end)
        
        table.insert(results, {{
            target = target.name,
            ok = ok,
            success = success,
            msg = msg
        }})
    end
    
    -- Summary
    local okCount = 0
    for _, r in ipairs(results) do
        if r.success then okCount = okCount + 1 end
    end
    notify("Done! " .. okCount .. "/" .. #targets .. " success", 10)
    
    return results
end

-- Print commands
print("[Dashboard] Script loaded!")
print("[Dashboard] Manual commands:")
print("[Dashboard]   _G.MailboxSend(userId, 'Category|Key,Category|Key')")
print("[Dashboard]   _G.MailboxSendAll(userId, 'Pets')  -- kirim semua Pets")
print("[Dashboard]   _G.MailboxSendMulti({{id=123,name='Player'}}, 'Category|Key')")
print("[Dashboard]   _G.DashboardSendInventory()  -- refresh inventory")

notify("Dashboard loaded!", 5)
local ok = sendInventory()
if ok then
    notify("Inventory sent!", 3)
else
    notify("Send failed!", 5)
end

task.spawn(function()
    while task.wait(30) do
        pcall(function()
            local data = HttpService:JSONEncode({{account=LP.Name, status="active", message="Monitoring..."}})
            httpPost(URL .. "/api/status", data)
        end)
    end
end)

task.spawn(function()
    while task.wait(60) do
        pcall(function() sendInventory() end)
    end
end)

task.spawn(function()
    while task.wait(30) do
        pcall(function() scanHarvestedFruits() end)
    end
end)

-- ==================== COMMAND POLLING ====================
-- Poll dashboard untuk mailbox commands
task.spawn(function()
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    local gifting = networking.Gifting
    
    local function executeMailCommand(cmd)
        if cmd.type == "send_gift" then
            -- Kirim harvested fruit via GiftingSend (UUID-based)
            local targetId = cmd.target_id
            local itemId = cmd.item_id
            local note = cmd.note or "Gift from dashboard"
            
            if not targetId or targetId == 0 or not itemId or itemId == "" then
                local resultData = HttpService:JSONEncode({{success=false, message="Invalid target or item ID"}})
                httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
                return
            end
            
            notify("Gifting " .. itemId .. " -> " .. cmd.target, 5)
            local ok, success, msg = pcall(function()
                return gifting.Send:Fire(targetId, itemId, note)
            end)
            
            local resultMsg = ok and "Gift sent" or "Gift failed: " .. tostring(msg)
            local resultData = HttpService:JSONEncode({{
                success = ok or false,
                message = resultMsg
            }})
            httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
            notify(resultMsg, 5)
            return
        end
        
        -- Gunakan target_id yang sudah di-lookup oleh dashboard
        local targetId = cmd.target_id
        
        if not targetId or targetId == 0 then
            notify("Target ID tidak valid!", 5)
            local resultData = HttpService:JSONEncode({{success=false, message="Invalid target ID"}})
            httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
            return
        end
        
        notify("Mengirim " .. #cmd.items .. " items ke " .. cmd.target .. " (ID: " .. targetId .. ")...", 5)
        
        -- Build items table dengan Count dari inventory
        local items = {{}}
        for _, item in ipairs(cmd.items) do
            local itemKey = item.id and item.id ~= "" and item.id or item.name
            table.insert(items, {{
                Category = item.category or "Other",
                ItemKey = itemKey,
                Count = item.count or 1
            }})
        end
        
        -- Kirim semua items sekaligus dalam 1 batch
        notify("Kirim " .. #items .. " items...", 3)
        
        local note = cmd.note or "Gift from dashboard"
        local ok, success, msg = pcall(function()
            return mailbox.SendBatch:Fire(targetId, items, note)
        end)
        
        local successCount = 0
        local failCount = 0
        
        if ok and success then
            successCount = #items
        else
            failCount = #items
            print("[Mailbox] Gagal: " .. tostring(msg))
        end
        
        -- Report result
        local resultMsg = successCount .. " ok, " .. failCount .. " gagal"
        notify("Selesai! " .. resultMsg, 10)
        print("[Mailbox] " .. resultMsg)
        
        local resultData = HttpService:JSONEncode({{
            success = failCount == 0,
            message = resultMsg
        }})
        httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
    end
    
    while task.wait(5) do  -- Poll setiap 5 detik
        pcall(function()
            local resp = httpGet(URL .. "/api/mailbox/commands?account=" .. LP.Name)
            if resp then
                local data = HttpService:JSONDecode(resp)
                if data.commands and #data.commands > 0 then
                    for _, cmd in ipairs(data.commands) do
                        executeMailCommand(cmd)
                    end
                end
            end
        end)
    end
end)

-- ==================== WEATHER DETECTION ====================
task.spawn(function()
    while task.wait(30) do
        pcall(function()
            local pg = LP:FindFirstChild("PlayerGui")
            if not pg then return end
            
            -- Cari weather indicator di UI
            local weather = nil
            
            for _, gui in ipairs(pg:GetChildren()) do
                if gui:IsA("ScreenGui") then
                    for _, child in ipairs(gui:GetDescendants()) do
                        if child:IsA("TextLabel") then
                            local text = child.Text:lower()
                            if text:find("rain") and not text:find("rainbow") then
                                weather = "Rain"
                            elseif text:find("rainbow") then
                                weather = "Rainbow"
                            elseif text:find("lightning") then
                                weather = "Lightning"
                            elseif text:find("snow") then
                                weather = "Snowfall"
                            elseif text:find("starfall") then
                                weather = "Starfall"
                            elseif text:find("aurora") then
                                weather = "Aurora"
                            elseif text:find("sunburst") then
                                weather = "Sunburst"
                            elseif text:find("blood") then
                                weather = "Bloodlit"
                            end
                        end
                    end
                end
            end
            
            if weather then
                local data = HttpService:JSONEncode({{weather = weather}})
                httpPost(URL .. "/api/set-weather", data)
            end
        end)
    end
end)

-- ==================== DISCONNECT DETECTION ====================
-- Deteksi disconnect/kick dan report ke dashboard
task.spawn(function()
    local lastStatus = "active"
    local checkInterval = 5
    
    while task.wait(checkInterval) do
        pcall(function()
            -- Cek apakah masih di game
            local inGame = false
            pcall(function()
                if LP and LP.Parent and LP.Character then
                    inGame = true
                end
            end)
            
            local newStatus = inGame and "active" or "disconnected"
            
            -- Jika status berubah, report ke dashboard
            if newStatus ~= lastStatus then
                lastStatus = newStatus
                local statusData = HttpService:JSONEncode({{
                    account = LP.Name,
                    status = newStatus,
                    message = newStatus == "disconnected" and "Disconnected from game" or "Reconnected"
                }})
                httpPost(URL .. "/api/status", statusData)
            end
        end)
    end
end)

_G.DashboardSendInventory = sendInventory
'''

@misc_bp.route('/api/generate-mailbox-script', methods=['GET'])
def generate_mailbox_script():
    """Generate mailbox send script for executor"""
    target_id = request.args.get('target_id', '0')
    target_name = request.args.get('target_name', 'Player')
    batch_size = request.args.get('batch_size', '25')
    delay = request.args.get('delay', '8')
    
    script = f'''-- Mailbox Send Script (Bypass 20-item limit)
-- Target: {target_name} (ID: {target_id})
-- Batch Size: {batch_size} | Delay: {delay}s
-- Jalankan script ini di executor untuk mengirim item

local Players = game:GetService("Players")
local StarterGui = game:GetService("StarterGui")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local LP = Players.LocalPlayer

-- ==================== KONFIGURASI ====================
local TARGET_USER_ID = {target_id}  -- Target player UserId
local BATCH_SIZE = {batch_size}      -- Items per batch (bypass 20 limit!)
local DELAY_BETWEEN_BATCHES = {delay}  -- Detik antar batch
-- =====================================================

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
        table.insert(batch, {{
            Category = item.category,
            ItemKey = item.itemKey,
            Count = 1
        }})
    end
    
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(TARGET_USER_ID, batch, "Batch " .. batchNum)
    end)
    
    return ok, success, msg
end

-- Main execution
notify("Loading inventory...", 3)
local allItems = getInventory()
notify("Found " .. #allItems .. " items", 3)

if #allItems == 0 then
    notify("No items to send!", 5)
    return
end

-- Split into batches
local batches = {{}}
for i = 1, #allItems, BATCH_SIZE do
    local batch = {{}}
    for j = i, math.min(i + BATCH_SIZE - 1, #allItems) do
        table.insert(batch, allItems[j])
    end
    table.insert(batches, batch)
end

notify("Sending " .. #batches .. " batches...", 5)

-- Send batches
local successCount = 0
local failCount = 0

for i, batch in ipairs(batches) do
    if i > 1 then
        notify("Waiting " .. DELAY_BETWEEN_BATCHES .. "s...", 2)
        task.wait(DELAY_BETWEEN_BATCHES)
    end
    
    notify("Sending batch " .. i .. "/" .. #batches .. " (" .. #batch .. " items)", 3)
    local ok, success, msg = sendBatch(batch, i)
    
    if ok and success then
        successCount = successCount + 1
        print("[Mailbox] Batch " .. i .. " sent: " .. msg)
    else
        failCount = failCount + 1
        print("[Mailbox] Batch " .. i .. " failed: " .. tostring(msg))
    end
end

-- Summary
local summary = "Done! " .. successCount .. " ok, " .. failCount .. " failed"
notify(summary, 10)
print("[Mailbox] " .. summary)
print("[Mailbox] Total items sent: " .. #allItems)
'''
    
    return jsonify({
        'script': script,
        'filename': f'MailboxSend_{target_name}_{target_id}.luau',
        'target_id': target_id,
        'target_name': target_name,
        'batch_size': batch_size,
        'delay': delay
    })

@misc_bp.route('/api/generate-mailbox-batch-script', methods=['POST'])
def generate_mailbox_batch_script():
    """Generate custom batch mailbox script"""
    data = request.json or {}
    target_id = data.get('target_id', 0)
    target_name = data.get('target_name', 'Player')
    items = data.get('items', [])
    note = data.get('note', '')
    batch_size = data.get('batch_size', 25)
    delay = data.get('delay', 8)
    
    if not target_id:
        return jsonify({'error': 'target_id required'}), 400
    
    # Build items Lua table
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
-- Generated by Dashboard

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

-- Split items into batches
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
    if i > 1 then
        task.wait(DELAY)
    end
    
    notify("Batch " .. i .. "/" .. #batches, 3)
    
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(TARGET_ID, batch, NOTE ~= "" and NOTE or ("Batch " .. i))
    end)
    
    if ok and success then
        successCount = successCount + 1
        print("[Mailbox] Batch " .. i .. " OK: " .. tostring(msg))
    else
        failCount = failCount + 1
        print("[Mailbox] Batch " .. i .. " FAIL: " .. tostring(msg))
    end
end

notify("Done! " .. successCount .. " ok, " .. failCount .. " failed", 10)
print("[Mailbox] SUMMARY: " .. successCount .. " success, " .. failCount .. " failed")
'''
    
    return jsonify({
        'script': script,
        'filename': f'MailboxBatch_{target_name}_{target_id}.luau'
    })

@misc_bp.route('/api/batch/push-script', methods=['POST'])
def batch_push_script():
    """Push script ke semua instance aktif"""
    from services.adb import find_adb, adb_connect, auto_push_script_to_vm
    serials = settings.get('mumu_serials', [''])
    serial = serials[0] if serials else ''
    if not serial:
        return jsonify({'error': 'No ADB serial configured'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500
    results = []
    for acc in accounts:
        pkg = acc.get('package_name', get_package_name(acc.get('mumu_instance', 0)))
        success, result_msg = auto_push_script_to_vm(acc, serial)
        results.append({
            'account': acc['name'],
            'package': pkg,
            'success': success,
            'message': result_msg
        })
    ok_count = sum(1 for r in results if r['success'])
    return jsonify({'success': True, 'results': results, 'pushed': ok_count, 'total': len(results)})

@misc_bp.route('/api/batch/screenshot', methods=['GET'])
def batch_screenshot():
    """Screenshot semua instance"""
    from services.adb import find_adb, adb_connect, adb_screenshot
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
        pkg = acc.get('package_name', get_package_name(acc.get('mumu_instance', 0)))
        data = adb_screenshot(serial)
        if data:
            screenshots[acc['name']] = {
                'package': pkg,
                'image': base64.b64encode(data).decode()
            }
    return jsonify({'screenshots': screenshots, 'count': len(screenshots)})

@misc_bp.route('/api/batch/auto-login', methods=['POST'])
def batch_auto_login():
    """Cookie injection ke semua akun"""
    from services.adb import find_adb, get_serial, adb_connect
    results = []
    for acc in accounts:
        cookie = acc.get('cookie', '')
        if not cookie:
            results.append({'account': acc['name'], 'success': False, 'error': 'No cookie'})
            continue
        instance = acc.get('mumu_instance', 0)
        package = acc.get('package_name', get_package_name(instance))
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
                subprocess.run([adb, '-s', serial, 'shell', 'am', 'start', '-n', f'{package}/.RobloxApp'],
                    capture_output=True, timeout=10)
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
    """Arrange semua floating windows dalam grid"""
    from services.adb import find_adb, adb_connect, adb_cmd
    serials = settings.get('mumu_serials', [''])
    serial = serials[0] if serials else ''
    if not serial:
        return jsonify({'error': 'No ADB serial configured'}), 400
    ok, msg = adb_connect(serial)
    if not ok:
        return jsonify({'error': f'ADB connect failed: {msg}'}), 500
    packages = [a.get('package_name', get_package_name(a.get('mumu_instance', 0))) for a in accounts]
    if not packages:
        return jsonify({'error': 'No accounts configured'}), 400
    r = adb_cmd(['shell', 'wm', 'size'], serial)
    if r and r[0] == 0 and r[1]:
        import re
        m = re.search(r'(\d+)x(\d+)', r[1])
        if m:
            screen_w = int(m.group(1))
            screen_h = int(m.group(2))
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
        x = col * cell_w
        y = row * cell_h
        w = cell_w
        h = cell_h
        try:
            subprocess.run([adb, '-s', serial, 'shell', 'am', 'start', '-n', f'{pkg}/.Activity',
                '--windowingMode', '6'], capture_output=True, timeout=10)
            time.sleep(0.5)
            results.append({'package': pkg, 'position': {'x': x, 'y': y, 'w': w, 'h': h}, 'success': True})
        except Exception as e:
            results.append({'package': pkg, 'success': False, 'error': str(e)})
    return jsonify({
        'success': True,
        'grid': f'{cols}x{rows}',
        'screen': {'w': screen_w, 'h': screen_h},
        'cell': {'w': cell_w, 'h': cell_h},
        'results': results
    })


# ==================== REMOTE MONITOR API ====================
remote_monitors = {}

@misc_bp.route('/api/remote/register', methods=['POST'])
def remote_register():
    data = request.json or {}
    serial = data.get('serial', '')
    packages = data.get('packages', [])
    if not serial or not packages:
        return jsonify({'error': 'serial and packages required'}), 400

    existing_pkgs = {acc.get('package_name') for acc in accounts}
    auto_created = []

    for pkg_info in packages:
        pkg = pkg_info.get('name', '')
        if pkg and pkg not in existing_pkgs:
            acc = {
                'id': str(int(time.time() * 1000000) + hash(pkg) % 100000),
                'name': pkg.split('.')[-1],
                'cookie': '',
                'active': False,
                'status': 'idle',
                'last_joined': None,
                'server_id': '',
                'server_ids': [],
                'mumu_instance': 0,
                'package_name': pkg,
                'auto_join': False,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'remote': True
            }
            with _data_lock:
                accounts.append(acc)
            auto_created.append(pkg)
            log_activity(f'Auto-created account for {pkg}')

    if auto_created:
        save_data()

    account_map = {}
    for acc in accounts:
        pkg = acc.get('package_name', '')
        if pkg:
            account_map[pkg] = acc.get('name', pkg)

    remote_monitors[serial] = {
        'serial': serial,
        'packages': [p.get('name', '') for p in packages],
        'registered_at': time.time(),
        'last_report': 0
    }
    log_activity(f'Remote monitor registered: {serial} ({len(packages)} packages, {len(auto_created)} new)')
    return jsonify({
        'success': True,
        'account_map': account_map,
        'accounts': len(accounts),
        'auto_created': auto_created
    })

@misc_bp.route('/api/remote/monitors', methods=['GET'])
def remote_monitors_list():
    result = []
    for serial, info in remote_monitors.items():
        packages = info.get('packages', [])
        pkg_status = []
        for pkg in packages:
            matched_account = None
            for acc in accounts:
                if acc.get('package_name') == pkg:
                    matched_account = acc.get('name', '')
                    break
            pkg_status.append({
                'package': pkg,
                'account': matched_account or 'Unassigned',
                'has_account': bool(matched_account)
            })
        result.append({
            'serial': serial,
            'packages': pkg_status,
            'registered_at': info.get('registered_at', 0),
            'package_count': len(packages)
        })
    return jsonify({'monitors': result, 'count': len(result)})

@misc_bp.route('/api/remote/cookie', methods=['POST'])
def remote_cookie():
    data = request.json or {}
    package = data.get('package', '')
    cookie = data.get('cookie', '')
    if not package or not cookie:
        return jsonify({'error': 'package and cookie required'}), 400
    for acc in accounts:
        if acc.get('package_name') == package:
            if not acc.get('cookie') or acc['cookie'] == '':
                from models import encrypt_cookie
                acc['cookie'] = encrypt_cookie(cookie)
                acc['status'] = 'cookie_ready'
                save_data()
                log_activity(f'Cookie auto-extracted for {package} -> {acc.get("name", "?")}')
                return jsonify({'success': True, 'account': acc.get('name', ''), 'package': package})
            else:
                return jsonify({'success': True, 'account': acc.get('name', ''), 'package': package, 'note': 'Cookie already set'})
    return jsonify({'error': f'No account for package {package}'}), 404

@misc_bp.route('/api/remote/status', methods=['POST'])
def remote_status():
    data = request.json or {}
    account_name = data.get('account_name', '')
    package = data.get('package', '')
    status = data.get('status', 'unknown')
    tc = data.get('thread_count')
    kicked = data.get('kicked')
    for acc in accounts:
        if acc.get('name') == account_name or acc.get('package_name') == package:
            old_status = acc.get('status', '')
            acc['status'] = status
            if status in ('in_game', 'monitoring', 'connected', 'active'):
                acc['active'] = True
            elif status in ('kicked', 'disconnected', 'error'):
                acc['active'] = False
                if status == 'kicked' and old_status != 'kicked':
                    send_webhook(
                        f'⚠️ {account_name} — KICKED (Remote)',
                        f'Package: {package}\nKicked: {kicked or "unknown"}',
                        0xffaa00,
                        acc.get('verified_avatar')
                    )
            save_data()
            break
    if account_name:
        log_account(account_name, account_name, f'[Remote] {status} (tc={tc}, kicked={kicked})')
    return jsonify({'success': True})

@misc_bp.route('/api/remote/config', methods=['GET'])
def remote_config():
    return jsonify({
        'monitor_interval': settings.get('monitor_interval', 5),
        'rejoin_interval': settings.get('rejoin_interval', 2400),
        'thread_threshold': settings.get('thread_threshold', 80),
        'rejoin_delay': settings.get('rejoin_delay', 3),
        'max_retries': settings.get('max_retries', 5),
        'auto_join_enabled': settings.get('auto_join_enabled', True),
        'current_server': servers[0] if servers else {}
    })

@misc_bp.route('/api/remote/commands', methods=['GET'])
def remote_commands():
    from blueprints.mailbox import mailbox_commands, command_lock
    account = request.args.get('account', '')
    if not account:
        return jsonify({'commands': [], 'count': 0})
    with command_lock:
        pending = [cmd for cmd in mailbox_commands
                   if cmd.get('account') == account and cmd['status'] == 'pending']
    return jsonify({'commands': pending, 'count': len(pending)})

@misc_bp.route('/api/remote/commands/<cmd_id>/complete', methods=['POST'])
def remote_command_complete(cmd_id):
    from blueprints.mailbox import mailbox_commands, mailbox_results, command_lock
    data = request.json or {}
    success = data.get('success', False)
    message = data.get('message', '')
    with command_lock:
        if cmd_id in mailbox_results:
            mailbox_results[cmd_id] = {
                'status': 'completed' if success else 'failed',
                'message': message,
                'completed_at': time.time()
            }
        for cmd in mailbox_commands:
            if cmd['id'] == cmd_id:
                cmd['status'] = 'completed' if success else 'failed'
                break
    return jsonify({'success': True})
