import json, time, threading
import requests
from flask import Blueprint, jsonify, request
from models import settings, inventory_data, accounts, log_activity

mailbox_bp = Blueprint('mailbox', __name__)

# Command queue for mailbox operations
mailbox_commands = []
mailbox_results = {}
command_lock = threading.Lock()

def lookup_user_id(username):
    """Lookup Roblox User ID from username"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    # Method 1: users.roblox.com API
    try:
        resp = requests.get(
            f'https://users.roblox.com/v1/users/search?keyword={username}&limit=10',
            headers=headers,
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            for user in data.get('data', []):
                if user.get('name', '').lower() == username.lower():
                    return user.get('id', 0)
    except Exception as e:
        print(f"[Mailbox] Lookup method 1 failed: {e}")
    
    # Method 2: api.roblox.com API
    try:
        resp = requests.get(
            f'https://api.roblox.com/users/get-by-username?username={username}',
            headers=headers,
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('Id'):
                return data['Id']
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
        
        # Jika category tidak ada, coba tentukan dari nama
        if category == 'Other':
            name_lower = name.lower()
            if any(x in name_lower for x in ['pet', 'bunny', 'dragon', 'cat', 'dog', 'bird', 'fox', 'bear', 'owl', 'raccoon', 'deer', 'frog', 'monkey', 'turtle']):
                category = 'Pets'
            elif 'gnome' in name_lower:
                category = 'Gnomes'
            elif 'seed' in name_lower:
                category = 'Seeds'
            elif any(x in name_lower for x in ['crate', 'pack', 'egg']):
                category = 'Crates'
            elif 'sprinkler' in name_lower:
                category = 'Sprinklers'
            elif 'watering' in name_lower:
                category = 'WateringCans'
        
        # Gunakan ID (UUID) sebagai identifier utama
        display_name = item_id if item_id else name
        
        mailbox_items.append({
            'name': display_name,
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
