import sys, json, re

URL = sys.argv[1]

from playwright.sync_api import sync_playwright

all_responses = []
btn_states = []

def on_response(response):
    ct = response.headers.get('content-type', '')
    if 'json' in ct or 'text' in ct:
        body = ''
        try: body = response.text()[:300]
        except: pass
        all_responses.append({
            'status': response.status,
            'url': response.url[:150],
            'body': body
        })

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = ctx.new_page()
    page.on('response', on_response)

    page.goto(URL, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)

    text = page.evaluate("() => document.body.innerText")
    print('=== PAGE TEXT ===')
    print(text[:800])

    # Wait timer
    print('\n=== WAITING TIMER ===')
    for i in range(6):
        page.wait_for_timeout(1000)
        btns = page.evaluate("""() => 
            Array.from(document.querySelectorAll('button')).map(e => ({
                t: e.innerText.replace(/\\n/g,' ').trim().slice(0,60),
                d: e.disabled
            }))
        """)
        if btns:
            btn_states.append(btns)
            print(f'  t={i+1}s: {btns}')

    # Click Continue
    print('\n=== CLICKING CONTINUE ===')
    page.evaluate("() => { const b = document.querySelector('button:not([disabled])'); if(b) b.click() }")
    page.wait_for_timeout(4000)
    
    # Check popups
    print(f'Pages open: {len(ctx.pages)}')
    for p in ctx.pages:
        if p != page:
            print(f'Popup: {p.url[:120]}')
            p.close()
    
    page.wait_for_timeout(3000)
    print(f'URL after first click: {page.url[:150]}')
    text = page.evaluate("() => document.body.innerText")
    print(f'Page text:\n{text[:500]}')

    # Keep clicking Continue and closing popups until we reach LootLabs or give up
    print('\n=== LOOP: CLICK CONTINUE + CLOSE POPUPS ===')
    for attempt in range(5):
        # Close any popups first
        for p in ctx.pages:
            if p != page:
                print(f'  Close popup: {p.url[:80]}')
                p.close()
        
        page.wait_for_timeout(2000)
        
        # Check if we're on LootLabs
        if 'lootlabs' in page.url.lower() or 'links.' in page.url.lower():
            print(f'REACHED LOOTLABS! URL: {page.url[:150]}')
            break
        
        # Find and click enabled button
        btns = page.evaluate("""() => 
            Array.from(document.querySelectorAll('button, a')).filter(e => e.offsetParent)
                .map(e => ({
                    t: e.innerText.replace(/\\n/g,' ').trim().slice(0,60),
                    tag: e.tagName, href: (e.href||'').slice(0,100)
                }))
        """)
        print(f'  Attempt {attempt+1}: {btns}')
        
        # Click Continue button if exists
        clicked = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const cont = btns.find(b => b.innerText.includes('Continue') && !b.disabled);
            if (cont) { cont.click(); return 'Continue'; }
            const anyBtn = btns.find(b => !b.disabled);
            if (anyBtn) { anyBtn.click(); return anyBtn.innerText; }
            return 'nothing';
        }""")
        print(f'  Clicked: {clicked}')
        page.wait_for_timeout(3000)

    print(f'\nFINAL URL: {page.url[:200]}')
    
    # Check if there's a different page context
    for p in ctx.pages:
        print(f'  Page: {p.url[:150]}')

    print(f'\n=== RESPONSES ({len(all_responses)}) ===')
    for r in all_responses:
        print(f'  [{r["status"]}] {r["url"]}')
        if r['body'] and '{' in r['body']:
            try:
                j = json.loads(r['body'])
                print(f'    JSON: {json.dumps(j, indent=2)[:300]}')
            except:
                pass

    browser.close()
