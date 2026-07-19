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
    
    # Search for key patterns in the obfuscated JS
    searches = [
        '.done', 'done', 
        'unlock-ready-text', 'show',
        'go', 
        'classList', 'className',
        'addEventListener', '.click',
        'complete', 'finish', 
        'reward', 'generateSucceedModal',
        'getElementById', 'querySelector',
        'session', 'verify', '&key=', 'redirect'
    ]
    
    print('=== SEARCHING 35.js FOR KEY PATTERNS ===')
    for term in searches:
        positions = [m.start() for m in re.finditer(re.escape(term), js35, re.I)]
        if positions:
            print(f'\n--- "{term}" found at positions: {positions[:5]} ---')
            for pos in positions[:3]:
                start = max(0, pos - 200)
                end = min(len(js35), pos + 200)
                snippet = js35[start:end]
                snippet = snippet.replace('\\x20', ' ').replace('\\x22', '"').replace('\\x27', "'")
                print(f'  pos={pos}: ...{snippet}...')

    browser.close()
