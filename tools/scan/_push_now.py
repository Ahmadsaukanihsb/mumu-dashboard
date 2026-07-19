from services.adb import auto_push_script_to_vm
import json

with open('data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

accounts = data.get('accounts', [])
serials = data.get('settings', {}).get('mumu_serials', [])

pushed = 0
for idx, serial in enumerate(serials):
    if not serial.strip():
        continue
    acc = next((a for a in accounts if a.get('mumu_instance') == idx and a.get('cookie')), None)
    if not acc:
        continue
    name = acc.get('name', '?')
    success, msg = auto_push_script_to_vm(acc, serial.strip())
    if success:
        pushed += 1
        print(f'  {name}: OK')
    else:
        print(f'  {name}: {msg}')

print(f'Pushed: {pushed}')
