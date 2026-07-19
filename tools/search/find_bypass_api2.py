import sys, json, re

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()
    
    page.goto('https://bypass.tools', wait_until='networkidle', timeout=30000)
    
    resp = page.evaluate("""async () => {
        const r = await fetch('/api/captcha-config');
        return await r.json();
    }""")
    print('=== CAPTCHA CONFIG ===')
    print(json.dumps(resp, indent=2))
    
    resp2 = page.evaluate("""async () => {
        const r = await fetch('/api/risky-domains');
        return await r.json();
    }""")
    print('\n=== RISKY DOMAINS ===')
    print(json.dumps(resp2, indent=2)[:500])
    
    # Now read the actual JS around the /api/bypass endpoint
    content = page.evaluate("""async () => {
        const resp = await fetch('/assets/index-pXVRzQ_o.js');
        return await resp.text();
    }""")
    
    # Find the bypass function
    bypass_idx = content.find('/api/bypass')
    if bypass_idx >= 0:
        print(f'\n=== CONTEXT AROUND /api/bypass (chars {bypass_idx}-{bypass_idx+2000}) ===')
        print(content[max(0,bypass_idx-500):bypass_idx+2000])
    
    # Find the function that calls the bypass API
    # Look for patterns like "url:", "bypass(", "formData"
    patterns = [
        r'\.post\([^)]+\)',
        r'axios[^;]+',
        r'fetch\([^)]+\)',
        r'bypass[^;]+',
    ]
    
    browser.close()
