from services.adb import auto_push_script_to_vm
import json

with open('data.json') as f:
    data = json.load(f)

accounts = data.get('accounts', [])
serials = data.get('settings', {}).get('mumu_serials', [])

for idx, serial in enumerate(serials):
    if not serial.strip():
        continue
    acc = next((a for a in accounts if a.get('mumu_instance') == idx and a.get('cookie')), None)
    if not acc:
        print(f'Instance {idx}: no account')
        continue
    name = acc.get('name', '?')
    print(f'Instance {idx} ({name}): pushing script via ADB...')
    success, msg = auto_push_script_to_vm(acc, serial.strip())
    print(f'  Result: {success} - {msg}')
