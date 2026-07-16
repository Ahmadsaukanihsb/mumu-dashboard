import json, time, urllib.request, urllib.error, urllib.parse

from flask import Blueprint, render_template, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from models import settings
from config import AUTH_PASSWORD_KEY, PUBLIC_ROUTES

auth_bp = Blueprint('auth', __name__)

DISCORD_AUTH_URL = 'https://discord.com/api/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_USER_URL = 'https://discord.com/api/users/@me'
DISCORD_GUILD_URL = 'https://discord.com/api/users/@me/guilds'

_login_attempts = {}

@auth_bp.route('/login', methods=['GET'])
def login_page():
    if session.get('authenticated'):
        return render_template('index.html')
    return render_template('login.html')

@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    ip = request.remote_addr or 'unknown'
    now = time.time()
    attempts, first = _login_attempts.get(ip, (0, now))
    if attempts >= 5 and now - first < 300:
        return jsonify({'error': 'Too many attempts. Try again in 5 minutes.'}), 429
    if now - first > 300:
        attempts = 0
        first = now
    data = request.json
    pwd = settings.get(AUTH_PASSWORD_KEY, '')
    if not pwd:
        session['authenticated'] = True
        return jsonify({'success': True})
    if data and data.get('password'):
        try:
            if check_password_hash(pwd, data['password']):
                _login_attempts.pop(ip, None)
                session['authenticated'] = True
                return jsonify({'success': True})
            else:
                _login_attempts[ip] = (attempts + 1, first)
                return jsonify({'error': 'Wrong password'}), 403
        except Exception:
            # Hash format is invalid, reject login
            _login_attempts[ip] = (attempts + 1, first)
            return jsonify({'error': 'Invalid password configuration'}), 500
    _login_attempts[ip] = (attempts + 1, first)
    return jsonify({'error': 'Wrong password'}), 403

@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('authenticated', None)
    return jsonify({'success': True})

@auth_bp.route('/api/auth-status', methods=['GET'])
def api_auth_status():
    password = settings.get(AUTH_PASSWORD_KEY, '')
    has_discord = bool(settings.get('discord_client_id') and settings.get('discord_client_secret'))
    return jsonify({
        'authenticated': session.get('authenticated', False),
        'has_password': bool(password),
        'has_discord': has_discord,
        'discord_username': session.get('discord_username')
    })

@auth_bp.route('/api/auth/discord')
def auth_discord():
    cid = settings.get('discord_client_id')
    if not cid:
        return jsonify({'error': 'Discord not configured'}), 400
    redirect_uri = request.url_root.rstrip('/') + '/api/auth/discord/callback'
    session['discord_redirect_uri'] = redirect_uri
    params = urllib.parse.urlencode({
        'client_id': cid,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'identify guilds'
    })
    return jsonify({'redirect': f'{DISCORD_AUTH_URL}?{params}'})

@auth_bp.route('/api/auth/discord/callback')
def auth_discord_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    if error or not code:
        return render_template('login.html', discord_error='Login dibatalkan atau gagal')
    cid = settings.get('discord_client_id')
    secret = settings.get('discord_client_secret')
    if not cid or not secret:
        return render_template('login.html', discord_error='Discord not configured')
    redirect_uri = session.pop('discord_redirect_uri', None) or (request.url_root.rstrip('/') + '/api/auth/discord/callback')

    data = urllib.parse.urlencode({
        'client_id': cid,
        'client_secret': secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }).encode()
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(DISCORD_TOKEN_URL, data=data, headers=headers)
    try:
        res = urllib.request.urlopen(req, timeout=10)
        token_data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        print(f'[DISCORD TOKEN ERROR] HTTP {e.code}: {e.read().decode(errors="replace")}')
        return render_template('login.html', discord_error=f'Token exchange failed (HTTP {e.code})')
    except Exception as e:
        print(f'[DISCORD TOKEN ERROR] {e}')
        return render_template('login.html', discord_error=f'Token exchange failed: {e}')
    access_token = token_data.get('access_token')
    if not access_token:
        return render_template('login.html', discord_error='No access token')
    req2 = urllib.request.Request(DISCORD_USER_URL, headers={'Authorization': f'Bearer {access_token}', 'User-Agent': 'Mozilla/5.0'})
    try:
        res2 = urllib.request.urlopen(req2, timeout=10)
        user = json.loads(res2.read())
    except Exception as e:
        return render_template('login.html', discord_error='Failed to get user info')
    guild_id = settings.get('discord_guild_id')
    if guild_id:
        req3 = urllib.request.Request(DISCORD_GUILD_URL, headers={'Authorization': f'Bearer {access_token}', 'User-Agent': 'Mozilla/5.0'})
        try:
            res3 = urllib.request.urlopen(req3, timeout=10)
            guilds = json.loads(res3.read())
            if not any(g['id'] == guild_id for g in guilds):
                return render_template('login.html', discord_error='Kamu bukan member server Discord ini')
        except:
            return render_template('login.html', discord_error='Failed to verify guild membership')
    session['authenticated'] = True
    session['discord_username'] = user.get('username', 'Unknown')
    session['discord_avatar'] = user.get('avatar', '')
    session['discord_id'] = user.get('id', '')
    return render_template('index.html')
