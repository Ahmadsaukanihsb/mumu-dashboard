import pytesseract
from PIL import Image
import json

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

img = Image.open(r'C:\Users\Administrator\Desktop\Dashboard Roblox\vm_screenshot.png')
w, h = img.size

data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

print(f"Image: {w}x{h}")
print(f"\n{'LINE':<6} {'LEFT':<6} {'TOP':<6} {'WIDTH':<7} {'HEIGHT':<8} {'CONF':<6} TEXT")
print("="*80)

regions = []
for i in range(len(data['text'])):
    text = data['text'][i].strip()
    if not text:
        continue
    line = data['line_num'][i]
    x, y, bw, bh = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
    conf = data['conf'][i]
    print(f"{line:<6} {x:<6} {y:<6} {bw:<7} {bh:<8} {conf:<6} {text}")
    regions.append({
        'text': text, 'line': line,
        'x': x, 'y': y, 'w': bw, 'h': bh,
        'cx': x + bw//2, 'cy': y + bh//2,
        'conf': conf
    })

# Check bottom half of screen in detail
print(f"\n=== TEXT IN BOTTOM HALF (y > {h//2}) ===")
for r in regions:
    if r['y'] >= h//2:
        print(f"  @({r['cx']},{r['cy']}) '{r['text']}' [{r['w']}x{r['h']}]")

# Check right side
print(f"\n=== TEXT IN RIGHT THIRD (x > {w*2//3}) ===")
for r in regions:
    if r['x'] >= w*2//3:
        print(f"  @({r['cx']},{r['cy']}) '{r['text']}' [{r['w']}x{r['h']}]")

with open(r'C:\Users\Administrator\Desktop\Dashboard Roblox\ocr_result.json', 'w') as f:
    json.dump({'image_size': [w, h], 'regions': regions}, f, indent=2)
