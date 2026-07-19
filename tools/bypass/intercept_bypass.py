import sys, json, re

URL = sys.argv[1]

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
    page = ctx.new_page()

    # Intercept network to modify verification responses
    def handle_route(route):
        url = route.request.url
        method = route.request.method

        # Intercept /verify to say all tasks done
        if '/verify' in url and method == 'POST':
            print(f'Intercepted /verify POST -> returning success')
            route.fulfill(
                status=200,
                content_type='application/json',
                body=json.dumps({
                    "status": "success",
                    "tasks_completed": 2,
                    "max_tasks": 2,
                    "all_done": True,
                    "can_claim": True
                })
            )
            return

        # Intercept nerventualken.com/tc to indicate all tasks done
        if 'nerventualken.com/tc' in url:
            body = route.request.post_data
            print(f'Intercepted /tc POST -> faking completion')
            route.fulfill(
                status=200,
                content_type='application/json',
                body=json.dumps([{
                    "id": "1",
                    "status": "completed",
                    "completed": True
                }, {
                    "id": "2",
                    "status": "completed",
                    "completed": True
                }])
            )
            return

        # Intercept Platoboost session status to say key is ready
        if '/api/session/status' in url:
            print(f'Intercepted /status -> returning fake key')
            route.fulfill(
                status=200,
                content_type='application/json',
                body=json.dumps({
                    "success": True,
                    "data": {
                        "key": "DELTA_KEY_12345_ABCDEFGHIJKLMNOP",
                        "minutesLeft": 24
                    }
                })
            )
            return

        route.continue_()

    page.route('**/*', handle_route)

    # Platoboost -> LootLabs
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
    page.wait_for_timeout(2000)

    text = page.evaluate("() => document.body.innerText")
    print(f'\n=== PAGE TEXT ===')
    print(text[:1000])

    # Check claim button
    btn = page.evaluate("""() => {
        const b = document.querySelector('.unlock');
        return b ? {cls: b.className, disabled: b.disabled, text: b.innerText?.slice(0,30)} : null;
    }""")
    print(f'\nButton: {btn}')

    # Check ready text
    ready = page.evaluate("""() => {
        const el = document.getElementById('readyText');
        if (!el) return 'no readyText';
        return {display: getComputedStyle(el).display, text: el.innerText?.slice(0,50)};
    }""")
    print(f'Ready text: {ready}')

    # Check tasks
    tasks = page.evaluate("""() => 
        Array.from(document.querySelectorAll('.task')).map(t => ({
            done: t.className.includes('done'),
            text: t.innerText?.replace(/\\n/g,' ').trim().slice(0,60)
        }))
    """)
    print(f'Tasks: {tasks}')

    # Try clicking claim
    page.evaluate("""() => {
        const btn = document.querySelector('.unlock');
        if (btn) {
            btn.classList.add('go');
            btn.disabled = false;
            btn.click();
            btn.dispatchEvent(new Event('click', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(3000)

    text2 = page.evaluate("() => document.body.innerText")
    print(f'\n=== AFTER CLAIM ===')
    print(text2[:1500])

    km = re.search(r'[A-Z0-9_\-]{25,50}', text2)
    if km:
        print(f'\n*** KEY: {km.group(0)} ***')
    else:
        km2 = re.search(r'[A-Z0-9_\-]{25,50}', page.url)
        if km2:
            print(f'\n*** KEY in URL: {km2.group(0)} ***')
        else:
            print('\nNo key found')

    browser.close()
