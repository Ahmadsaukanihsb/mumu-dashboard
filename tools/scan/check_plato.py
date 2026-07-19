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

    print('=== PAGE HTML after load ===')
    html = page.content()
    print(html[:3000])

    print('\n=== VISIBLE TEXT ===')
    text = page.evaluate("() => document.body.innerText")
    print(text[:1000])

    print('\n=== BUTTONS ===')
    btns = page.evaluate("""() => 
        Array.from(document.querySelectorAll('button, a, [role="button"], .btn, input[type="submit"]'))
            .map(e => ({tag: e.tagName, text: e.innerText?.trim()?.slice(0,50), href: e.href || '', id: e.id, cls: e.className?.slice(0,60), display: getComputedStyle(e).display, visible: e.offsetParent !== null}))
    """)
    for b in btns:
        print(f'  {b["tag"]} text="{b["text"]}" visible={b["visible"]} id={b["id"]}')

    input('\nTekan Enter untuk close...')
    browser.close()
