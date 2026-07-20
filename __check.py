import urllib.request, json, urllib.parse

# Test the actual API response for each server
codes = {
    'Grow a Garden 2': '08285ab0e3dd9b4c82a835d86c55f5c5',
    'farm': '1a93f4af708bf542a0ac0a7d1e3ea510',
    'VIP1': 'e091a5afaf2aae48977466ba9c86b6ce',
    'gacha': '7dc8c4b8ab875c4d9efb49562f8ab2ff',
}

for name, code in codes.items():
    url = f'https://games.roblox.com/v1/games/97598239454123/servers/Private?sortOrder=Asc&limit=10&privateServerLinkCode={urllib.parse.quote(code)}'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Roblox/Win32')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            servers = data.get('data', [])
            if servers:
                for srv in servers:
                    gid = srv.get('id', '')
                    name_tok = srv.get('name', '')
                    player_cap = srv.get('playerCapacity', '')
                    playing = srv.get('playing', '')
                    print(f'{name}: gid={gid}, server_name={name_tok}, capacity={player_cap}, playing={playing}')
            else:
                print(f'{name}: NO SERVERS FOUND (data empty)')
    except Exception as e:
        print(f'{name}: ERROR: {e}')
