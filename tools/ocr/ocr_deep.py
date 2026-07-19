import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
import json

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

img = Image.open(r'C:\Users\Administrator\Desktop\Dashboard Roblox\vm_screenshot.png')
w, h = img.size
print(f"Image: {w}x{h}")

# Try multiple PSM modes
for psm in [3, 6, 11, 12, 13]:
    config = f'--psm {psm} --oem 3'
    text = pytesseract.image_to_string(img, config=config)
    text_clean = text.strip()
    if text_clean:
        print(f"\n=== PSM {psm} ===")
        print(text_clean)

# Try with preprocessing - enhance contrast
gray = img.convert('L')
enhancer = ImageEnhance.Contrast(gray)
gray = enhancer.enhance(2.0)
# Apply threshold
bw = gray.point(lambda x: 0 if x < 128 else 255)

print("\n=== PSM 6 WITH THRESHOLD ===")
text = pytesseract.image_to_string(bw, config='--psm 6 --oem 3')
print(text.strip())

# Search specifically for: continue, receive, get, generate, key, enter, submit, ok
keywords = ['continue', 'receive', 'get key', 'generate', 'submit', 'next', 'ok', 'menu', 'setting']
data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
print("\n=== SEARCH KEYWORDS ===")
for i in range(len(data['text'])):
    text_lower = data['text'][i].strip().lower()
    for kw in keywords:
        if kw in text_lower:
            x, y, bw_w, bh = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
            print(f"  FOUND '{data['text'][i].strip()}' (match: {kw}) @ ({x},{y}) size={bw_w}x{bh} conf={data['conf'][i]}")
            break
