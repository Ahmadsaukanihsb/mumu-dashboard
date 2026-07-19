# Fruit Values dari gag.gg/values/
FRUIT_VALUES = {
    "Rocket Pop": {"value": 22500, "base_weight": 0.8, "rarity": "Legendary"},
    "Mushroom": {"value": 13000, "base_weight": 5, "rarity": "Epic"},
    "Hypno Bloom": {"value": 9500, "base_weight": 9, "rarity": "Super"},
    "Moon Bloom": {"value": 9000, "base_weight": 9, "rarity": "Super"},
    "Venom Spitter": {"value": 3800, "base_weight": 9, "rarity": "Mythic"},
    "Dragon's Breath": {"value": 3400, "base_weight": 7.5, "rarity": "Super"},
    "Venus Fly Trap": {"value": 3000, "base_weight": 3, "rarity": "Mythic"},
    "Ghost Pepper": {"value": 2500, "base_weight": 7.5, "rarity": "Mythic"},
    "Sunflower": {"value": 1750, "base_weight": 6, "rarity": "Legendary"},
    "Poison Ivy": {"value": 1700, "base_weight": 2.1, "rarity": "Legendary"},
    "Pomegranate": {"value": 900, "base_weight": 1.5, "rarity": "Mythic"},
    "Poison Apple": {"value": 900, "base_weight": 2.25, "rarity": "Mythic"},
    "Fire Fern": {"value": 900, "base_weight": 9, "rarity": "Legendary"},
    "Bamboo": {"value": 800, "base_weight": 4, "rarity": "Rare"},
    "Glow Mushroom": {"value": 700, "base_weight": 7, "rarity": "Epic"},
    "Cherry": {"value": 350, "base_weight": 1.5, "rarity": "Legendary"},
    "Acorn": {"value": 200, "base_weight": 1.5, "rarity": "Legendary"},
    "Horned Melon": {"value": 200, "base_weight": 1.125, "rarity": "Rare"},
    "Dragon Fruit": {"value": 150, "base_weight": 3, "rarity": "Legendary"},
    "Mango": {"value": 90, "base_weight": 3, "rarity": "Epic"},
    "Baby Cactus": {"value": 70, "base_weight": 1.5, "rarity": "Rare"},
    "Coconut": {"value": 60, "base_weight": 1.5, "rarity": "Epic"},
    "Tulip": {"value": 60, "base_weight": 0.5, "rarity": "Uncommon"},
    "Grape": {"value": 45, "base_weight": 2, "rarity": "Epic"},
    "Cactus": {"value": 40, "base_weight": 1.5, "rarity": "Rare"},
    "Banana": {"value": 35, "base_weight": 1.5, "rarity": "Epic"},
    "Corn": {"value": 34, "base_weight": 3, "rarity": "Rare"},
    "Pineapple": {"value": 30, "base_weight": 5, "rarity": "Rare"},
    "Apple": {"value": 12, "base_weight": 1.5, "rarity": "Uncommon"},
    "Green Bean": {"value": 10, "base_weight": 0.5, "rarity": "Epic"},
    "Tomato": {"value": 9, "base_weight": 0.9, "rarity": "Uncommon"},
    "Blueberry": {"value": 5, "base_weight": 1.15, "rarity": "Common"},
    "Carrot": {"value": 5, "base_weight": 0.8, "rarity": "Common"},
    "Strawberry": {"value": 3, "base_weight": 1, "rarity": "Common"},
}

# Mutation Multipliers dari gag.gg/values/
MUTATION_MULTIPLIERS = {
    "None": 1,
    "Bloodlit": 70,
    "Ignited": 60,
    "Starstruck": 50,
    "Aurora": 40,
    "Rainbow": 30,
    "Electric": 25,
    "Frozen": 20,
    "Gold": 10,
    "Chained": 8,
}

def calculate_fruits_for_value(target_value, inventory, use_mutation=False, mutation_multiplier=1):
    """
    Hitung kombinasi fruit untuk mencapai target value.
    Mengembalikan list items yang perlu dikirim.
    """
    items_to_send = []
    remaining_value = target_value
    
    # Sort by value (highest first) untuk efisiensi
    sorted_fruits = sorted(FRUIT_VALUES.items(), key=lambda x: x[1]['value'], reverse=True)
    
    for fruit_name, fruit_data in sorted_fruits:
        if remaining_value <= 0:
            break
        
        fruit_value = fruit_data['value'] * mutation_multiplier
        fruit_lower = fruit_name.lower()
        
        # Cari fruit di inventory — coba exact match dulu, lalu partial
        inv_item = None
        for item in inventory:
            item_name = item.get('name', '').lower()
            if item_name == fruit_lower:
                inv_item = item
                break
        if not inv_item:
            for item in inventory:
                item_name = item.get('name', '').lower()
                if fruit_lower in item_name or item_name in fruit_lower:
                    inv_item = item
                    break
        
        if not inv_item:
            continue
        
        available_count = inv_item.get('count', inv_item.get('qty', 0))
        if available_count <= 0:
            continue
        
        # Hitung berapa yang dikirim
        send_count = min(available_count, int(remaining_value / fruit_value))
        
        if send_count > 0:
            items_to_send.append({
                'name': fruit_name,
                'category': inv_item.get('category', 'Seeds'),
                'qty': send_count,
                'value_per_item': fruit_value,
                'total_value': send_count * fruit_value
            })
            remaining_value -= send_count * fruit_value
        
        if remaining_value <= 0:
            break
    
    return items_to_send, remaining_value

def format_value(value):
    """Format value dengan suffix (M, B, T)"""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    else:
        return str(value)
