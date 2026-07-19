"""
Load the real Delta gateway URL in Playwright and monitor API calls
"""
import json, time, re
from playwright.sync_api import sync_playwright

CAPTURED_URL = 'https://auth.platorelay.com/a?d=SwLj0tAjs4kmgV1uybKATDBXUwnEK5gxhUQJ32MnAsyDXhkPLm9TBfTTmgJh56ssiWYU0bjoJY7LnfdEr321ULYU8uE5WGdvDRVWB6127h6be8nMerBfU3'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1280, 'height': 720})
    
    api_calls = []
    def on_request(req):
        url = req.url
        if any(k in url for k in ['api', 'session', 'authenticator', 'ticket', 'platorelay']):
            post_data = None
            if req.method == 'POST':
                try:
                    post_data = req.post_data
                except:
                    pass
            api_calls.append({
                'method': req.method,
                'url': url,
                'post_data': post_data,
                'headers': dict(req.headers),
            })
    
    page.on('request', on_request)
    
    console_logs = []
    def on_console(msg):
        console_logs.append(f'[{msg.type}] {msg.text[:200]}')
    page.on('console', on_console)
    
    print(f'Loading URL...', flush=True)
    page.goto(CAPTURED_URL, timeout=30000, wait_until='networkidle')
    time.sleep(10)
    
    print(f'\nCaptured {len(api_calls)} API calls:\n', flush=True)
    for i, call in enumerate(api_calls):
        print(f'--- Call {i+1} ---', flush=True)
        print(f'  {call["method"]} {call["url"][:200]}', flush=True)
        if call.get('post_data'):
            print(f'  POST: {call["post_data"][:300]}', flush=True)
    
    if console_logs:
        print(f'\nConsole logs ({len(console_logs)}):', flush=True)
        for log in console_logs[:10]:
            print(f'  {log}', flush=True)
    
    # Check page content
    body = page.text_content('body')
    print(f'\nBody: {body[:500]}', flush=True)
    
    page.screenshot(path='gateway_real.png')
    print(f'\nScreenshot saved.', flush=True)
    
    browser.close()
