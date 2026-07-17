import os
import sys
import platform
import secrets

IS_TERMUX = 'TERMUX_VERSION' in os.environ or os.path.exists('/data/data/com.termux')
IS_ANDROID = platform.system() == 'Linux' and os.path.exists('/system/build.prop')
IS_ARM = platform.machine() in ('aarch64', 'arm64', 'armv7l', 'armv8l')

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, 'data.json')
BACKUP_FILE = DATA_FILE + '.bak'

PACKAGE_MAP = {
    0: 'com.roblox.client',
    1: 'com.roblox.client.clone1',
    2: 'com.roblox.client.clone2',
    3: 'com.roblox.client.clone3',
    4: 'com.roblox.client.clone4',
}

AUTH_PASSWORD_KEY = 'dashboard_password'
PUBLIC_ROUTES = {'/login', '/api/login', '/api/auth-status', '/api/auth/discord', '/api/auth/discord/callback', '/api/status', '/api/inventory', '/api/item-thumbnails', '/api/item-sell-prices', '/api/game-status', '/api/set-weather', '/static/style.css', '/static/script.js', '/static/manifest.json', '/static/service-worker.js', '/api/harvest-fruits', '/api/push-all-active', '/api/remote/register', '/api/remote/status', '/api/remote/config', '/api/remote/commands', '/api/remote/monitors', '/api/remote/cookie', '/api/seed-shop/config', '/api/seed-shop/status', '/api/seed-shop/seeds'}

FLASK_SECRET = os.environ.get('FLASK_SECRET') or secrets.token_hex(32)
HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 5000))
DELTA_PKG = 'com.delta.executor'
JOIN_COOLDOWN = 15
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://localhost:5000')
