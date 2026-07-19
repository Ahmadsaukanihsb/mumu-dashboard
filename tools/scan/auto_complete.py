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
    print('ON LOOTLABS')

    # Click ALL task items by their text (like original script)
    for attempt in range(3):
        tasks = page.evaluate("""() => {
            const divs = document.querySelectorAll('.task, [class*="task"]');
            return Array.from(divs).map(t => t.innerText?.replace(/\\n/g,' ').trim().slice(0,80));
        }""")
        print(f'\nTasks found: {tasks}')
        
        for task_text in tasks:
            print(f'\nClicking task: "{task_text[:40]}"')
            page.evaluate(f"""() => {{
                const divs = document.querySelectorAll('div, button, a');
                for (const d of divs) {{
                    if (d.offsetParent !== null && d.innerText?.includes('{task_text[:30]}')) {{
                        d.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true, view: window}}));
                        return;
                    }}
                }}
            }}""")
            page.wait_for_timeout(2000)
            
            # Close any popup
            for p in ctx.pages:
                if p != page and p.url != 'about:blank':
                    print(f'  Popup: {p.url[:80]}')
                    p.close()
            page.wait_for_timeout(1000)

    # Wait for auto-complete
    print('\n=== WAITING FOR TASKS TO AUTO-COMPLETE (60s) ===')
    for i in range(30):
        page.wait_for_timeout(2000)
        
        # Check task status
        status = page.evaluate("""() => {
            const tasks = document.querySelectorAll('.task');
            return Array.from(tasks).map(t => ({
                done: t.className.includes('done'),
                text: t.innerText?.replace(/\\n/g,' ').trim().slice(0,60),
                cls: t.className
            }));
        }""")
        
        btn = page.evaluate("""() => {
            const b = document.querySelector('.unlock');
            return b ? {go: b.className.includes('go'), disabled: b.disabled} : null;
        }""")
        
        print(f't={i*2+2}s  done={[s["done"] for s in status]}  btn_go={btn}')
        
        # Check if all tasks done
        if all(s['done'] for s in status):
            print('\n*** ALL TASKS DONE! ***')
            break
        
        # Check if button has go class
        if btn and btn['go']:
            print('\n*** CLAIM READY! ***')
            break

    # Try claiming
    print('\n=== CLAIMING ===')
    page.evaluate("""() => {
        const btn = document.querySelector('.unlock');
        if (btn) {
            // Ensure it's active
            btn.classList.add('go');
            btn.disabled = false;
            // Click via multiple methods
            btn.click();
            btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        }
    }""")
    page.wait_for_timeout(5000)

    text = page.evaluate("() => document.body.innerText")
    print(f'\n=== FINAL TEXT ===')
    print(text[:1500])

    km = re.search(r'[A-Z0-9_\-]{25,50}', text)
    if km:
        print(f'\n*** KEY: {km.group(0)} ***')
    else:
        km2 = re.search(r'[A-Z0-9_\-]{25,50}', page.url)
        if km2:
            print(f'\n*** KEY in URL: {km2.group(0)} ***')

    browser.close()
