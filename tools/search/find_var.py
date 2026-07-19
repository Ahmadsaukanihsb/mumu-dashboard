import sys, json, re

URL = sys.argv[1]

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()

    page.goto(URL, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(5000)
    for attempt in range(10):
        for p in ctx.pages:
            if p != page:
                p.close()
        page.wait_for_timeout(1000)
        if 'lootlabs' in page.url.lower() or 'links.' in page.url.lower():
            break
        page.evaluate("() => { const b = document.querySelector('button:not([disabled])'); if(b) b.click() }")
        page.wait_for_timeout(2000)
    page.wait_for_timeout(2000)

    # Get 35.js
    js35 = page.evaluate("""async () => {
        const r = await fetch('/35.js');
        return await r.text();
    }""")
    
    # Find the assignment to _0x49342f
    # Search for var/let/const patterns near _0x49342f
    for pattern in [r'_0x49342f', r'_0x35e569', r'var\s+_\w+\s*=\s*\{', r'var\s+_\w+\s*=\s*this', r'_\w+\[["\']']:
        matches = [(m.start(), m.group()) for m in re.finditer(pattern, js35)]
        if matches:
            for pos, text in matches[:5]:
                start = max(0, pos - 100)
                end = min(len(js35), pos + 100)
                print(f'\n{text} at {pos}:')
                print(f'  ...{js35[start:end]}...')
    
    # Also search for the variable _0x49342f definition
    var_patterns = re.finditer(r'(?:var|let|const)\s+(_0x\w+)\s*=', js35)
    print('\n=== VARIABLE DECLARATIONS ===')
    found_49342f = False
    for m in var_patterns:
        varname = m.group(1)
        pos = m.start()
        if varname == '_0x49342f':
            found_49342f = True
            start = max(0, pos - 50)
            end = min(len(js35), pos + 200)
            print(f'FOUND _0x49342f at {pos}:')
            print(f'  {js35[start:end]}')
    
    if not found_49342f:
        print('_0x49342f not declared with var/let/const - checking for direct assignment...')
        # Maybe it's assigned as property of another object
        for m in re.finditer(r'(\w+)\[["\'](\w+)["\']\]\s*=\s*function', js35):
            obj = m.group(1)
            func = m.group(2)
            if func in ('createTasksModal', 'removeLoader', 'generateSucceedModal'):
                print(f'  Function {func} assigned on object: {obj} at {m.start()}')
                start = max(0, m.start() - 200)
                end = min(len(js35), m.start() + 100)
                print(f'  Context: ...{js35[start:end]}...')

    browser.close()
