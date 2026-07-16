from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash

from models import settings, _data_lock, log_activity, save_data
from config import AUTH_PASSWORD_KEY
from services.adb import find_adb
from services.mumu import load_vm_display_names
from services.delta import get_active_delta_keys_count

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    s = dict(settings)
    s.pop('dashboard_password', None)
    s.pop('discord_client_secret', None)  # Never expose secrets
    s['_has_password'] = bool(settings.get('dashboard_password', ''))
    s['_has_discord'] = bool(settings.get('discord_client_id') and settings.get('discord_client_secret'))
    s['_adb_found'] = find_adb() is not None
    s['vm_display_names'] = load_vm_display_names()
    s['delta_active_keys'] = get_active_delta_keys_count()
    return jsonify(s)

@settings_bp.route('/api/settings', methods=['PUT'])
def update_settings():
    data = request.json
    keys = ['auto_join_enabled', 'rejoin_delay', 'max_retries',
            'monitor_interval', 'rejoin_interval', 'thread_threshold', 'theme', 'adb_path', 'mumu_serials',
            'webhook_url', 'webhook_enabled', 'auto_restart_vm', 'dashboard_password',
            'delta_auto_key', 'auto_push_script', 'dashboard_url',
            'discord_client_id', 'discord_client_secret', 'discord_guild_id',
            'auto_verify_interval']
    with _data_lock:
        for k in keys:
            if k in data:
                val = data[k]
                if k == 'monitor_interval' and (not isinstance(val, (int, float)) or val < 1):
                    return jsonify({'error': 'monitor_interval minimal 1'}), 400
                if k == 'thread_threshold' and (not isinstance(val, (int, float)) or val < 20 or val > 500):
                    return jsonify({'error': 'thread_threshold harus 20-500'}), 400
                if k == 'rejoin_delay' and (not isinstance(val, (int, float)) or val < 1):
                    return jsonify({'error': 'rejoin_delay minimal 1'}), 400
                if k == 'max_retries' and (not isinstance(val, int) or val < 1):
                    return jsonify({'error': 'max_retries minimal 1'}), 400
                if k == 'rejoin_interval' and (not isinstance(val, (int, float)) or val < 0):
                    return jsonify({'error': 'rejoin_interval tidak valid'}), 400
                if k == 'dashboard_password' and val:
                    val = generate_password_hash(val)
                settings[k] = val
    
    save_data()
    # Don't auto-login on password change - user must login with new password
    log_activity('Pengaturan diperbarui')
    return jsonify(s)
