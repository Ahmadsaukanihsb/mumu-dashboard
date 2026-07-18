import os
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS

from config import FLASK_SECRET, AUTH_PASSWORD_KEY, PUBLIC_ROUTES, HOST, PORT, IS_TERMUX
from models import settings, load_data, discover_roblox_packages_on_start
from monitor import start_monitor

app = Flask(__name__)
app.secret_key = FLASK_SECRET
CORS(app)

# Register blueprints
from blueprints.auth import auth_bp
from blueprints.accounts import accounts_bp
from blueprints.servers import servers_bp
from blueprints.settings import settings_bp
from blueprints.delta import delta_bp
from blueprints.mumu import mumu_bp
from blueprints.misc import misc_bp
from blueprints.farm import farm_bp
from blueprints.mailbox import mailbox_bp

app.register_blueprint(auth_bp)
app.register_blueprint(accounts_bp)
app.register_blueprint(servers_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(delta_bp)
app.register_blueprint(mumu_bp)
app.register_blueprint(misc_bp)
app.register_blueprint(farm_bp)
app.register_blueprint(mailbox_bp)

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.before_request
def check_auth():
    password = settings.get(AUTH_PASSWORD_KEY, '')
    if not password:
        return
    # Allow static files
    if request.path.startswith('/static/'):
        return
    # Allow public routes
    if request.path in PUBLIC_ROUTES:
        return
    # Allow specific mailbox endpoints (for monitor script polling)
    mailbox_public = {'/api/mailbox/commands'}
    if request.path in mailbox_public:
        return
    # Check authentication for other routes
    if not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return render_template('login.html')

if __name__ == '__main__':
    load_data()
    from blueprints.misc import start_scheduler
    start_scheduler()
    if IS_TERMUX:
        serials = settings.get('mumu_serials', ['127.0.0.1:5555'])
        if not serials or not serials[0]:
            settings['mumu_serials'] = ['127.0.0.1:5555']
            from models import save_data
            save_data()
        serial = settings['mumu_serials'][0]
        from services.adb import find_adb, adb_connect
        adb = find_adb()
        print(f'Dashboard Roblox (Termux) running on http://0.0.0.0:{PORT}')
        print(f'ADB: {adb or "not found"}')
        print(f'Serial: {serial}')
        if adb:
            ok, msg = adb_connect(serial)
            print(f'ADB Connect: {"OK" if ok else msg}')
            discover_roblox_packages_on_start(serial)
        start_monitor()
    else:
        start_monitor()
        serials = settings.get('mumu_serials', [])
        info = ', '.join([f'#{i}:{s or "?"}' for i, s in enumerate(serials)])
        print(f'Dashboard Roblox running on http://localhost:{PORT}')
        from services.adb import find_adb
        print(f'ADB: {find_adb() or "not found"}')
        print(f'Instances: {info}')
        print(f'Monitor thread started (interval: {settings.get("monitor_interval", 5)}s)')
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
