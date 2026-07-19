from playwright.sync_api import sync_playwright
import json, re

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = ctx.new_page()
    page.goto('https://bypass.tools', wait_until='networkidle', timeout=30000)

    # Put a URL in the input
    page.fill('input[type="url"]', 'https://auth.platorelay.com/a?d=test')
    page.wait_for_timeout(500)

    # Listen for network requests to find captcha loading
    captcha_reqs = []
    def on_request(request):
        if 'turnstile' in request.url.lower() or 'challenges' in request.url.lower() or 'recaptcha' in request.url.lower() or 'captcha' in request.url.lower():
            captcha_reqs.append(request.url)
            print(f'Captcha req: {request.url}')

    page.on('request', on_request)

    # Click Bypass button
    page.click('button:has-text("Bypass")')
    page.wait_for_timeout(5000)

    print(f'\nCaptcha requests: {captcha_reqs}')

    # Check what appeared on the page
    html = page.content()
    # Search for turnstile sitekey
    for pattern in [r'data-sitekey=["\']([^"\']+)', r'sitekey["\':]=["\']([^"\']+)', r'0x4[A-Fa-f0-9]{32,40}']:
        matches = re.findall(pattern, html)
        if matches:
            print(f'Sitekey found: {matches}')

    # Also check for any new iframes
    iframes = page.evaluate("""() => 
        Array.from(document.querySelectorAll('iframe')).map(f => f.src).filter(Boolean)
    """)
    print(f'\nIframes: {iframes}')

    # Check the page for captcha elements
    captcha_elems = page.evaluate("""() => {
        const divs = Array.from(document.querySelectorAll('div'));
        return divs
            .filter(d => d.className && (d.className.includes('captcha') || d.className.includes('turnstile') || d.className.includes('challenge') || d.className.includes('cf-')))
            .slice(0,10)
            .map(d => ({id: d.id, cls: d.className?.slice(0,100), inner: d.innerHTML?.slice(0,200)}));
    }""")
    print(f'\nCaptcha elements: {json.dumps(captcha_elems, indent=2)[:1000]}')

    # Check what element was inserted
    body = page.evaluate("() => document.body.innerHTML.slice(5000, 15000)")
    print(f'\nBody snippet:\n{body[:2000]}')

    input('Tekan Enter untuk close...')
    browser.close()
