"""
Monitor API calls + responses from real gateway URL
"""
import json, time
from playwright.sync_api import sync_playwright

CAPTURED_URL = 'https://auth.platorelay.com/a?d=SwLj0tAjs4kmgV1uybKATDBXUwnEK5gxhUQJ32MnAsyDXhkPLm9TBfTTmgJh56ssiWYU0bjoJY7LnfdEr321ULYU8uE5WGdvDRVWB6127h6be8nMerBfU3'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1280, 'height': 720})
    
    resources = []
    
    def on_response(resp):
        url = resp.url
        if '/api/' in url:
            try:
                body = resp.text()
                resources.append({
                    'status': resp.status,
                    'url': url,
                    'body': body[:500],
                })
            except:
                resources.append({
                    'status': resp.status,
                    'url': url,
                    'body': '<error reading>',
                })
    
    page.on('response', on_response)
    
    print('Loading URL...', flush=True)
    page.goto(CAPTURED_URL, timeout=30000, wait_until='networkidle')
    time.sleep(10)
    
    print(f'\nAPI Responses ({len(resources)}):\n', flush=True)
    for r in resources:
        print(f'[{r["status"]}] {r["url"][:120]}', flush=True)
        print(f'  Body: {r["body"][:400]}', flush=True)
        print()
    
    # Check what the SPA displays
    try:
        body_text = page.evaluate("() => document.querySelector('.card')?.textContent?.trim() || document.body.textContent?.trim() || ''")
        print(f'Page text: {body_text[:500]}', flush=True)
    except:
        pass
    
    page.screenshot(path='gateway_real2.png')
    print('Screenshot saved.', flush=True)
    
    browser.close()
