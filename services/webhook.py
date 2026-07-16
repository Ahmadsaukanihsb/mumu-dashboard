import json, time, urllib.request

from models import settings

def send_webhook(title, description, color=0xff4444, avatar_url=None):
    url = settings.get('webhook_url', '')
    if not url or not settings.get('webhook_enabled'):
        return
    try:
        embed = {
            'title': title,
            'description': description,
            'color': color,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()),
            'footer': {'text': 'Dashboard Roblox'}
        }
        if avatar_url:
            embed['thumbnail'] = {'url': avatar_url}
        data = json.dumps({'embeds': [embed]}).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'DashboardRoblox/1.0'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f'[WEBHOOK ERROR] {e}')
