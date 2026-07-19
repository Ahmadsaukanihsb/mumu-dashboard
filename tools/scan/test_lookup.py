import requests, json

username = 'alimskri'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json'
}

print(f'Looking up: {username}')

# Method 1
try:
    resp = requests.get(
        f'https://users.roblox.com/v1/users/search?keyword={username}&limit=10',
        headers=headers,
        timeout=15
    )
    print(f'Method 1: HTTP {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'Found {len(data.get("data", []))} results')
        for user in data.get('data', []):
            print(f'  {user.get("name")} -> ID: {user.get("id")}')
            if user.get('name', '').lower() == username.lower():
                print(f'  MATCH!')
except Exception as e:
    print(f'Method 1 error: {e}')

# Method 2
print('\n--- Method 2 ---')
try:
    resp = requests.get(
        f'https://api.roblox.com/users/get-by-username?username={username}',
        headers=headers,
        timeout=15
    )
    print(f'Method 2: HTTP {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'Response: {json.dumps(data, indent=2)[:300]}')
except Exception as e:
    print(f'Method 2 error: {e}')
