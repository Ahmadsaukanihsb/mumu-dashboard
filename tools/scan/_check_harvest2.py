import requests
resp = requests.get('http://localhost:5000/api/harvest-fruits', timeout=5)
print('Status:', resp.status_code)
data = resp.json()
for acc, hf in data.items():
    print(f'\n=== {acc} ===')
    if isinstance(hf, dict) and hf.get('fruits'):
        total = 0
        for f in hf['fruits']:
            fn = f.get('fruitName', '?')
            mut = f.get('mutation', 'None')
            wt = f.get('weight', 0)
            val = f.get('totalValue', f.get('value', 0))
            cnt = f.get('count', 1)
            total += val
            print(f'  {fn} [{mut}] {cnt}x {wt:.1f}kg = {val:,}')
        print(f'  TOTAL: {total:,}')
    else:
        print('  No data')
