import re, json, sys

URL = sys.argv[1] if len(sys.argv) > 1 else input('URL: ')

from playwright.sync_api import sync_playwright

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
    page.goto(URL, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)

    print('=== INITIAL STATE ===')
    btns = page.evaluate("""() => 
        Array.from(document.querySelectorAll('button')).map(e => ({
            text: e.innerText.replace(/\\n/g, ' | ').trim().slice(0,80),
            disabled: e.disabled,
            visible: e.offsetParent !== null
        }))
    """)
    for b in btns:
        print(f'  button: "{b["text"]}" disabled={b["disabled"]}')

    # Wait for 3 second timer to finish
    print('\n=== WAITING FOR TIMER (10s max)... ===')
    for i in range(10):
        page.wait_for_timeout(1000)
        btns = page.evaluate("""() => 
            Array.from(document.querySelectorAll('button')).map(e => ({
                text: e.innerText.replace(/\\n/g, ' | ').trim().slice(0,80),
                disabled: e.disabled
            }))
        """)
        for b in btns:
            print(f'  t={i+1}s button: "{b["text"]}" disabled={b["disabled"]}')
        # Check if any button has "continue" or is enabled
        enabled_btns = [b for b in btns if not b['disabled']]
        if enabled_btns:
            print(f'\n  Found enabled button(s)!')
            break

    print('\n=== CLICKING ENABLED BUTTON ===')
    page.evaluate("""() => {
        const b = Array.from(document.querySelectorAll('button')).find(e => !e.disabled);
        if(b) { b.click(); console.log('Clicked:', b.innerText); }
    }""")
    page.wait_for_timeout(3000)

    print('\n=== AFTER CLICK ===')
    print(f'URL: {page.url[:150]}')
    print(f'Pages open: {len(ctx.pages)}')
    
    # Check for popup
    for p in ctx.pages:
        if p != page:
            print(f'Popup URL: {p.url[:150]}')
    
    input('Tekan Enter...')
    browser.close()
