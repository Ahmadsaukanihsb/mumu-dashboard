import sys, json, re, time

PLATO_URL = sys.argv[1] if len(sys.argv) > 1 else 'https://auth.platorelay.com/a?d=cCuWtGQJouFcPcmnUfGji5JQT8ORHSo1XsAn8lsEBRCcUVVP1NqKWzFYnMb5tEOQ3D3eVsBH4EKC1gOnfnKkOIuh7kMqSvqrRCCKEqLVkSFMIfMP3jsws9DBXBfMHtDYI7c7smG1GhBQQj1R1qtlqQ2b01rU9MqtcC4bJbcNAkoxqok4y8500cG0wYZ2bMzGF00blZu4qTEVTV0jfUE54JsotdaL0BrggslX4zS9zELqEgBajMwWnnSo2gzOvJHAsCJU33yvulxgrDyod87Pl9UE33GsdyWefAHMyle72HBvB5Scd2sQXO2zo5Ip4go6M3uNlY9cEQiGnOyf03qU8h86P2zNI4qEpHIVcJDq2ofgq6nQg8kfZORZq0K7FDBrh7lUMt2159BHsGGoebpRVISVmhOyQc01QgQrh5vOVxaXwCEwa4AqNybPQf47Gl'

from playwright.sync_api import sync_playwright

all_requests = []

def handle_request(request):
    rtype = request.resource_type
    url = request.url
    if rtype in ('xhr', 'fetch') or '/api/' in url.lower() or '/reward' in url.lower() or '/claim' in url.lower() or '/complete' in url.lower() or '/task' in url.lower():
        all_requests.append({
            'url': url, 'method': request.method,
            'post_data': request.post_data,
            'resource_type': rtype
        })

def handle_response(response):
    url = response.url
    if any(x in url.lower() for x in ['/api/', '/reward', '/claim', '/complete', '/task']):
        try:
            body = response.text()
            if body:
                print(f'  [{response.status}] {response.method} {url[:120]}')
                if len(body) < 1000:
                    print(f'    Body: {body[:500]}')
        except:
            pass

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
    page.on('response', handle_response)

    # Step 1: Platoboost - wait for Continue button
    print('=== STEP 1: Platoboost ===')
    page.goto(PLATO_URL, wait_until='domcontentloaded', timeout=30000)
    
    # Wait for timer to finish (3 seconds + buffer)
    page.wait_for_timeout(5000)
    
    # Click Continue button (it should be enabled after 3s)
    page.evaluate("""() => {
        const btn = Array.from(document.querySelectorAll('button')).find(e => !e.disabled);
        if (btn) { btn.click(); console.log('Clicked:', btn.innerText); }
    }""")
    page.wait_for_timeout(3000)
    
    # Close any popup
    for p in ctx.pages:
        if p != page:
            print(f'Closing popup: {p.url[:80]}')
            p.close()
    
    # Click Continue button on the new page
    page.wait_for_timeout(2000)
    try:
        btn = page.wait_for_selector('button:not([disabled])', timeout=5000)
        btn.click()
        print('Clicked second button')
    except:
        print('No second button found - trying evaluate')
        page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button, a')).filter(e => e.offsetParent !== null);
            const continueBtn = btns.find(b => b.innerText.toLowerCase().includes('continue'));
            if (continueBtn) continueBtn.click();
            else if (btns.length > 0) btns[0].click();
        }""")
    
    # Wait for redirect to LootLabs
    page.wait_for_timeout(5000)
    
    current_url = page.url
    print(f'\nCurrent URL: {current_url[:150]}')
    
    if 'lootlabs' in current_url.lower() or 'links.' in current_url.lower():
        print('\n=== ON LOOTLABS ===')
        
        # Get page text to see the tasks
        page_text = page.evaluate("() => document.body.innerText")
        print(f'\nPage text:\n{page_text[:800]}')
        
        # Find all task links/buttons
        tasks = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a, button, [role="button"]'))
                .filter(e => e.offsetParent !== null)
                .map(e => ({
                    text: e.innerText?.trim()?.slice(0,60),
                    href: e.href || '',
                    tag: e.tagName,
                    cls: e.className?.slice(0,50)
                }))
                .filter(e => e.text || e.href);
        }""")
        print(f'\nInteractive elements:')
        for t in tasks[:20]:
            print(f'  [{t.tag}] "{t.text}" href={t.href[:80] if t.href else "N/A"}')
        
        # Check localStorage for any state
        ls = page.evaluate("() => JSON.stringify(Object.entries(localStorage))")
        print(f'\nlocalStorage:\n{ls[:500]}')
        
        print('\nNow clicking task buttons to trigger API calls...')
        
        # Wait and observe for any more API calls
        page.wait_for_timeout(15000)
        
    else:
        print(f'\nNot on LootLabs. URL: {current_url[:200]}')
        # Take a screenshot
        page.screenshot(path='lootlabs_result.png')
    
    print(f'\n=== ALL INTERCEPTED REQUESTS ({len(all_requests)}) ===')
    for r in all_requests:
        print(f'  [{r["method"]}] [{r["resource_type"]}] {r["url"][:130]}')
        if r['post_data']:
            print(f'    data: {r["post_data"][:200]}')
    
    print('\nWaiting 20s more for any activity...')
    page.wait_for_timeout(20000)
    
    print(f'\n=== FINAL URL: {page.url[:200]} ===')
    
    # Save screenshot for debugging
    page.screenshot(path='lootlabs_final.png')
    
    browser.close()
