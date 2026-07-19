from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()
    
    page.goto('https://bypass.tools', wait_until='networkidle', timeout=30000)
    
    # Check for turnstile widget
    ts = page.evaluate("""() => {
        // Method 1: Check for turnstile iframe
        const iframes = Array.from(document.querySelectorAll('iframe'))
            .map(f => ({src: f.src?.slice(0,200), id: f.id}));
        
        // Method 2: Check window.turnstile
        const hasTurnstile = typeof window.turnstile !== 'undefined';
        
        // Method 3: Check for cf turnstile div
        const cfDivs = Array.from(document.querySelectorAll('[class*="cf-"], [id*="turnstile"], [class*="turnstile"]'))
            .map(d => ({id: d.id, cls: d.className?.slice(0,100)}));
        
        return { iframes, hasTurnstile, cfDivs };
    }""")
    print('Turnstile widget:', ts)
    
    # Check for sitekey in scripts
    sitekey = page.evaluate("""() => {
        const html = document.documentElement.innerHTML;
        const match = html.match(/sitekey[=:]["']([^"']+)["']/);
        const match2 = html.match(/data-sitekey=["']([^"']+)["']/);
        const match3 = html.match(/0x4[A-Za-z0-9_-]+/);
        return {
            sitekey: match ? match[1] : null,
            data_sitekey: match2 ? match2[1] : null,
            turnstile_key: match3 ? match3[0] : null
        };
    }""")
    print('Sitekey:', sitekey)
    
    # Check all external scripts on the page
    scripts = page.evaluate("""() => 
        Array.from(document.querySelectorAll('script[src]')).map(s => s.src)
    """)
    print(f'\nExternal scripts ({len(scripts)}):')
    for s in scripts:
        if 'turnstile' in s.lower() or 'challenge' in s.lower() or 'cloudflare' in s.lower():
            print(f'  {s}')
    
    browser.close()
