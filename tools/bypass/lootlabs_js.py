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

    page.wait_for_timeout(3000)

    # Get all external scripts
    scripts = page.evaluate("""() => 
        Array.from(document.querySelectorAll('script[src]')).map(s => s.src)
    """)
    print('=== EXTERNAL SCRIPTS ===')
    for s in scripts:
        print(f'  {s}')
    
    # Get inline scripts with size
    inline = page.evaluate("""() => 
        Array.from(document.querySelectorAll('script:not([src])'))
            .map(s => ({len: (s.textContent||'').length, content: (s.textContent||'').slice(0,200)}))
            .filter(s => s.len > 200)
    """)
    print(f'\n=== INLINE SCRIPTS ({len(inline)}) ===')
    for s in inline:
        print(f'  len={s["len"]}')
        print(f'  {s["content"]}')
    
    # Look at the main lodash/JS bundles for API patterns
    print('\n=== Fetching main JS bundle for API patterns ===')
    for src in scripts:
        if 'app' in src.lower() or 'main' in src.lower() or 'bundle' in src.lower() or '.js' in src:
            content = page.evaluate(f"""async (url) => {{
                try {{
                    const r = await fetch(url);
                    return await r.text();
                }} catch(e) {{ return ''; }}
            }}""", src)
            if content:
                apis = re.findall(r'["\'](/[a-z]+(?:/[a-z]+)+)["\']', content)
                if apis:
                    print(f'\n  From {src.split("/")[-1][:50]}:')
                    for a in sorted(set(apis)):
                        if not any(x in a for x in ['.js', '.css', '.png', '.svg', '.ico', '//']):
                            print(f'    {a}')
                
                # Look for fetch/xhr patterns
                fetch_urls = re.findall(r'fetch\(["\']([^"\']+)["\']', content)
                if fetch_urls:
                    print(f'  Fetch URLs:')
                    for f in set(fetch_urls):
                        print(f'    {f[:100]}')
                break

    browser.close()
