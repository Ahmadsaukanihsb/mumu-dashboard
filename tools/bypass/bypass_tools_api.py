import sys, json

lootlabs_url = sys.argv[1] if len(sys.argv) > 1 else 'https://links.lootlabs.gg/s/xxx'

from playwright.sync_api import sync_playwright

api_endpoints = []

def handle_request(request):
    if '/api/' in request.url.lower() or '/bypass' in request.url.lower() or request.url.endswith('/v1/') or request.url.endswith('/v2/'):
        api_endpoints.append({
            'url': request.url,
            'method': request.method,
            'headers': dict(request.headers),
            'post_data': request.post_data
        })
        print(f'  API: [{request.method}] {request.url}')

def handle_response(response):
    if '/api/' in response.url.lower() or '/bypass' in response.url.lower():
        print(f'  RESP: [{response.status}] {response.url[:130]}')

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()
    page.on('request', handle_request)
    page.on('response', handle_response)

    print('=== OPEN BYPASS.TOOLS ===')
    page.goto('https://bypass.tools', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(3000)

    # Check form structure
    print('\n=== FORM ELEMENTS ===')
    form_info = page.evaluate("""() => {
        const inputs = Array.from(document.querySelectorAll('input, textarea'));
        const buttons = Array.from(document.querySelectorAll('button'));
        return {
            inputs: inputs.map(i => ({type: i.type, placeholder: i.placeholder, id: i.id, name: i.name, cls: i.className?.slice(0,50)})),
            buttons: buttons.map(b => ({text: b.innerText?.trim()?.slice(0,40), id: b.id, cls: b.className?.slice(0,50)}))
        };
    }""")
    print('Inputs:', json.dumps(form_info['inputs'], indent=2))
    print('Buttons:', json.dumps(form_info['buttons'], indent=2))

    # Try to fill and submit
    input('Isi URL di form, masukin captcha manual, lalu tekan Enter setelah bypass selesai...')

    print('\n=== CAPTURED API ENDPOINTS ===')
    for e in api_endpoints:
        print(f'URL: {e["url"]}')
        print(f'Method: {e["method"]}')
        print(f'Headers: {json.dumps(e["headers"], indent=2)}')
        print(f'Post data: {e["post_data"]}')
        print('---')

    print('\n=== COOKIES ===')
    cookies = ctx.cookies()
    # Look for session/cf cookies
    for c in cookies:
        print(f'  {c["name"]} = {c["value"][:60]}')

    print('\n=== LOCALSTORAGE ===')
    ls = page.evaluate("() => JSON.stringify(Object.entries(localStorage))")
    print(ls[:1000])

    browser.close()
