"""
Test the real captured URL from Delta against the platoboost API
"""
import requests, json, urllib.parse, re, time

CAPTURED_URL = 'https://auth.platorelay.com/a?d=SwLj0tAjs4kmgV1uybKATDBXUwnEK5gxhUQJ32MnAsyDXhkPLm9TBfTTmgJh56ssiWYU0bjoJY7LnfdEr321ULYU8uE5WGdvDRVWB6127h6be8nMerBfU3'

# Parse URL
parsed = urllib.parse.urlparse(CAPTURED_URL)
params = urllib.parse.parse_qs(parsed.query)
d_val = params.get('d', [''])[0]
print(f'URL: {CAPTURED_URL}')
print(f'd param length: {len(d_val)}')
print(f'd param (first 100): {d_val[:100]}')

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': CAPTURED_URL,
    'Origin': 'https://auth.platorelay.com',
})

# 1. Try ticket=d_val
print('\n1. GET /api/session/status?ticket=d')
try:
    r = s.get('https://auth.platorelay.com/api/session/status', params={'ticket': d_val}, timeout=10)
    print(f'   Status: {r.status_code}')
    print(f'   Response: {r.text[:500]}')
except Exception as e:
    print(f'   Error: {e}')

# 2. Different endpoints
print('\n2. Alternative endpoints:')
endpoints = [
    f'/api/session?a={d_val}',
    f'/api/session/status?d={d_val}',
    f'/api/session/status?a={d_val}',
    f'/api/session/status/{d_val}',
    f'/api/v1/authenticators/8/{d_val}',
    f'/api/session?ticket={d_val}',
    '/api/session/status?' + urllib.parse.urlencode({'d': d_val}),
    '/api/session?' + urllib.parse.urlencode({'d': d_val}),
    '/api/session/status?' + urllib.parse.urlencode({'ticket': d_val}),
    '/api/session?' + urllib.parse.urlencode({'ticket': d_val}),
]
seen = set()
for ep in endpoints:
    if ep in seen:
        continue
    seen.add(ep)
    try:
        r = s.get('https://auth.platorelay.com' + ep, timeout=10)
        if r.text and len(r.text) > 10:
            print(f'   {ep[:80]}')
            print(f'     Status: {r.status_code}, Response: {r.text[:300]}')
    except Exception as e:
        print(f'   {ep[:80]} -> Error: {e}')

# 3. Load the actual page and check what JS calls it makes
print('\n3. Loading SPA page...')
r = s.get(CAPTURED_URL, timeout=10)
body = r.text
print(f'   Status: {r.status_code}')
print(f'   Body len: {len(body)}')

# Check for API URLs in the HTML
for m in re.finditer(r'/api/[^"\']+', body):
    print(f'   API path in HTML: {m.group(0)[:100]}')

# Check for fetch/axios calls  
for m in re.finditer(r'fetch\(["\']([^"\']+)["\']', body):
    print(f'   fetch: {m.group(1)[:150]}')

# Check for the actual API URL that the SPA would call
# Maybe the ticket is derived differently
print('\n4. Maybe the ticket is embedded differently...')
# The d param might need to be decoded (base64?)
import base64
try:
    # Try base64 decode
    decoded = base64.b64decode(d_val + '==')
    print(f'   Base64 decoded: {decoded[:200]}')
except:
    print('   Not simple base64')

# Try URL-safe base64
try:
    decoded = base64.urlsafe_b64decode(d_val + '==')
    print(f'   URL-safe base64 decoded: {decoded[:200]}')
except:
    print('   Not URL-safe base64')

# The d value is exactly 160 chars - could be hex?
try:
    decoded = bytes.fromhex(d_val)
    print(f'   Hex decoded: {decoded[:100]}')
except:
    print('   Not hex')

# Try first 32 chars as ticket
print(f'\n5. Try first 10 chars as ticket: {d_val[:10]}')
r = s.get('https://auth.platorelay.com/api/session/status', params={'ticket': d_val[:10]}, timeout=10)
print(f'   Status: {r.status_code}, Response: {r.text[:200]}')
