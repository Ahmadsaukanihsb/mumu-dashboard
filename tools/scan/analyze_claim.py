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

    # Get the 35.js source
    js35 = page.evaluate("""async () => {
        const r = await fetch('/35.js');
        return await r.text();
    }""")
    
    # Find key sections around "Claim Reward", "Mission Complete", "&key=", "redirect"
    keywords = ['Claim Reward', 'Mission Complete', '&key=', 'redirectToPublisher', 'unlock-ready-text', 'lkjlsdfiujjjasdlkw']
    for kw in keywords:
        if kw in js35:
            idx = js35.index(kw)
            start = max(0, idx - 1000)
            end = min(len(js35), idx + 2000)
            print(f'\n=== CONTEXT AROUND "{kw}" (pos={idx}) ===')
            print(js35[start:end])
            print('\n')

    # Also look for the actual claim handler
    # Search for function patterns near claim reward
    for pattern in ['lkjlsdfiujjjasdlkw', 'unlock-ready-text', 'Mission Complete']:
        if pattern in js35:
            idx = js35.index(pattern)
            # Get a wider context
            start = max(0, idx - 2000)
            end = min(len(js35), idx + 3000)
            # Deobfuscate a bit - replace \x20 with space, \x22 with ", etc.
            snippet = js35[start:end]
            snippet = snippet.replace('\\x20', ' ').replace('\\x22', '"').replace('\\x0a', '\n').replace('\\x27', "'")
            print(f'\n=== DEOBFUSCATED AROUND "{pattern}" ===')
            print(snippet)

    # Look for the function that handles the claim/unlock
    # Search for patterns like ".onclick", "addEventListener", "click", ".click"
    onclick_patterns = re.finditer(r'(?:\.onclick|addEventListener|\.click)\s*[=\(][^;]{0,200}', js35)
    print('\n=== CLICK HANDLER PATTERNS ===')
    for i, m in enumerate(onclick_patterns):
        if i < 20:
            print(f'  {m.group()[:150]}')

    browser.close()
