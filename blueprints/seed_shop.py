import json, time

from flask import Blueprint, jsonify, request

from models import log_activity

seed_shop_bp = Blueprint('seed_shop', __name__)

seed_shop_config = {}
seed_shop_status = {}

SEED_LIST = [
    {"id": "bamboo", "name": "Bamboo", "price": 50, "rarity": "Uncommon"},
    {"id": "carrot", "name": "Carrot", "price": 10, "rarity": "Common"},
    {"id": "strawberry", "name": "Strawberry", "price": 5, "rarity": "Common"},
    {"id": "blueberry", "name": "Blueberry", "price": 15, "rarity": "Common"},
    {"id": "tomato", "name": "Tomato", "price": 8, "rarity": "Common"},
    {"id": "corn", "name": "Corn", "price": 25, "rarity": "Rare"},
    {"id": "pineapple", "name": "Pineapple", "price": 30, "rarity": "Rare"},
    {"id": "apple", "name": "Apple", "price": 20, "rarity": "Uncommon"},
    {"id": "banana", "name": "Banana", "price": 35, "rarity": "Epic"},
    {"id": "grape", "name": "Grape", "price": 45, "rarity": "Epic"},
    {"id": "mango", "name": "Mango", "price": 60, "rarity": "Epic"},
    {"id": "coconut", "name": "Coconut", "price": 50, "rarity": "Epic"},
    {"id": "dragonfruit", "name": "Dragon Fruit", "price": 100, "rarity": "Legendary"},
    {"id": "cherry", "name": "Cherry", "price": 80, "rarity": "Legendary"},
    {"id": "acorn", "name": "Acorn", "price": 40, "rarity": "Legendary"},
    {"id": "sunflower", "name": "Sunflower", "price": 150, "rarity": "Legendary"},
    {"id": "cactus", "name": "Cactus", "price": 30, "rarity": "Rare"},
    {"id": "tulip", "name": "Tulip", "price": 25, "rarity": "Uncommon"},
    {"id": "greenbean", "name": "Green Bean", "price": 12, "rarity": "Epic"},
    {"id": "baby_cactus", "name": "Baby Cactus", "price": 45, "rarity": "Rare"},
    {"id": "horned_melon", "name": "Horned Melon", "price": 55, "rarity": "Rare"},
    {"id": "bamboo_rare", "name": "Bamboo (Rare)", "price": 200, "rarity": "Rare"},
    {"id": "glow_mushroom", "name": "Glow Mushroom", "price": 120, "rarity": "Epic"},
    {"id": "mushroom", "name": "Mushroom", "price": 80, "rarity": "Epic"},
    {"id": "poison_apple", "name": "Poison Apple", "price": 300, "rarity": "Mythic"},
    {"id": "pomegranate", "name": "Pomegranate", "price": 250, "rarity": "Mythic"},
    {"id": "ghost_pepper", "name": "Ghost Pepper", "price": 400, "rarity": "Mythic"},
    {"id": "venus_flytrap", "name": "Venus Fly Trap", "price": 500, "rarity": "Mythic"},
    {"id": "fire_fern", "name": "Fire Fern", "price": 180, "rarity": "Legendary"},
    {"id": "poison_ivy", "name": "Poison Ivy", "price": 350, "rarity": "Legendary"},
]

@seed_shop_bp.route('/api/seed-shop/seeds', methods=['GET'])
def get_seed_list():
    return jsonify({'seeds': SEED_LIST})

@seed_shop_bp.route('/api/seed-shop/config', methods=['GET'])
def get_seed_shop_config():
    return jsonify({'config': seed_shop_config, 'status': seed_shop_status})

@seed_shop_bp.route('/api/seed-shop/config', methods=['POST'])
def update_seed_shop_config():
    data = request.json or {}
    seed_shop_config.update(data)
    log_activity(f'Seed shop config updated: {len(data)} seeds configured')
    return jsonify({'success': True, 'config': seed_shop_config})

@seed_shop_bp.route('/api/seed-shop/status', methods=['POST'])
def receive_seed_shop_status():
    data = request.json or {}
    account = data.get('account', '')
    bought = data.get('bought', [])
    failed = data.get('failed', [])
    seed_shop_status[account] = {
        'bought': bought,
        'failed': failed,
        'updated_at': time.strftime('%H:%M:%S')
    }
    if bought:
        log_activity(f'[{account}] Auto-bought {len(bought)} seeds')
    return jsonify({'success': True})
