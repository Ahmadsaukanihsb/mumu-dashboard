import re, time, json, urllib.request, urllib.error, urllib.parse, threading

from models import accounts, settings, _data_lock, log_account, log_activity, save_data, get_package_name
from core.state import delta_logs
from services.adb import find_adb, _adb_run, adb_connect, get_serial
from config import IS_ARM

_delta_lock = threading.Lock()
delta_key_store = {}


def log_delta_event(device_id, package, account, step, status, message='', key=''):
    """Catat event delta key ke store terpusat (persisten di data.json).

    step: 'capture_url', 'bypass', 'inject', 'receive', 'queue', 'extract'
    status: 'success', 'failed', 'info', 'redirect'
    """
    entry = {
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'ts': time.time(),
        'device_id': device_id or '-',
        'package': package or '-',
        'account': account or '-',
        'step': step,
        'status': status,
        'message': message[:200],
        'key_preview': (key[:12] + '...') if key else ''
    }
    with _delta_lock:
        delta_logs.append(entry)
        if len(delta_logs) > 300:
            delta_logs[:] = delta_logs[-300:]
    return entry


def get_delta_logs(limit=100):
    """Ambil delta logs terbaru (terbalik kronologis)."""
    with _delta_lock:
        return list(reversed(delta_logs))[:limit]

# Whitelist domains allowed for bypass (prevents SSRF)
_BYPASS_ALLOWED_DOMAINS = {
    'linkvertise.com', 'www.linkvertise.com',
    'lootlabs.gg', 'www.lootlabs.gg',
    'auth.platorelay.com',
    'baconbypass.xyz', 'www.baconbypass.xyz',
    'gateway.platorelay.com',
    'link-hub.net', 'www.link-hub.net',
    'direct-link.net', 'www.direct-link.net',
    'link-target.net', 'www.link-target.net',
    'link-center.net', 'www.link-center.net',
    'linkvertise.download',
}

def _is_allowed_bypass_url(url):
    """Check if URL is from an allowed bypass domain."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or '').lower()
        if not host:
            return False
        return host in _BYPASS_ALLOWED_DOMAINS or any(
            host.endswith('.' + d) for d in _BYPASS_ALLOWED_DOMAINS
        )
    except Exception:
        return False

def delta_get_link_from_ui(serial):
    adb = find_adb()
    if not adb: return None
    try:
        _adb_run([adb, '-s', serial, 'shell', 'uiautomator', 'dump', '--compressed', '/data/local/tmp/delta_ui.xml'],
            serial=serial, capture_output=True, timeout=15)
        r = _adb_run([adb, '-s', serial, 'shell', 'cat', '/data/local/tmp/delta_ui.xml 2>/dev/null || echo empty'],
            serial=serial, capture_output=True, text=True, timeout=10)
        _adb_run([adb, '-s', serial, 'shell', 'rm', '-f', '/data/local/tmp/delta_ui.xml'],
            serial=serial, capture_output=True, timeout=5)
        urls = re.findall(r'https?://[^\s"\'<>]+', r.stdout)
        for u in urls:
            if any(k in u for k in ['key', 'verify', 'delta', 'linkvertise', 'gateway', 'bypass']):
                return u
        if urls:
            return urls[0]
    except:
        pass
    return None

def delta_get_link_from_logcat(serial):
    adb = find_adb()
    if not adb: return None
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'logcat', '-d'],
            serial=serial, capture_output=True, text=True, timeout=10)
        urls = set()
        for line in r.stdout.split('\n'):
            for u in re.findall(r'https?://[^\s"\'<>)]+', line):
                low = u.lower()
                if any(k in low for k in ['key', 'verify', 'delta', 'linkvertise', 'gateway', 'bypass', 'executor']):
                    return u
                if 'roblox' not in low:
                    urls.add(u)
        for u in sorted(urls, key=len):
            return u
    except:
        pass
    return None

def delta_get_link_from_dumpsys(serial):
    adb = find_adb()
    if not adb: return None
    try:
        r = _adb_run([adb, '-s', serial, 'shell', 'dumpsys', 'activity', 'recents'],
            serial=serial, capture_output=True, text=True, timeout=10)
        urls = re.findall(r'https?://[^\s"\'<>]+', r.stdout)
        for u in urls:
            low = u.lower()
            if any(k in low for k in ['key', 'verify', 'delta', 'linkvertise', 'gateway', 'bypass', 'executor']):
                return u
        for u in urls:
            if 'roblox' not in u.lower() and 'firebase' not in u.lower():
                return u
    except:
        pass
    return None

def delta_capture_url(serial):
    for fn in [delta_get_link_from_ui, delta_get_link_from_logcat, delta_get_link_from_dumpsys]:
        url = fn(serial)
        if url:
            return url
    return None

def delta_bypass_via_api(url):
    import urllib.request, urllib.error, json as json_lib
    ticket = None
    parsed = urllib.parse.urlparse(url)
    if parsed.path == '/a' and 'd' in urllib.parse.parse_qs(parsed.query):
        ticket = urllib.parse.parse_qs(parsed.query)['d'][0]
    else:
        m = re.search(r'auth\.platorelay\.com/([^?&#]+)', url)
        if m:
            ticket = m.group(1)
    print(f'[DELTA] Extracted ticket: {ticket}')
    if not ticket:
        print('[DELTA] No ticket found in URL')
        return None
    api_url = f'https://auth.platorelay.com/api/session/status?ticket={ticket}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        'Accept': 'application/json, text/plain, */*',
        'Referer': url,
        'Origin': 'https://auth.platorelay.com',
    }
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json_lib.loads(resp.read().decode())
    except Exception as e:
        print(f'[DELTA] API error: {e}')
        return None
    print(f'[DELTA] API response: {json_lib.dumps(data)[:300]}')
    raw_key = data.get('data', {}).get('key') if isinstance(data.get('data'), dict) else data.get('key')
    minutes_left = data.get('data', {}).get('minutesLeft') if isinstance(data.get('data'), dict) else None
    if raw_key and raw_key != 'KEY_NOT_FOUND':
        return raw_key
    if minutes_left and minutes_left > 0:
        print(f'[DELTA] Session active, {minutes_left}min left. Polling...')
        for _ in range(12):
            time.sleep(5)
            try:
                req2 = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    data2 = json_lib.loads(resp2.read().decode())
                raw_key2 = data2.get('data', {}).get('key') if isinstance(data2.get('data'), dict) else data2.get('key')
                if raw_key2 and raw_key2 != 'KEY_NOT_FOUND':
                    print(f'[DELTA] Key found after polling: {raw_key2[:20]}...')
                    return raw_key2
            except:
                pass
        return None
    try:
        post_req = urllib.request.Request(
            'https://auth.platorelay.com/api/session/status',
            data=json_lib.dumps({'ticket': ticket, 'captcha': '', 'type': 'Turnstile'}).encode(),
            headers={**headers, 'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(post_req, timeout=10) as post_resp:
            post_data = json_lib.loads(post_resp.read().decode())
        print(f'[DELTA] POST response: {json_lib.dumps(post_data)[:300]}')
        raw_key = post_data.get('data', {}).get('key') if isinstance(post_data.get('data'), dict) else post_data.get('key')
        if raw_key and raw_key != 'KEY_NOT_FOUND':
            return raw_key
        if post_data.get('redirect'):
            return post_data['redirect']
    except Exception as e:
        print(f'[DELTA] POST error: {e}')
    return None

def delta_bypass_via_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 720})
            page.goto('https://baconbypass.xyz/', timeout=30000, wait_until='domcontentloaded')
            time.sleep(3)
            page.evaluate("""
                document.querySelectorAll('iframe[id^="container-"]').forEach(el => el.remove());
                document.querySelectorAll('[data-ad-element]').forEach(el => el.remove());
            """)
            page.locator('#urlInput').fill(url)
            time.sleep(1)
            page.evaluate("document.getElementById('bypassBtn').click()")
            for _ in range(30):
                time.sleep(2)
                err = page.evaluate("() => document.getElementById('errBox')?.textContent?.trim() || ''")
                if err and len(err) > 3:
                    continue
                result = page.evaluate("() => document.getElementById('modalResult')?.innerHTML || ''")
                if result and len(result) > 3:
                    km = re.search(r'[A-Z0-9_\-]{25,50}', result)
                    if km:
                        browser.close()
                        return km.group(0)
                    urls = re.findall(r'https?://[^\s"\'<>]+', result)
                    if urls:
                        browser.close()
                        return urls[0]
                    browser.close()
                    return result.strip()
    except Exception as e:
        print(f'[DELTA] Playwright bypass error: {e}')
    finally:
        if browser:
            try: browser.close()
            except: pass
    return None

def delta_bypass_via_playwright_lootlabs(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    browser = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            ctx = browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
            )
            page = ctx.new_page()

            page.add_init_script("""
            (() => {
                const realNow = Date.now;
                const start = realNow();
                Date.now = function() {
                    const elapsed = realNow() - start;
                    if (elapsed > 3000) return start + 120000;
                    return realNow();
                };
                const realPerf = Performance.prototype.now;
                Performance.prototype.now = function() {
                    const elapsed = realPerf.call(this);
                    if (elapsed > 3000) return 120000;
                    return elapsed;
                };
            })();
            """)

            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            print('[KEY] Page loaded, polling for key...')

            import requests as _req
            for attempt in range(20):
                page.wait_for_timeout(1500)
                for p in ctx.pages:
                    if p != page:
                        p.close()
                ticket_match = re.search(r'd=([A-Za-z0-9%]+)', page.url)
                if ticket_match:
                    try:
                        r = _req.get(
                            f'https://auth.platorelay.com/api/session/status?ticket={ticket_match.group(1)}',
                            timeout=10
                        )
                        data = r.json()
                        if data.get('data', {}).get('key'):
                            key = data['data']['key']
                            print(f'[KEY] Found via API: {key[:20]}...')
                            browser.close()
                            return key
                    except:
                        pass
                text = page.evaluate("() => document.body.innerText")
                km = re.search(r'[A-Z0-9_\-]{25,50}', text)
                if km:
                    key = km.group(0)
                    if not key.startswith('FREE_') or len(key) > 20:
                        print(f'[KEY] Found in text: {key[:20]}...')
                        browser.close()
                        return key
                btns = page.evaluate("""() =>
                    Array.from(document.querySelectorAll('button')).map(b => ({
                        text: b.innerText.replace(/\\n/g,' ').trim(),
                        disabled: b.disabled
                    }))
                """)
                enabled = [b for b in btns if not b['disabled']]
                if enabled:
                    print(f'[KEY] Clicking "{enabled[0]["text"]}" (attempt {attempt+1})')
                    page.evaluate("() => { document.querySelector('button:not([disabled])')?.click() }")
                elif attempt == 0:
                    page.evaluate("() => { document.querySelector('button')?.click() }")
            print('[KEY] No key obtained via acceleration')
            return None
    except Exception as e:
        print(f'[KEY] Error: {e}')
        import traceback
        traceback.print_exc()
        return None
    finally:
        if browser:
            try: browser.close()
            except: pass

def delta_bypass_url(url):
    if not _is_allowed_bypass_url(url):
        print(f'[DELTA] URL rejected (not in whitelist): {url[:100]}')
        return None
    key = delta_bypass_via_api(url)
    if key:
        return key
    if not IS_ARM:
        key = delta_bypass_via_playwright(url)
        if key:
            return key
        key = delta_bypass_via_playwright_lootlabs(url)
        if key:
            return key
    return None

def delta_find_button(serial, label):
    adb = find_adb()
    if not adb: return None
    try:
        _adb_run([adb, '-s', serial, 'shell', 'uiautomator', 'dump', '--compressed', '/data/local/tmp/delta_btn.xml'],
            serial=serial, capture_output=True, timeout=15)
        r = _adb_run([adb, '-s', serial, 'shell', 'cat', '/data/local/tmp/delta_btn.xml 2>/dev/null || echo empty'],
            serial=serial, capture_output=True, text=True, timeout=10)
        _adb_run([adb, '-s', serial, 'shell', 'rm', '-f', '/data/local/tmp/delta_btn.xml'],
            serial=serial, capture_output=True, timeout=5)
        label_lower = label.lower()
        for node in re.finditer(r'<node\s+([^>]+?)/?\s*>', r.stdout):
            attrs = node.group(1)
            text = re.search(r'text="([^"]*)"', attrs)
            cd = re.search(r'content-desc="([^"]*)"', attrs)
            txt = ((text.group(1) if text else '') + ' ' + (cd.group(1) if cd else '')).lower()
            if label_lower not in txt:
                continue
            bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', attrs)
            if bounds:
                cx = (int(bounds.group(1)) + int(bounds.group(3))) // 2
                cy = (int(bounds.group(2)) + int(bounds.group(4))) // 2
                return cx, cy
    except:
        pass
    return None


def delta_extract_key_from_ui(serial):
    """Extract key that is already filled in the Delta key input field.

    Returns the key string if found (25-50 chars, uppercase/digits/dash/underscore),
    or None if field is empty or key not valid.
    """
    adb = find_adb()
    if not adb: return None
    try:
        _adb_run([adb, '-s', serial, 'shell', 'uiautomator', 'dump', '--compressed', '/data/local/tmp/delta_key.xml'],
            serial=serial, capture_output=True, timeout=15)
        r = _adb_run([adb, '-s', serial, 'shell', 'cat', '/data/local/tmp/delta_key.xml 2>/dev/null || echo empty'],
            serial=serial, capture_output=True, text=True, timeout=10)
        _adb_run([adb, '-s', serial, 'shell', 'rm', '-f', '/data/local/tmp/delta_key.xml'],
            serial=serial, capture_output=True, timeout=5)

        # Look for EditText fields (key input)
        for node in re.finditer(r'<node\s+([^>]+?)/?\s*>', r.stdout):
            attrs = node.group(1)
            cls = re.search(r'class="([^"]*)"', attrs)
            text = re.search(r'text="([^"]*)"', attrs)
            if not text:
                continue
            txt = text.group(1).strip()
            # Check if it's an EditText with key-like content
            if cls and 'EditText' in cls.group(1):
                # Key pattern: 25-50 chars, uppercase letters, digits, dash, underscore
                m = re.search(r'[A-Z0-9_\-]{25,50}', txt)
                if m and 'key' not in txt.lower() and 'enter' not in txt.lower():
                    return m.group(0)
            # Also check any text field that looks like a key
            if re.match(r'^[A-Z0-9_\-]{25,50}$', txt):
                return txt

        # Fallback: find any long uppercase string in the UI
        for node in re.finditer(r'<node\s+([^>]+?)/?\s*>', r.stdout):
            attrs = node.group(1)
            text = re.search(r'text="([^"]*)"', attrs)
            if not text:
                continue
            txt = text.group(1).strip()
            if re.match(r'^[A-Z0-9_\-]{25,50}$', txt):
                return txt
    except Exception as e:
        print(f'[DELTA] extract_key error: {e}')
    return None

def _escape_for_adb_input(text):
    """Escape special characters for ADB 'input text' command."""
    return (text.replace('%', '%25')
                .replace(' ', '%20')
                .replace('&', '%26')
                .replace("'", '%27')
                .replace('"', '%22')
                .replace(';', '%3B')
                .replace('<', '%3C')
                .replace('>', '%3E')
                .replace('|', '%7C')
                .replace('\\', '%5C'))


def delta_inject_key(serial, key, package='com.roblox.client'):
    adb = find_adb()
    if not adb: return False
    try:
        pt = delta_find_button(serial, 'KEY')
        if not pt:
            pt = (540, 960)
        _adb_run([adb, '-s', serial, 'shell', 'input', 'tap', str(pt[0]), str(pt[1])],
            serial=serial, capture_output=True, timeout=5)
        time.sleep(1)
        escaped = _escape_for_adb_input(key)
        key_part = escaped[:20]
        _adb_run([adb, '-s', serial, 'shell', 'input', 'text', key_part],
            serial=serial, capture_output=True, timeout=5)
        if len(escaped) > 20:
            time.sleep(0.3)
            _adb_run([adb, '-s', serial, 'shell', 'input', 'text', escaped[20:]],
                serial=serial, capture_output=True, timeout=5)
        time.sleep(1)
        verify_pt = delta_find_button(serial, 'Receive Key')
        if not verify_pt:
            verify_pt = delta_find_button(serial, 'RECEIVE')
        if not verify_pt:
            verify_pt = delta_find_button(serial, 'Receive')
        if not verify_pt:
            verify_pt = delta_find_button(serial, 'VERIFY')
        if not verify_pt:
            verify_pt = delta_find_button(serial, 'SUBMIT')
        if verify_pt:
            _adb_run([adb, '-s', serial, 'shell', 'input', 'tap', str(verify_pt[0]), str(verify_pt[1])],
                serial=serial, capture_output=True, timeout=5)
        return True
    except:
        return False

def delta_auto_get_key(serial, package='com.roblox.client', device_id=''):
    try:
        adb = find_adb()
        if not adb:
            return None, 'ADB not found'

        # STEP 1: Check if key is already filled in Delta UI (no bypass needed)
        existing_key = delta_extract_key_from_ui(serial)
        if existing_key:
            print(f'[DELTA] Key already filled in UI: {existing_key[:20]}...')
            log_delta_event(device_id, package, '', 'extract', 'success',
                          'Key sudah terisi di Delta UI', existing_key)
            # Tap "Receive Key" to activate it
            receive_pt = delta_find_button(serial, 'Receive Key')
            if not receive_pt:
                receive_pt = delta_find_button(serial, 'RECEIVE')
            if not receive_pt:
                receive_pt = delta_find_button(serial, 'Receive')
            if receive_pt:
                _adb_run([adb, '-s', serial, 'shell', 'input', 'tap', str(receive_pt[0]), str(receive_pt[1])],
                    serial=serial, capture_output=True, timeout=5)
                time.sleep(2)
                print(f'[DELTA] Tapped Receive Key at {receive_pt}')
                log_delta_event(device_id, package, '', 'receive', 'success',
                              f'Tapped Receive Key @ {receive_pt}')
            else:
                log_delta_event(device_id, package, '', 'receive', 'failed',
                              'Tombol Receive Key tidak ditemukan')
            return existing_key, None

        log_delta_event(device_id, package, '', 'extract', 'info',
                      'Key belum terisi, mulai bypass flow')

        # STEP 2: No key filled — do full bypass flow
        disp_w, disp_h = 960, 540
        try:
            r = _adb_run([adb, '-s', serial, 'shell', 'wm', 'size'],
                serial=serial, capture_output=True, text=True, timeout=5)
            m = re.search(r'(\d+)x(\d+)', r.stdout)
            if m:
                pw, ph = int(m.group(1)), int(m.group(2))
            else:
                pw, ph = 540, 960
            dr = _adb_run([adb, '-s', serial, 'shell', 'dumpsys', 'display'],
                serial=serial, capture_output=True, text=True, timeout=5)
            ov = re.search(r'OverrideDisplayInfo.*?real (\d+) x (\d+)', dr.stdout, re.DOTALL)
            if ov:
                disp_w, disp_h = int(ov.group(1)), int(ov.group(2))
            elif 'orientation=1' in dr.stdout or 'orientation=3' in dr.stdout:
                disp_w, disp_h = ph, pw
            else:
                disp_w, disp_h = pw, ph
        except:
            pass

        _adb_run([adb, '-s', serial, 'shell', 'logcat', '-c'],
            serial=serial, capture_output=True, timeout=5)

        rx, ry = int(disp_w * 0.835), int(disp_h * 0.657)
        for dy in (-30, 0, 30):
            for dx in (-50, 0, 50):
                tx = rx + dx
                ty = ry + dy
                if 0 <= tx < disp_w and 0 <= ty < disp_h:
                    _adb_run([adb, '-s', serial, 'shell', 'input', 'tap', str(tx), str(ty)],
                        serial=serial, capture_output=True, timeout=5)
                    time.sleep(0.15)

        time.sleep(2)
        url = None
        for attempt in range(5):
            r = _adb_run([adb, '-s', serial, 'shell', 'logcat', '-d', '-s', 'ActivityTaskManager'],
                serial=serial, capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n'):
                if 'ACTION_VIEW' in line and 'http' in line:
                    for u in re.findall(r'https?://[^\s"\'<>)]+', line.replace('...', '')):
                        low = u.lower()
                        if any(k in low for k in ['linkvertise', 'lootlabs', 'gateway', 'bypass', 'key',
                                                   'verify', 'delta', 'executor', 'platorelay', 'auth.']):
                            url = u
                            print(f'[DELTA] URL from logcat intent: {u[:150]}')
                            break
                    if url:
                        break
            if url:
                break
            time.sleep(1)

        if not url:
            r = _adb_run([adb, '-s', serial, 'shell', 'logcat', '-d'],
                serial=serial, capture_output=True, text=True, timeout=10)
            for line in r.stdout.split('\n'):
                if 'http' in line.lower() and 'ACTION_VIEW' in line:
                    for u in re.findall(r'https?://[^\s"\'<>)]+', line.replace('...', '')):
                        low = u.lower()
                        if any(k in low for k in ['linkvertise', 'lootlabs', 'gateway', 'bypass',
                                                   'key', 'verify', 'delta', 'executor', 'platorelay', 'auth.']):
                            url = u
                            print(f'[DELTA] URL from logcat: {u[:150]}')
                            break
                    if url:
                        break

        if not url:
            r = _adb_run([adb, '-s', serial, 'shell', 'dumpsys', 'activity', 'recents'],
                serial=serial, capture_output=True, text=True, timeout=10)
            for u in re.findall(r'https?://[^\s"\'<>)]+', r.stdout):
                low = u.lower()
                if any(k in low for k in ['linkvertise', 'lootlabs', 'gateway', 'bypass', 'key',
                                           'verify', 'delta', 'executor', 'platorelay', 'auth.']):
                    url = u
                    print(f'[DELTA] URL from dumpsys: {u[:150]}')
                    break

        if not url:
            log_delta_event(device_id, package, '', 'capture_url', 'failed',
                          'Gagal capture URL key dari logcat/dumpsys')
            return None, 'Gagal capture URL key'

        print(f'[DELTA] URL captured via method: {url[:120]}...')
        log_delta_event(device_id, package, '', 'capture_url', 'success',
                      f'URL: {url[:100]}')

        if not _is_allowed_bypass_url(url):
            log_delta_event(device_id, package, '', 'capture_url', 'failed',
                          f'URL rejected (whitelist): {url[:80]}')
            return None, f'URL rejected (not in bypass whitelist): {url[:80]}'

        _adb_run([adb, '-s', serial, 'shell', 'am', 'force-stop', 'com.android.chrome'],
            serial=serial, capture_output=True, timeout=5)
        time.sleep(1)
        _adb_run([adb, '-s', serial, 'shell', 'monkey', '-p', package, '1'],
            serial=serial, capture_output=True, timeout=5)

        print(f'[DELTA] Auto-bypassing via Playwright...')
        try:
            key = delta_bypass_via_playwright_lootlabs(url)
            if key:
                print(f'[DELTA] Key found via Playwright: {key[:20]}...')
                log_delta_event(device_id, package, '', 'bypass', 'success',
                              'Key diperoleh via bypass', key)
                ok = delta_inject_key(serial, key)
                if not ok:
                    log_delta_event(device_id, package, '', 'inject', 'failed',
                                  'Gagal inject key ke Delta UI')
                    return None, 'Gagal inject key ke Delta'
                log_delta_event(device_id, package, '', 'inject', 'success',
                              'Key di-inject ke Delta UI', key)
                return key, None
            log_delta_event(device_id, package, '', 'bypass', 'failed',
                          'Playwright bypass tidak menghasilkan key')
        except Exception as e:
            print(f'[DELTA] Playwright error: {e}')
            log_delta_event(device_id, package, '', 'bypass', 'failed', f'Error: {str(e)[:100]}')

        import webbrowser
        try:
            webbrowser.open(url)
            print(f'[DELTA] URL opened on PC browser as fallback')
        except Exception as e:
            print(f'[DELTA] Failed to open PC browser: {e}')

        return None, 'Gagal bypass gateway'
    except Exception as e:
        return None, str(e)

def delta_get_stored_key(acc_id):
    with _delta_lock:
        entry = delta_key_store.get(acc_id)
        if entry and entry.get('expires_at', 0) > time.time():
            return entry.get('key')
    return None

def delta_set_stored_key(acc_id, key):
    with _delta_lock:
        delta_key_store[acc_id] = {
            'key': key,
            'expires_at': time.time() + 22 * 3600,
            'updated_at': time.time()
        }

def delta_refresh_key_for_acc(acc):
    acc_id = acc.get('id', '')
    acc_name = acc.get('name', '?')
    device_id = acc.get('device_id', '') or f"vm{acc.get('mumu_instance', 0)}"
    instance = acc.get('mumu_instance', 0)
    package = acc.get('package_name', get_package_name(instance))
    serial = get_serial(instance)
    if not serial:
        log_delta_event(device_id, package, acc_name, 'queue', 'failed', 'No serial')
        return {'success': False, 'error': 'No serial'}
    ok, msg = adb_connect(serial)
    if not ok:
        log_delta_event(device_id, package, acc_name, 'queue', 'failed', f'ADB: {msg}')
        return {'success': False, 'error': f'ADB: {msg}'}
    key, err = delta_auto_get_key(serial, package, device_id)
    if err:
        log_delta_event(device_id, package, acc_name, 'queue', 'failed', err)
        return {'success': False, 'error': err}
    delta_set_stored_key(acc_id, key)
    # Tag the most recent log entries with this account name
    with _delta_lock:
        for entry in reversed(delta_logs[-10:]):
            if entry.get('account') in ('', '-') and entry.get('package') == package:
                entry['account'] = acc_name
    log_delta_event(device_id, package, acc_name, 'queue', 'success',
                  'Key refreshed dan disimpan (22 jam)', key)
    return {'success': True, 'key_preview': key[:10] + '...'}

def get_active_delta_keys_count():
    with _delta_lock:
        return sum(1 for v in delta_key_store.values()
                   if v.get('key') and v.get('expires_at', 0) > time.time())
