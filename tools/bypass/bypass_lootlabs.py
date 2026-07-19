import re
import sys

TEST_URL = sys.argv[1] if len(sys.argv) > 1 else None
if not TEST_URL:
    TEST_URL = input('Paste Platoboost URL: ').strip()
if not TEST_URL:
    print('No URL provided')
    sys.exit(1)

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
    )
    page = ctx.new_page()

    print('[1/6] Buka Platoboost...')
    page.goto(TEST_URL, wait_until='domcontentloaded', timeout=30000)

    print('[2/6] Tunggu 7s biar button enable...')
    page.wait_for_timeout(7000)

    print('[3/6] Klik Continue...')
    page.evaluate("() => { const b = document.querySelector('button'); if(b){b.click()} }")
    page.wait_for_timeout(3000)
    for p in ctx.pages:
        if p != page:
            print(f'  Close popup: {p.url[:70]}')
            p.close()

    print('  Klik Continue lagi...')
    page.evaluate("() => { const b = document.querySelector('button'); if(b){b.click()} }")
    page.wait_for_timeout(5000)
    page.wait_for_load_state('domcontentloaded')
    print(f'  URL skrg: {page.url[:100]}')

    if 'lootlabs' in page.url.lower() or 'links.' in page.url.lower():
        print('[4/6] Klik task Register...')
        page.evaluate("() => { const divs = document.querySelectorAll('div'); for (const d of divs) { if (d.textContent.includes('Register') && d.textContent.includes('Bet')) { d.click(); break } } }")
        page.wait_for_timeout(2000)
        for p in ctx.pages:
            if p != page:
                print(f'  Close popup: {p.url[:70]}')
                p.close()

        print('  Klik task Get an App...')
        page.evaluate("() => { const divs = document.querySelectorAll('div'); for (const d of divs) { if (d.textContent.includes('Get an App')) { d.click(); break } } }")
        page.wait_for_timeout(2000)
        for p in ctx.pages:
            if p != page:
                print(f'  Close popup: {p.url[:70]}')
                p.close()

        print('[5/6] Tunggu 70 detik timer...')
        page.wait_for_timeout(70000)

        print('[6/6] Klik Claim Reward...')
        page.evaluate("() => { const btns = document.querySelectorAll('button'); for (const b of btns) { if (b.textContent.includes('Claim Reward')) { b.click(); break } } }")
        page.wait_for_timeout(5000)

        text = page.evaluate("() => document.body.innerText")
        print(f'\n--- PAGE TEXT ---\n{text[:1000]}')
        km = re.search(r'[A-Z0-9_\-]{25,50}', text)
        if km:
            print(f'\n*** KEY: {km.group(0)} ***')
        else:
            km2 = re.search(r'[A-Z0-9_\-]{25,50}', page.url)
            if km2:
                print(f'\n*** KEY in URL: {km2.group(0)} ***')
            else:
                print('\nNo key ditemukan')
    elif 'platorelay' in page.url.lower():
        print('Masih di Platoboost (mungkin perlu interaksi manual)')
    else:
        print(f'Redirect ke: {page.url[:120]}')

    browser.close()
    print('\nSelesai')
