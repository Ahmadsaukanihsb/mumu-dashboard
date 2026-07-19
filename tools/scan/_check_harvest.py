import requests
resp = requests.get('http://localhost:5000/api/harvest-fruits', timeout=5)
print('Status:', resp.status_code)
data = resp.json()
for acc, hf in data.items():
    print(f'\n=== {acc} ===')
    if isinstance(hf, dict) and hf.get('fruits'):
        for f in hf['fruits']:
            fn = f.get('fruitName', '?')
            mut = f.get('mutation', 'None')
            wt = f.get('weight', 0)
            val = f.get('value', 0)
            print(f'  {fn} [{mut}] ({wt}kg) = {val:,}')
    else:
        print('  No harvest fruits data')
