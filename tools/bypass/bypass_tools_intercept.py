import sys, json

LOOTLABS_URL = sys.argv[1] if len(sys.argv) > 1 else 'https://links.lootlabs.gg/s/xxx'

from playwright.sync_api import sync_playwright

api_calls = []

def handle_request(request):
    if '/api/' in request.url.lower() and 'bypass' not in request.url.lower() and 'static' not in request.url.lower() and 'jsd' not in request.url.lower():
        api_calls.append({
            'url': request.url,
            'method': request.method,
            'post_data': request.post_data
        })

def handle_response(response):
    if '/api/' in response.url.lower() and 'static' not in response.url.lower() and 'jsd' not in response.url.lower():
        body = None
        try:
            body = response.text()
        except:
            pass
        print(f'  [{response.status}] {response.url[:120]}')
        if body and len(body) < 2000:
            print(f'    Body: {body[:500]}')

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()
    page.on('response', handle_response)
    
    page.goto('https://bypass.tools', wait_until='networkidle', timeout=30000)
    
    # Find and fill the input
    page.fill('input[type="url"]', LOOTLABS_URL)
    page.wait_for_timeout(500)
    
    # Click Bypass
    page.click('button:has-text("Bypass")')
    page.wait_for_timeout(5000)
    
    print('\n--- Waiting 10s for responses... ---')
    page.wait_for_timeout(10000)
    
    print('\n=== API CALLS CAPTURED ===')
    # Check what's on the page now
    text = page.evaluate("() => document.body.innerText")
    print(f'\nPage text:\n{text[:1000]}')
    
    input('Tekan Enter untuk close...')
    browser.close()
