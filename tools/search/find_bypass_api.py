import sys, json, re

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()
    
    # Get the main JS to find API endpoints
    page.goto('https://bypass.tools', wait_until='networkidle', timeout=30000)
    
    # Find all JS bundles
    scripts = page.evaluate("""() => 
        Array.from(document.querySelectorAll('script[src]'))
            .map(s => s.src)
            .filter(src => src.includes('.js'))
    """)
    print('JS bundles:', scripts)
    
    # Read main bundle
    for src in scripts:
        if 'vendor-react' in src or 'vendor-ui' in src or 'index-' in src:
            print(f'\n=== Reading {src} ===')
            response = page.evaluate(f"""async (url) => {{
                const resp = await fetch(url);
                return await resp.text();
            }}""", src)
            # Look for API endpoints
            apis = re.findall(r'["\'](/api/[^"\']+)["\']', response)
            if apis:
                print('Found API endpoints:')
                for a in set(apis):
                    print(f'  {a}')
            
            # Look for bypass function patterns
            bypass_patterns = re.findall(r'(?:bypass|resolve|unlock)[^"\']*["\']([^"\']+)["\']', response, re.I)
            if bypass_patterns:
                print(f'\nBypass-related strings:')
                for b in bypass_patterns[:20]:
                    print(f'  {b}')
            
            # Look for specific endpoint patterns
            endpoints = re.findall(r'["\']/(?:v\d/)?[a-z]+(?:/bypass|/resolve|/unlock|/bypasser)["\']', response, re.I)
            if endpoints:
                print(f'\nExplicit endpoint paths:')
                for e in set(endpoints):
                    print(f'  {e}')
    
    browser.close()
