import json, time, threading
import urllib.request, urllib.error
import uuid as _uuid
from flask import Blueprint, jsonify, request
from models import settings, inventory_data, harvested_fruits_data, accounts, log_activity
from tools.fruit_values import FRUIT_VALUES, calculate_fruits_for_value, format_value

mailbox_bp = Blueprint('mailbox', __name__)

# Command queue for mailbox operations
mailbox_commands = []
mailbox_results = {}
command_lock = threading.Lock()

def lookup_user_id(username):
    """Lookup Roblox User ID from username using urllib"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    # Method 1: POST username lookup (most reliable)
    try:
        body = json.dumps({"usernames": [username], "excludeBannedUsers": False}).encode()
        req = urllib.request.Request(
            'https://users.roblox.com/v1/usernames/users',
            data=body,
            headers=headers,
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            for user in data.get('data', []):
                if user.get('name', '').lower() == username.lower():
                    return user.get('id', 0)
    except Exception as e:
        print(f"[Mailbox] Lookup method 1 failed: {e}")
    
    # Method 2: Search API (fallback)
    try:
        req = urllib.request.Request(
            f'https://users.roblox.com/v1/users/search?keyword={username}&limit=10',
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            for user in data.get('data', []):
                if user.get('name', '').lower() == username.lower():
                    return user.get('id', 0)
    except Exception as e:
        print(f"[Mailbox] Lookup method 2 failed: {e}")
    
    return 0

@mailbox_bp.route('/api/mailbox/inventory', methods=['POST'])
def get_inventory():
    """Get inventory for specific account (hanya yang sudah report)"""
    data = request.json or {}
    account_name = data.get('account', '')
    
    if not account_name:
        return jsonify({'error': 'Pilih akun dulu'}), 400
    
    inv = inventory_data.get(account_name)
    
    if not inv:
        return jsonify({'error': f'Akun {account_name} belum melaporkan inventory. Pastikan script monitor sudah jalan di executor.'}), 400
    
    items = inv.get('items', [])
    
    if not items:
        return jsonify({'error': f'Inventory {account_name} kosong.'}), 400
    
    mailbox_items = []
    for item in items:
        name = item.get('name', '')
        item_id = item.get('id', '')
        count = item.get('count', 1)
        category = item.get('category', 'Other')
        
        # Gunakan category dari monitor script (sudah benar)
        # Jika category kosong, coba tentukan dari nama
        if not category or category == 'Other':
            name_lower = name.lower()
            item_id_lower = (item_id or '').lower()
            if 'pet' in name_lower or 'pet' in item_id_lower:
                category = 'Pets'
            elif 'sprinkler' in name_lower or 'sprinkler' in item_id_lower:
                category = 'Sprinklers'
            elif 'watering' in name_lower or 'watering' in item_id_lower:
                category = 'WateringCans'
            elif 'gnome' in name_lower or 'gnome' in item_id_lower:
                category = 'Gnomes'
            elif 'seed' in name_lower or 'seed' in item_id_lower:
                category = 'Seeds'
            elif 'crate' in name_lower or 'pack' in name_lower or 'egg' in name_lower:
                category = 'Crates'
        
        mailbox_items.append({
            'name': name,
            'id': item_id,
            'qty': count,
            'category': category
        })
    
    return jsonify({
        'items': mailbox_items,
        'account': account_name,
        'total': len(mailbox_items),
        'sheckles': inv.get('sheckles', 0),
        'updated_at': inv.get('updated_at', 'unknown')
    })

@mailbox_bp.route('/api/mailbox/calculate-value', methods=['POST'])
def calculate_value():
    """Hitung kombinasi fruit untuk mencapai target value"""
    data = request.json or {}
    account_name = data.get('account', '')
    target_input = data.get('target_value', 0)
    
    if not account_name:
        return jsonify({'error': 'Pilih akun dulu'}), 400
    
    # Parse target value (support 1m, 50m, 1b, 500k, etc.)
    try:
        if isinstance(target_input, str):
            target_input = target_input.lower().strip()
            if target_input.endswith('b'):
                target_value = float(target_input[:-1]) * 1_000_000_000
            elif target_input.endswith('m'):
                target_value = float(target_input[:-1]) * 1_000_000
            elif target_input.endswith('k'):
                target_value = float(target_input[:-1]) * 1_000
            else:
                target_value = float(target_input)
        else:
            target_value = float(target_input)
    except (ValueError, TypeError):
        return jsonify({'error': 'Format value salah. Contoh: 50m, 1b, 500k'}), 400
    
    if target_value <= 0:
        return jsonify({'error': 'Target value harus > 0'}), 400
    
    inv = inventory_data.get(account_name)
    if not inv:
        return jsonify({'error': f'Akun {account_name} tidak ada'}), 400
    
    items = inv.get('items', [])
    if not items:
        return jsonify({'error': 'Inventory kosong'}), 400
    
    # Hitung kombinasi fruit
    items_to_send, remaining = calculate_fruits_for_value(target_value, items)
    
    total_value = sum(item['total_value'] for item in items_to_send)
    
    return jsonify({
        'success': True,
        'items': items_to_send,
        'target_value': target_value,
        'actual_value': total_value,
        'remaining': remaining,
        'formatted_target': format_value(target_value),
        'formatted_actual': format_value(total_value),
        'items_count': len(items_to_send),
        'total_qty': sum(item['qty'] for item in items_to_send)
    })

@mailbox_bp.route('/api/mailbox/harvest-fruits', methods=['POST'])
def get_harvest_fruits_value():
    """Get harvested fruits value for an account"""
    data = request.json or {}
    account_name = data.get('account', '')
    
    if not account_name:
        return jsonify({'error': 'Pilih akun dulu'}), 400
    
    hf = harvested_fruits_data.get(account_name)
    if not hf or not hf.get('fruits'):
        return jsonify({'error': f'Tidak ada harvest fruits untuk {account_name}'}), 400
    
    fruits = hf['fruits']
    total_value = sum(f.get('totalValue', f.get('value', 0)) for f in fruits)
    total_count = sum(f.get('count', 1) for f in fruits)
    
    from tools.fruit_values import MUTATION_MULTIPLIERS
    for f in fruits:
        mut = f.get('mutation', 'None')
        f['mutation_multiplier'] = MUTATION_MULTIPLIERS.get(mut, 1)
        if 'totalValue' not in f:
            f['totalValue'] = f.get('value', 0) * f.get('count', 1)
    
    return jsonify({
        'success': True,
        'account': account_name,
        'fruits': fruits,
        'total_value': total_value,
        'formatted_value': format_value(total_value),
        'total_count': total_count,
        'unique_count': len(fruits),
        'updated_at': hf.get('updated_at', '')
    })

@mailbox_bp.route('/api/mailbox/accounts', methods=['GET'])
def get_accounts():
    """Get accounts that have reported inventory (script sudah jalan)"""
    result = []
    for name, inv in inventory_data.items():
        # Hanya tampilkan akun yang punya items dan baru update (dalam 5 menit terakhir)
        if inv.get('items'):
            result.append({
                'name': name,
                'items_count': len(inv.get('items', [])),
                'sheckles': inv.get('sheckles', 0),
                'updated_at': inv.get('updated_at', '')
            })
    
    # Sort berdasarkan updated_at terbaru
    result.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    
    return jsonify({
        'accounts': result,
        'total': len(result)
    })

@mailbox_bp.route('/api/mailbox/send', methods=['POST'])
def send_items():
    """Queue send command with User ID lookup"""
    data = request.json or {}
    account = data.get('account', '')
    target_username = data.get('targetUsername', '')
    items = data.get('items', [])
    batch_size = data.get('batchSize', 25)
    note = data.get('note', '')
    
    if not account:
        return jsonify({'error': 'Pilih akun dulu'}), 400
    if not target_username:
        return jsonify({'error': 'Username target required'}), 400
    if not items:
        return jsonify({'error': 'Pilih items dulu'}), 400
    
    # Lookup User ID dari username
    print(f"[Mailbox] Looking up username: {target_username}")
    target_id = lookup_user_id(target_username)
    print(f"[Mailbox] Lookup result: {target_username} -> {target_id}")
    
    if target_id == 0:
        return jsonify({
            'error': f'User "{target_username}" tidak ditemukan. Pastikan username benar (case-sensitive).',
            'suggestion': 'Coba gunakan username yang tepat, contoh: "alimskri" bukan "Alimskri"'
        }), 400
    
    # Generate command ID
    cmd_id = f"mail_{int(time.time() * 1000)}"
    
    # Build items list
    cmd_items = []
    for item in items:
        cmd_items.append({
            'name': item.get('name', ''),
            'id': item.get('id', ''),
            'category': item.get('category', 'Other'),
            'count': item.get('qty', 1)
        })
    
    # Queue command dengan User ID
    command = {
        'id': cmd_id,
        'type': 'send_mail',
        'account': account,
        'target': target_username,
        'target_id': target_id,
        'items': cmd_items,
        'note': note,
        'batch_size': batch_size,
        'timestamp': time.time(),
        'status': 'pending'
    }
    
    with command_lock:
        mailbox_commands.append(command)
        mailbox_results[cmd_id] = {'status': 'pending', 'message': 'Menunggu executor...'}
    
    log_activity(f'[Mailbox] Queued: {len(items)} items → {target_username} (ID: {target_id}) dari {account}')
    
    return jsonify({
        'success': True,
        'command_id': cmd_id,
        'message': f'Command queued untuk {target_username} (ID: {target_id})',
        'items_count': len(items),
        'target': target_username,
        'target_id': target_id
    })

@mailbox_bp.route('/api/mailbox/send-gift', methods=['POST'])
def send_gift():
    """Queue GiftingSend command for harvested fruit"""
    data = request.json or {}
    account = data.get('account', '')
    target_username = data.get('targetUsername', '')
    item_id = data.get('itemId', '')
    note = data.get('note', '')
    
    if not account:
        return jsonify({'error': 'Pilih akun dulu'}), 400
    if not target_username:
        return jsonify({'error': 'Username target required'}), 400
    if not item_id:
        return jsonify({'error': 'Item ID required'}), 400
    
    target_id = lookup_user_id(target_username)
    if target_id == 0:
        return jsonify({'error': f'User "{target_username}" tidak ditemukan'}), 400
    
    cmd_id = f"gift_{_uuid.uuid4().hex[:12]}"

    command = {
        'id': cmd_id,
        'type': 'send_gift',
        'account': account,
        'target': target_username,
        'target_id': target_id,
        'item_id': item_id,
        'note': note or 'Gift from dashboard',
        'timestamp': time.time(),
        'status': 'pending'
    }
    
    with command_lock:
        mailbox_commands.append(command)
        mailbox_results[cmd_id] = {'status': 'pending', 'message': 'Menunggu executor...'}
    
    log_activity(f'[Gift] Queued: {item_id} → {target_username} (ID: {target_id})')
    
    return jsonify({
        'success': True,
        'command_id': cmd_id,
        'message': f'Gift queued for {target_username}',
        'target_id': target_id
    })

@mailbox_bp.route('/api/mailbox/send-gift-batch', methods=['POST'])
def send_gift_batch():
    """Queue multiple gift items as ONE command (1 lookup, 1 queue entry)."""
    data = request.json or {}
    account = data.get('account', '')
    target_username = data.get('targetUsername', '')
    items = data.get('items', [])  # [{'id': '...', 'name': '...', 'note': '...'}, ...]
    note = data.get('note', '')

    if not account:
        return jsonify({'error': 'Pilih akun dulu'}), 400
    if not target_username:
        return jsonify({'error': 'Username target required'}), 400
    if not items:
        return jsonify({'error': 'Items kosong'}), 400

    # Single lookup for all items
    target_id = lookup_user_id(target_username)
    if target_id == 0:
        return jsonify({'error': f'User "{target_username}" tidak ditemukan'}), 400

    cmd_id = f"giftb_{_uuid.uuid4().hex[:12]}"

    gift_items = []
    for item in items:
        iid = item.get('id', '')
        if iid:
            gift_items.append({'id': iid, 'name': item.get('name', iid)})

    if not gift_items:
        return jsonify({'error': 'Tidak ada item dengan ID valid'}), 400

    command = {
        'id': cmd_id,
        'type': 'send_gift_batch',
        'account': account,
        'target': target_username,
        'target_id': target_id,
        'items': gift_items,
        'note': note or 'Gift from dashboard',
        'timestamp': time.time(),
        'status': 'pending'
    }

    with command_lock:
        mailbox_commands.append(command)
        mailbox_results[cmd_id] = {'status': 'pending', 'message': f'Menunggu executor... ({len(gift_items)} items)'}

    log_activity(f'[Gift] Batch queued: {len(gift_items)} items → {target_username} (ID: {target_id})')

    return jsonify({
        'success': True,
        'command_id': cmd_id,
        'message': f'Batch gift queued: {len(gift_items)} items → {target_username}',
        'target_id': target_id,
        'items_count': len(gift_items)
    })

@mailbox_bp.route('/api/mailbox/commands', methods=['GET'])
def get_commands():
    """Get pending commands for monitor script to execute"""
    account = request.args.get('account', '')
    
    if not account:
        return jsonify({'error': 'Account required'}), 400
    
    with command_lock:
        # Get pending commands for this account
        pending = [cmd for cmd in mailbox_commands 
                   if cmd['account'] == account and cmd['status'] == 'pending']
    
    return jsonify({
        'commands': pending,
        'count': len(pending)
    })

@mailbox_bp.route('/api/mailbox/commands/<cmd_id>/complete', methods=['POST'])
def complete_command(cmd_id):
    """Mark command as completed (called by monitor script)"""
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
        
        # Update command status
        for cmd in mailbox_commands:
            if cmd['id'] == cmd_id:
                cmd['status'] = 'completed' if success else 'failed'
                break
    
    return jsonify({'success': True})

@mailbox_bp.route('/api/mailbox/result/<cmd_id>', methods=['GET'])
def get_result(cmd_id):
    """Get command result"""
    with command_lock:
        result = mailbox_results.get(cmd_id, {'status': 'not_found', 'message': 'Command tidak ditemukan'})
    
    return jsonify(result)
