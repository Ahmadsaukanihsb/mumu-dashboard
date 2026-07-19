import json, sys

PLATO_URL = sys.argv[1] if len(sys.argv) > 1 else 'https://auth.platorelay.com/a?d=cCuWtGQJouFcPcmnUfGji5JQT8ORHSo1XsAn8lsEBRCcUVVP1NqKWzFYnMb5tEOQ3D3eVsBH4EKC1gOnfnKkOIuh7kMqSvqrRCCKEqLVkSFMIfMP3jsws9DBXBfMHtDYI7c7smG1GhBQQj1R1qtlqQ2b01rU9MqtcC4bJbcNAkoxqok4y8500cG0wYZ2bMzGF00blZu4qTEVTV0jfUE54JsotdaL0BrggslX4zS9zELqEgBajMwWnnSo2gzOvJHAsCJU33yvulxgrDyod87Pl9UE33GsdyWefAHMyle72HBvB5Scd2sQXO2zo5Ip4go6M3uNlY9cEQiGnOyf03qU8h86P2zNI4qEpHIVcJDq2ofgq6nQg8kfZORZq0K7FDBrh7lUMt2159BHsGGoebpRVISVmhOyQc01QgQrh5vOVxaXwCEwa4AqNybPQf47Gl'

import requests

session = requests.Session()

# First get the main page to get cookies
r = session.get('https://bypass.tools')
print(f'Main page: {r.status_code}')

# Try /api/captcha-config
r = session.get('https://bypass.tools/api/captcha-config')
print(f'Captcha config: {r.json()}')

# Try bypass without captcha
data = {
    'url': PLATO_URL,
    'captchaToken': None,
    'captchaType': None,
    'isPremium': False,
    'key': None,
    'forceRefresh': False
}

headers = {
    'Content-Type': 'application/json',
    'Origin': 'https://bypass.tools',
    'Referer': 'https://bypass.tools/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

r = session.post('https://bypass.tools/api/bypass', json=data, headers=headers)
print(f'\nBypass API response ({r.status_code}):')
try:
    print(json.dumps(r.json(), indent=2))
except:
    print(r.text[:500])
