import sys, json, re

URL = sys.argv[1]

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(viewport={'width': 1280, 'height': 720})

    # Inject before 35.js loads - modify key behavior
    ctx.add_init_script("""
        // Override addEventListener to catch claim button setup
        const origAddEventListener = EventTarget.prototype.addEventListener;
        EventTarget.prototype.addEventListener = function(type, handler, options) {
            // If this is the unlock button, wrap the handler
            if (type === 'click' && this.classList && this.classList.contains('unlock')) {
                console.log('Blocked click handler on unlock button');
                return; // Don't add the handler - we'll trigger it ourselves
            }
            return origAddEventListener.call(this, type, handler, options);
        };
        
        // Block the unlock button's click setup
        // Also override classList.add to detect when 'go' is added
        const origAdd = DOMTokenList.prototype.add;
        DOMTokenList.prototype.add = function(...classes) {
            if (this.value && this.value.includes('unlock') && classes.includes('go')) {
                console.log('Unlock button got go class!');
            }
            return origAdd.apply(this, classes);
        };
    """)

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

    # Try to find the internal state/object
    print('=== SCANNING WINDOW FOR INTERNAL OBJECTS ===')
    result = page.evaluate("""() => {
        const found = [];
        
        // Check all window properties for objects with key methods
        for (const key of Object.getOwnPropertyNames(window)) {
            try {
                const val = window[key];
                if (val && typeof val === 'object' && !Array.isArray(val)) {
                    const props = Object.getOwnPropertyNames(val);
                    if (props.some(p => p.includes('continueBtn') || p.includes('unlock') || p.includes('removeContent') || p.includes('generateSucceed'))) {
                        found.push({key: key.slice(0,40), props: props.slice(0,10)});
                    }
                }
            } catch(e) {}
        }
        
        // Also try to find the main instance by looking for elements with specific IDs
        const readyText = document.getElementById('readyText');
        const unlockBtn = document.querySelector('.unlock');
        
        return {
            objects: found,
            hasReadyText: !!readyText,
            hasUnlockBtn: !!unlockBtn,
            window_keys: Object.getOwnPropertyNames(window).filter(k => {
                try { return window[k] && typeof window[k] === 'object' && k.length < 30; } catch(e) { return false; }
            }).slice(0, 50)
        };
    }""")
    print(f'Found objects: {json.dumps(result["objects"], indent=2)[:500]}')
    print(f'Ready text: {result["hasReadyText"]}')
    print(f'Unlock btn: {result["hasUnlockBtn"]}')
    print(f'Window keys (first 20): {result["window_keys"][:20]}')

    # Try to search for the controller object differently
    # Check all elements with ID for the readyText
    result2 = page.evaluate("""() => {
        const btn = document.querySelector('.unlock');
        const info = {};
        
        // Check the button's parent elements
        if (btn) {
            let el = btn;
            for (let i = 0; i < 5; i++) {
                if (el && el.parentElement) {
                    const kids = Array.from(el.parentElement.children).length;
                    info['level_' + i] = {tag: el.tagName, id: el.id, cls: el.className, kids: kids};
                    el = el.parentElement;
                }
            }
        }
        
        // Check for the main app root
        const appRoot = document.getElementById('app') || document.querySelector('#root') || document.querySelector('[data-app]');
        if (appRoot) {
            info['app_root'] = appRoot.id || appRoot.className;
        }
        
        return info;
    }""")
    print(f'\nDOM info: {json.dumps(result2, indent=2)}')

    # Check what scripts reference the continueBtn
    result3 = page.evaluate("""() => {
        // Try to find internal state in DOM
        const all = [];
        
        // Check for JSON data in script tags
        document.querySelectorAll('script[type="application/json"], script[data-]').forEach(s => {
            try {
                all.push({type: s.type, data: s.textContent?.slice(0,100)});
            } catch(e) {}
        });
        
        // Check __NEXT_DATA__ or similar
        if (window.__NEXT_DATA__) all.push('__NEXT_DATA__ found');
        if (window.__NUXT__) all.push('__NUXT__ found');
        
        return all;
    }""")
    print(f'\nPage data: {result3}')

    browser.close()
