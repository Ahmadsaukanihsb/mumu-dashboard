import os

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, 'data.json')
BACKUP_FILE = DATA_FILE + '.bak'

AUTH_PASSWORD_KEY = 'dashboard_password'
PUBLIC_ROUTES = {'/login', '/api/login', '/api/auth-status', '/api/auth/discord', '/api/auth/discord/callback', '/api/status', '/api/inventory', '/api/item-thumbnails', '/api/item-sell-prices', '/api/game-status', '/api/set-weather', '/static/style.css', '/static/script.js', '/static/manifest.json', '/static/service-worker.js', '/api/mailbox/commands', '/api/mailbox/commands/'}

FLASK_SECRET = os.environ.get('FLASK_SECRET', 'dash-roblox-secret-change-me')
HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 5000))
DELTA_PKG = 'com.delta.executor'
JOIN_COOLDOWN = 15
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://localhost:5000')
