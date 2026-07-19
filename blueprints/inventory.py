import os, json, time, urllib.request

from flask import Blueprint, jsonify, request

from models import accounts, inventory_data, harvested_fruits_data, log_activity
from tools.fruit_values import FRUIT_VALUES, MUTATION_MULTIPLIERS

inventory_bp = Blueprint('inventory', __name__)

game_state = {
    'current_weather': None,
    'last_weather_update': None
}

@inventory_bp.route('/api/inventory', methods=['POST'])
def receive_inventory():
    data = request.json
    acc_name = data.get('account', '')
    items = data.get('items', [])
    sheckles = data.get('sheckles', 0)
    if not acc_name:
        return jsonify({'error': 'No account name'}), 400
    matched_acc = next((a for a in accounts if a.get('name', '').lower() == acc_name.lower()), None)
    if matched_acc:
        acc_name = matched_acc['name']
    item_counts = {}
    for item in items:
        name = item.get('name', 'Unknown')
        count = item.get('count', 1)
        equipped = item.get('equipped', False)
        thumbnail = item.get('thumbnail', '')
        item_id = item.get('id', '')
        category = item.get('category', 'Other')
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

@inventory_bp.route('/api/inventory', methods=['GET'])
def get_inventory():
    return jsonify(inventory_data)

@inventory_bp.route('/api/harvest-fruits', methods=['POST'])
def receive_harvest_fruits():
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

@inventory_bp.route('/api/harvest-fruits', methods=['GET'])
def get_harvest_fruits():
    return jsonify(harvested_fruits_data)

@inventory_bp.route('/api/item-thumbnails', methods=['GET'])
def get_item_thumbnails():
    thumb_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'item_thumbnails.json')
    try:
        with open(thumb_file, 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@inventory_bp.route('/api/item-sell-prices', methods=['GET'])
def get_item_sell_prices():
    price_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'item_sell_prices.json')
    try:
        with open(price_file, 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@inventory_bp.route('/api/game-status', methods=['GET'])
def get_game_status():
    status_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'game_status_data.json')
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

@inventory_bp.route('/api/set-weather', methods=['POST'])
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
