import pytesseract
from PIL import Image
import json

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

img = Image.open(r'C:\Users\Administrator\Desktop\Dashboard Roblox\vm_screenshot.png')
w, h = img.size

# PSM 6 - single uniform block
data = pytesseract.image_to_data(img, config='--psm 6 --oem 3', output_type=pytesseract.Output.DICT)

print(f"Image: {w}x{h}")
print(f"\n{'LEFT':<6} {'TOP':<6} {'WIDTH':<7} {'HEIGHT':<8} {'CONF':<6} TEXT")
print("="*60)

targets = ['receive', 'continue', 'con\'', 'get key', 'generate']
found = []
for i in range(len(data['text'])):
    text = data['text'][i].strip()
    text_lower = text.lower()
    x, y, bw, bh = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
    conf = data['conf'][i]
    if text:
        print(f"{x:<6} {y:<6} {bw:<7} {bh:<8} {conf:<6} {text}")
    for t in targets:
        if t in text_lower:
            found.append({
                'text': text, 'target': t,
                'x': x, 'y': y, 'w': bw, 'h': bh,
                'cx': x + bw//2, 'cy': y + bh//2,
                'conf': conf
            })

print(f"\n=== TARGET FOUND ===")
for f in found:
    print(f"  '{f['text']}' (match: {f['target']}) @ ({f['cx']},{f['cy']}) box=[{f['x']},{f['y']},{f['w']},{f['h']}] conf={f['conf']}")

# PSM 11 for comparison
data11 = pytesseract.image_to_data(img, config='--psm 11 --oem 3', output_type=pytesseract.Output.DICT)
print(f"\n=== PSM 11 ===")
for i in range(len(data11['text'])):
    text = data11['text'][i].strip()
    text_lower = text.lower()
    x, y, bw, bh = data11['left'][i], data11['top'][i], data11['width'][i], data11['height'][i]
    conf = data11['conf'][i]
    for t in targets:
        if text and t in text_lower:
            print(f"  '{text}' (match: {t}) @ ({x+ bw//2},{y + bh//2}) box=[{x},{y},{bw},{bh}] conf={conf}")

with open(r'C:\Users\Administrator\Desktop\Dashboard Roblox\ocr_coords.json', 'w') as f:
    json.dump({'found': found, 'image_size': [w, h]}, f, indent=2)
