import re, json, sys

URL = sys.argv[1] if len(sys.argv) > 1 else input('URL: ')

from playwright.sync_api import sync_playwright

requests_log = []

def handle_request(request):
    if request.resource_type in ('xhr', 'fetch') or '/api/' in request.url.lower():
        requests_log.append({
            'url': request.url,
            'method': request.method,
            'resource_type': request.resource_type,
            'headers': dict(request.headers),
            'post_data': request.post_data
        })
        print(f'  [{request.method}] {request.url[:120]}')

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
    page.on('request', handle_request)

    # Step 1: Platoboost
    print('=== STEP 1: Platoboost ===')
    page.goto(URL, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(7000)

    page.evaluate("() => { const b = document.querySelector('button'); if(b) b.click() }")
    page.wait_for_timeout(3000)
    for p in ctx.pages:
        if p != page: p.close()
    page.wait_for_timeout(2000)

    page.evaluate("() => { const b = document.querySelector('button'); if(b) b.click() }")
    page.wait_for_timeout(5000)
    page.wait_for_load_state('domcontentloaded')

    current_url = page.url
    print(f'\nRedirected to: {current_url[:150]}')

    if 'lootlabs' in current_url.lower() or 'links.' in current_url.lower():
        print('\n=== STEP 2: On LootLabs - Network Log ===')
        print(f'\nTotal API/XHR requests captured: {len(requests_log)}')
        print('\n--- All requests ---')
        for r in requests_log:
            print(f'  [{r["method"]}] {r["url"][:130]}')

        print('\n--- Page state ---')
        text = page.evaluate("() => document.body.innerText")
        print(text[:500])

        print('\n--- localStorage keys ---')
        ls = page.evaluate("() => JSON.stringify(Object.entries(localStorage))")
        print(ls[:500])

        print('\n--- sessionStorage keys ---')
        ss = page.evaluate("() => JSON.stringify(Object.entries(sessionStorage))")
        print(ss[:500])

        print('\n--- Cookies ---')
        cookies = ctx.cookies()
        for c in cookies:
            print(f'  {c["name"]} = {c["value"][:50]}')

        input('\nTekan Enter untuk tutup browser...')

    browser.close()
