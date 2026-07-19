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
    
    # Find function definitions in the JS
    # Pattern: name=function or name:function
    print('=== FUNCTION DEFINITIONS ===')
    
    # Search for function definition patterns
    patterns = [
        (r"[\w]+\[['\"](\w+)['\"]\]\s*=\s*function", 'bracket notation'),
        (r"(\w+)\s*:\s*function", 'object method'),
        (r"function\s+(\w+)", 'named function'),
    ]
    
    for pattern, desc in patterns:
        matches = re.findall(pattern, js35)
        if matches:
            # Filter to unique names related to our interest
            interesting = [m for m in set(matches) if any(kw in m.lower() for kw in ['success', 'reward', 'claim', 'unlock', 'complete', 'done', 'generate', 'modal', 'redirect', 'remove', 'content', 'blocker', 'ready', 'finish'])]
            if interesting:
                print(f'\n  {desc}:')
                for m in interesting:
                    print(f'    {m}')
    
    # Look for 'generateSucceedModal' definition in the JS
    idx = js35.find('generateSucceedModal')
    if idx >= 0:
        start = max(0, idx - 500)
        end = min(len(js35), idx + 1500)
        print(f'\n=== AROUND generateSucceedModal (pos={idx}) ===')
        snippet = js35[start:end].replace('\\x20', ' ').replace('\\x22', '"').replace('\\x27', "'")
        print(snippet)
    
    # Look for 'redirectToPublisherLink' definition
    idx2 = js35.find('redirectToPublisherLink')
    if idx2 >= 0:
        start = max(0, idx2 - 500)
        end = min(len(js35), idx2 + 1500)
        print(f'\n=== AROUND redirectToPublisherLink (pos={idx2}) ===')
        snippet = js35[start:end].replace('\\x20', ' ').replace('\\x22', '"').replace('\\x27', "'")
        print(snippet)

    browser.close()
