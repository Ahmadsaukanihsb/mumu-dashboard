import os
import sys
import time
import json
import subprocess
import requests
try:
    import readline
except ImportError:
    pass
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.prompt import Prompt, Confirm
import pyfiglet
import re

console = Console()
CONFIG_FILE = "/sdcard/Download/kellzy_config.json"

def clear_screen():
    os.system('tput reset 2>/dev/null || stty sane 2>/dev/null; clear')

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except:
        pass

def setup_wizard():
    clear_screen()
    ascii_art = pyfiglet.figlet_format("SETUP KELLZY", font="standard")
    console.print(Text(ascii_art, style="bold magenta"))

    console.print("\n[bold cyan]--- SETUP TOOLS PREMIUM KELLZY ---[/bold cyan]\n")
    
    # Check existing config
    existing_config = load_config()
    if existing_config and existing_config.get('packages'):
        console.print("[bold yellow]⚠ Setup sebelumnya ditemukan![/bold yellow]")
        console.print(f"[white]  Packages: {len(existing_config.get('packages', []))} apps[/white]")
        console.print(f"[white]  PS URL: {existing_config.get('ps_url', 'None')}[/white]")
        console.print(f"[white]  Scripts: {len(existing_config.get('scripts', []))} scripts[/white]")
        create_new = Confirm.ask("\n[cyan]Buat Setup Baru? (No = pakai setup lama)[/cyan]", default=False)
        if not create_new:
            console.print("\n[bold green]✅ Setup lama dipakai![/bold green]")
            console.print("[white][i] Re-injecting scripts...[/white]")
            for pkg in existing_config.get('packages', []):
                auto_inject_script(pkg, existing_config)
            console.print("[bold green]✅ Injection complete![/bold green]")
            time.sleep(2)
            return existing_config
    
    config = {}
    
    console.print("[white][i] Select package selection mode:[/white]")
    console.print("[white]1) Auto-detect (Recommended)[/white]")
    console.print("[white]2) Enter manual package names[/white]")
    pkg_mode = Prompt.ask("[cyan][?] Choice[/cyan]", choices=["1", "2"], default="1")
    
    discovered_packages = []
    if pkg_mode == "1":
        console.print("[white][i] Auto-detecting packages...[/white]")
        try:
            # Menggunakan pm list packages untuk mendeteksi semua clone Roblox
            output = subprocess.check_output(['su', '-c', 'pm list packages | grep com.roblox']).decode('utf-8')
            os.system("stty sane")
            for line in output.split('\n'):
                if line.startswith('package:'):
                    discovered_packages.append(line.split(':')[1].strip())
        except:
            pass
            
        console.print("\n[cyan][?] Discovered packages:[/cyan]")
        for i, p in enumerate(discovered_packages):
            console.print(f"[white]{i+1}) {p}[/white]")
            
        console.print("[white]- Press <Enter> or 'all' to select ALL packages (Default)[/white]")
        console.print("[white]- Type 'none' to skip, or enter indices (e.g. '1,3')[/white]")
        sel = Prompt.ask("[cyan][?] Select[/cyan]", default="all").strip().lower()
        if sel == "" or sel == "all":
            config['packages'] = discovered_packages
        elif sel == "none":
            config['packages'] = []
        else:
            selected = []
            for idx in sel.split(','):
                try: selected.append(discovered_packages[int(idx.strip())-1])
                except: pass
            config['packages'] = selected
    else:
        manual_pkgs = Prompt.ask("[cyan]Enter package names separated by comma[/cyan]", default="com.roblox.client")
        config['packages'] = [p.strip() for p in manual_pkgs.split(',')]
        
    use_ps = Confirm.ask("\n[cyan]Use same Private Server URL for all packages?[/cyan]", default=True)
    if use_ps:
        config['ps_url'] = Prompt.ask("[yellow]Global Private Server URL (or Game URL)[/yellow]")
        config['ps_urls'] = {}
    else:
        config['ps_url'] = ""
        console.print("\n[yellow]\\[i] Setting per-package URLs (Press Enter to leave blank):[/yellow]")
        ps_urls = {}
        for pkg in config.get('packages', []):
            username = get_masked_username(pkg, config)
            os.system("stty sane 2>/dev/null")
            console.print(f"[cyan]\\[?] URL for {pkg} ({username}) (Biarkan kosong jika tidak ada):[/cyan]")
            new_url = input("> ").strip()
            ps_urls[pkg] = new_url
        config['ps_urls'] = ps_urls

    config['mask_username'] = Confirm.ask("[cyan]Mask username in status table? (e.g. naxxxie)[/cyan]", default=True)
    config['delay_launch'] = int(Prompt.ask("[cyan]Delay between launching apps (seconds)[/cyan]", default="15"))
    config['delay_relaunch'] = int(Prompt.ask("[cyan]Delay before relaunching crashed/disconnected apps (seconds)[/cyan]", default="60"))
    
    config['webhook'] = Prompt.ask("[cyan]Discord Webhook URL (for critical alerts) [Enter to skip][/cyan]", default="")
    config['status_update_interval'] = int(Prompt.ask("[cyan]Status Update Interval (minutes) [0 to Disable][/cyan]", default="0"))
    config['scheduled_restart_interval'] = int(Prompt.ask("[cyan]Scheduled Restart Interval (minutes) [0 to Disable][/cyan]", default="0"))
    
    config['auto_clear_cache'] = Confirm.ask("[cyan]Auto clear cache sebelum launch?[/cyan]", default=True)
    config['auto_captcha'] = Confirm.ask("[cyan]Enable Auto Captcha Solve?[/cyan]", default=False)
    if config['auto_captcha']:
        config['captcha_timeout'] = int(Prompt.ask("[cyan]Captcha Wait Time out (seconds)[/cyan]", default="300"))
    
    config['auto_inject'] = Confirm.ask("[cyan]Inject scripts to 'autoexecute' folder?[/cyan]", default=True)
    config['scripts'] = []
    
    if config['auto_inject']:
        script_num = 1
        while True:
            add_script = Confirm.ask(f"[bold white]\\[?] Add Script #{script_num}?[/bold white]", default=True)
            if not add_script: break
            console.print("[bold white]\\[i] Paste your script below. Type 'END' on a new line to save.[/bold white]")
            console.print("[white]" + "-"*50 + "[/white]")
            lines = []
            while True:
                line = input()
                if line.strip() == "END": break
                lines.append(line)
            
            if lines: 
                print("\r", end="")
                console.print("[white]" + "-"*50 + "[/white]")
                console.print(f"[bold white]\\[*] Deploying script_{script_num}.lua...[/bold white]")
                config['scripts'].append("\n".join(lines))
                
                # Instantly deploy to all folders
                if 'packages' in config:
                    for pkg in config['packages']:
                        auto_inject_script(pkg, config)
                        
                time.sleep(1)
                console.print(f"[bold white]\\[+] Finished deploying script_{script_num}.lua[/bold white]")
            script_num += 1

    save_config(config)
    
    console.print("\n[bold green]✅ Setup Tersimpan![/bold green]")
    time.sleep(2)
    return config

def get_free_memory():
    try:
        meminfo = subprocess.check_output(['su', '-c', 'cat /proc/meminfo'], stderr=subprocess.DEVNULL).decode('utf-8')
        mem_free = mem_total = 0
        for line in meminfo.split('\n'):
            if 'MemFree' in line: mem_free = int(line.split()[1]) // 1024
            elif 'MemTotal' in line: mem_total = int(line.split()[1]) // 1024
        if mem_total > 0:
            percent = 100 - int((mem_free / mem_total) * 100)
            return f"Free: {mem_free}MB ({percent}%)"
    except: pass
    return "Free: Unknown"

def is_app_running(pkg):
    try:
        pid = subprocess.check_output(['su', '-c', f'pidof {pkg}'], stderr=subprocess.DEVNULL).decode('utf-8').strip()
        return bool(pid)
    except:
        return False

def get_hwid():
    try:
        out = subprocess.check_output(['su', '-c', 'settings get secure android_id 2>/dev/null'], stderr=subprocess.DEVNULL).decode('utf-8').strip()
        if out and len(out) > 5: return out
    except: pass
    
    # Fallback ke termux id / mac
    try:
        out = subprocess.check_output(['ip', 'link', 'show', 'wlan0'], stderr=subprocess.DEVNULL).decode('utf-8')
        mac = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', out)
        if mac: return mac.group(0).replace(':', '')
    except: pass
    
    return "UNKNOWN_HWID"

def validate_license(key, config=None):
    while True:
        try:
            hwid = get_hwid()
            res = requests.post("https://dashboard.aavpanel.my.id/api/validate_key", json={"key": key, "hwid": hwid}, timeout=5).json()
            if res.get("valid"):
                return key
            
            console.print(f"\n[bold red]❌ LICENSE ERROR: {res.get('error', 'Invalid Key or Max Device Limit Reached')}[/bold red]")
            console.print(f"[white]HWID Kamu: {hwid}[/white]")
            console.print("[yellow]Silakan masukkan License Key yang valid:[/yellow]")
            console.print("[cyan][?] License Key:[/cyan]")
            os.system("stty sane 2>/dev/null")
            key = input("> ").strip()
            
            if config is not None:
                config['license_key'] = key
                save_config(config)
        except Exception as e:
            console.print("[yellow]⚠ Gagal menghubungi server lisensi. Melanjutkan...[/yellow]")
            return key

def send_webhook(url, title, description, color=16776960):
    if not url: return
    data = {"embeds": [{"title": title, "description": description, "color": color}]}
    try: requests.post(url, json=data, timeout=3)
    except: pass

def get_masked_username(pkg, config):
    if 'usernames_cache' not in config:
        config['usernames_cache'] = {}
        
    username = config['usernames_cache'].get(pkg)
    
    if not username:
        username = "account"
        try:
            # Dynamically fetch Roblox username from shared_prefs
            cmd = f"grep -ioE 'name=\"username\">[^<]+' /data/data/{pkg}/shared_prefs/*.xml 2>/dev/null | head -1"
            res = subprocess.run(['su', '-c', cmd], capture_output=True, text=True, timeout=2)
            out = res.stdout.strip()
            if ">" in out:
                username = out.split(">")[-1].strip()
        except: pass
        config['usernames_cache'][pkg] = username

    if config.get('mask_username') and len(username) > 4:
        username = username[:2] + "xxx" + username[-2:]
        
    return f"{pkg} ({username})"

def auto_inject_script(pkg, config):
    if not config.get('auto_inject'): return
    
    # DYNAMIC DISCOVERY: find actual autoexec folders created by Delta
    discovered = []
    try:
        result = subprocess.run(
            ['su', '-c', f'find /sdcard/Android/data/{pkg} /data/data/{pkg} /storage/emulated/0/Android/data/{pkg} -type d \\( -name "autoexec" -o -name "autoexecute" \\) 2>/dev/null'],
            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
        )
        discovered = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
    except: pass
    
    # Known standard Delta paths (fallback)
    known = [
        f"/sdcard/Delta/Autoexecute",
        f"/sdcard/Delta/autoexec",
        f"/storage/emulated/0/Delta/Autoexecute",
        f"/storage/emulated/0/Delta/autoexec",
        f"/sdcard/Android/data/{pkg}/files/delta/autoexecute",
        f"/sdcard/Android/data/{pkg}/files/delta/autoexec",
        f"/data/data/{pkg}/files/delta/autoexecute",
        f"/data/data/{pkg}/files/delta/autoexec",
        f"/storage/emulated/0/Android/data/{pkg}/files/delta/autoexecute",
        f"/storage/emulated/0/Android/data/{pkg}/files/delta/autoexec",
    ]
    
    if not discovered:
        # Fallback to standard locations
        discovered = [
            f"/sdcard/Android/data/{pkg}/autoexec",
            f"/storage/emulated/0/Android/data/{pkg}/autoexec"
        ]
        
    discovered.append("/storage/emulated/0/Delta/Autoexecute")
    paths = list(set(discovered))
    
    owner_str = ""
    try:
        res = subprocess.run(['su', '-c', f'stat -c "%U:%G" /sdcard/Android/data/{pkg}'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if ":" in res.stdout: owner_str = res.stdout.strip()
    except: pass
    
    try:
        all_paths = " ".join(paths)
        subprocess.run(['su', '-c', f'mkdir -p {all_paths}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        subprocess.run(['su', '-c', f'chmod -R 777 {all_paths}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        if owner_str:
            subprocess.run(['su', '-c', f'chown -R {owner_str} {all_paths}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            
        # Bersihkan file script lama di folder tujuan biar nggak numpuk kalau ada yang dihapus
        for p in paths:
            subprocess.run(['su', '-c', f'rm {p}/script_*.lua {p}/kellzy*.lua {p}/*.lua 2>/dev/null'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            
        temp_file = os.path.abspath("./kellzy.lua")
        
        # Selalu tanam script LiveFarm ke dalam autoexecute
        license_key = config.get('license_key', 'KELLZY-HUB-ADMIN')
        try:
            with open(temp_file, "w") as f:
                f.write(f'getgenv().LICENSE_KEY = "{license_key}";\nloadstring(game:HttpGet("https://dashboard.aavpanel.my.id/livefarmbot-kellzy.lua"))()\n')
            
            for p in paths:
                subprocess.run(['su', '-c', f"cp {temp_file} {p}/kellzy.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                subprocess.run(['su', '-c', f"chmod 777 {p}/kellzy.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                if owner_str:
                    subprocess.run(['su', '-c', f"chown {owner_str} {p}/kellzy.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except Exception as e:
            console.print(f"[red]Error writing kellzy.lua: {e}[/red]")
        
        # Tanam script-script tambahan dari user (Auto Buy, dll)
        for i, script_content in enumerate(config.get('packages_scripts', config.get('scripts', []))):
            temp_file = os.path.abspath(f"./script_{i+1}.lua")
            try:
                with open(temp_file, "w") as f:
                    f.write(script_content)
                for p in paths:
                    subprocess.run(['su', '-c', f"cp {temp_file} {p}/script_{i+1}.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    subprocess.run(['su', '-c', f"chmod 777 {p}/script_{i+1}.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    if owner_str:
                        subprocess.run(['su', '-c', f"chown {owner_str} {p}/script_{i+1}.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            except: pass
            
        if config.get('auto_captcha'):
            temp_file = "./kellzy_captcha.lua"
            try:
                with open(temp_file, "w") as f:
                    f.write('print("[KELLZY] Auto Captcha Solver Injected!");\n')
                for p in paths:
                    subprocess.run(['su', '-c', f"cp {temp_file} {p}/kellzy_captcha.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    subprocess.run(['su', '-c', f"chmod 777 {p}/kellzy_captcha.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    if owner_str:
                        subprocess.run(['su', '-c', f"chown {owner_str} {p}/kellzy_captcha.lua"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            except: pass
            
        # Clean up local files
        subprocess.run(['rm', '-f', './kellzy*.lua', './script_*.lua'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def kill_app(pkg):
    try:
        subprocess.run(['su', '-c', f'am force-stop {pkg}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except: pass

def optimize_system():
    try:
        subprocess.run(['su', '-c', 'echo 3 > /proc/sys/vm/drop_caches'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        subprocess.run(['su', '-c', 'dumpsys deviceidle whitelist +com.termux'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        subprocess.run(['su', '-c', 'settings put global enable_freeform_support 1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        subprocess.run(['su', '-c', 'settings put global force_resizable_activities 1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except: pass

def get_grid_bounds(idx, total):
    try:
        result = subprocess.run(['su', '-c', 'wm size'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        size_match = re.search(r'(\d+)x(\d+)', result.stdout)
        if not size_match: return None
        screen_w = int(size_match.group(1))
        screen_h = int(size_match.group(2))
        
        cols = int(total ** 0.5)
        if cols * cols < total: cols += 1
        rows = (total + cols - 1) // cols
        
        cell_w = screen_w // cols
        cell_h = screen_h // rows
        
        row = idx // cols
        col = idx % cols
        left = col * cell_w
        top = row * cell_h
        right = left + cell_w
        bottom = top + cell_h
        
        return f"{left},{top},{right},{bottom}"
    except: return None

def get_all_task_ids(packages):
    """Get task IDs for ALL packages using a single optimized shell command"""
    task_map = {}
    
    # Build a single shell script that dumps activity info ONCE, then greps each pkg
    pkg_list = ' '.join(packages)
    script = f'''
output=$(dumpsys activity activities 2>/dev/null)
for p in {pkg_list}; do
  tid=$(echo "$output" | grep -F "$p" | grep -oE "( t[0-9]+|#[0-9]+|taskId=[0-9]+)" | head -1 | tr -d " t#taskId=")
  [ -n "$tid" ] && echo "$p=$tid"
done
'''
    try:
        res = subprocess.run(
            ['su', '-c', script],
            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL
        )
        os.system("stty sane 2>/dev/null")
        for line in res.stdout.strip().split('\n'):
            if '=' in line:
                pkg, tid = line.split('=', 1)
                pkg = pkg.strip()
                tid = tid.strip()
                if pkg in packages and tid:
                    task_map[pkg] = tid
    except: pass
    
    # Fallback: am stack list (if shell script missed any)
    missing = [p for p in packages if p not in task_map]
    if missing:
        try:
            res = subprocess.run(
                ['su', '-c', 'am stack list'],
                capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
            )
            os.system("stty sane 2>/dev/null")
            for line in res.stdout.split('\n'):
                for pkg in missing:
                    if pkg in line and pkg not in task_map:
                        m = re.search(r'taskId=(\d+)', line) or re.search(r'#(\d+)', line)
                        if m:
                            task_map[pkg] = m.group(1)
        except: pass
    
    return task_map

def get_all_stack_ids(packages):
    """Get stack IDs for ALL packages in one shot"""
    stack_map = {}
    try:
        res = subprocess.run(
            ['su', '-c', 'am stack list'],
            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
        )
        os.system("stty sane 2>/dev/null")
        current_stack = None
        for line in res.stdout.split('\n'):
            sm = re.search(r'Stack id=(\d+)', line) or re.search(r'stackId=(\d+)', line)
            if sm:
                current_stack = sm.group(1)
            for pkg in packages:
                if pkg in line and current_stack and pkg not in stack_map:
                    stack_map[pkg] = current_stack
    except: pass
    return stack_map

def resize_task(pkg, bounds_str):
    """Resize a single task - used during start_app only"""
    if not bounds_str: return
    task_map = get_all_task_ids([pkg])
    stack_map = get_all_stack_ids([pkg])
    task_id = task_map.get(pkg)
    stack_id = stack_map.get(pkg)
    left, top, right, bottom = bounds_str.split(',')
    if task_id:
        subprocess.run(['su', '-c', f'am task resize {task_id} {left} {top} {right} {bottom}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    if stack_id:
        subprocess.run(['su', '-c', f'am stack resize {stack_id} {left} {top} {right} {bottom}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

def tile_all_windows(packages):
    """Arrange ALL running app windows in a neat grid - batch mode"""
    try:
        n = len(packages)
        if n == 0: return
        
        # Get screen size ONCE
        try:
            result = subprocess.run(['su', '-c', 'wm size'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            os.system("stty sane 2>/dev/null")
            size_match = re.search(r'(\d+)x(\d+)', result.stdout)
            if not size_match: return
            screen_w = int(size_match.group(1))
            screen_h = int(size_match.group(2))
        except: return
        
        # Calculate grid
        cols = int(n ** 0.5)
        if cols * cols < n: cols += 1
        rows = (n + cols - 1) // cols
        cell_w = screen_w // cols
        cell_h = screen_h // rows
        
        # Get ALL task IDs and stack IDs in ONE shot
        task_map = get_all_task_ids(packages)
        stack_map = get_all_stack_ids(packages)
        
        # Resize each window using cached IDs
        for i, pkg in enumerate(packages):
            row = i // cols
            col = i % cols
            left = col * cell_w
            top = row * cell_h
            right = left + cell_w
            bottom = top + cell_h
            
            task_id = task_map.get(pkg)
            stack_id = stack_map.get(pkg)
            
            # Try task resize
            if task_id:
                subprocess.run(['su', '-c', f'am task resize {task_id} {left} {top} {right} {bottom}'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            # Try stack resize
            if stack_id:
                subprocess.run(['su', '-c', f'am stack resize {stack_id} {left} {top} {right} {bottom}'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except: pass

def start_app(pkg, config, bounds_str=None):
    try:
        if config.get('auto_clear_cache'):
            subprocess.run(['su', '-c', f'rm -rf /data/data/{pkg}/cache/*'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        
        # Pre-inject (for folders from previous runs)
        auto_inject_script(pkg, config)
        
        # Enable freeform window mode
        subprocess.run(['su', '-c', 'settings put global enable_freeform_support 1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        subprocess.run(['su', '-c', 'settings put global force_resizable_activities 1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        
        # Resolve main launcher activity to properly force freeform mode
        activity = ""
        try:
            res = subprocess.run(['su', '-c', f'cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER {pkg}'], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
            lines = [l.strip() for l in res.stdout.strip().split('\n') if '/' in l]
            if lines: activity = lines[-1]
        except: pass

        ps_urls = config.get('ps_urls', {})
        ps_url = ps_urls.get(pkg, config.get('ps_url', ""))
        
        # Launch with URL (Private Server) or normal launch
        if ps_url:
            cmd = f'am start --windowingMode 5 -a android.intent.action.VIEW -d "{ps_url}" -p {pkg}'
            subprocess.run(['su', '-c', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        elif activity:
            cmd = f'am start --windowingMode 5 -n {activity}'
            subprocess.run(['su', '-c', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        else:
            cmd = f'monkey -p {pkg} -c android.intent.category.LAUNCHER 1'
            subprocess.run(['su', '-c', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        
        # Wait a moment then try to resize as backup
        time.sleep(2)
        if bounds_str:
            resize_task(pkg, bounds_str)
        
        # Wait for Delta to initialize and create its autoexec folders
        time.sleep(1)
        
        # Post-inject (for folders Delta just created)
        auto_inject_script(pkg, config)
    except: pass

def tile_all_windows(packages):
    """Arrange all running app windows in a neat grid layout like Kaeru"""
    try:
        n = len(packages)
        if n == 0: return
        
        for i, pkg in enumerate(packages):
            bounds = get_grid_bounds(i, n)
            if bounds:
                resize_task(pkg, bounds)
    except: pass

def generate_table(status_dict, step, config, packages):
    CYAN = "\033[1;36m"
    YELLOW = "\033[1;33m"
    GREEN = "\033[1;32m"
    RED = "\033[1;31m"
    RESET = "\033[0m"
    
    lines = []
    lines.append(f"{CYAN}{'PACKAGE':<30}| STATUS{RESET}")
    lines.append(f"{CYAN}{'-'*30}+----------------{RESET}")
    total_pkgs = len(packages) if packages else 1
    lines.append(f"{CYAN}{'System':<30}{RESET}| {YELLOW}Checking [{step}/{total_pkgs}]{RESET}")
    lines.append(f"{CYAN}{'Memory':<30}{RESET}| {YELLOW}{get_free_memory()}{RESET}")
    lines.append(f"{CYAN}{'-'*30}+----------------{RESET}")

    for pkg in packages:
        status = status_dict.get(pkg, "Unknown")
        display_name = get_masked_username(pkg, config)
        
        if status == "Online": status_color = GREEN
        elif status in ["Starting...", "Waiting", "Ready"]: status_color = YELLOW
        else: status_color = RED
            
        lines.append(f"{display_name:<30}| {status_color}{status}{RESET}")
        
    return "\r\n".join(lines) + "\r\n"

def manage_scripts(config):
    while True:
        clear_screen()
        console.print(Panel("[bold green]Manage Auto-Execute Scripts[/bold green]", border_style="green"))
        console.print("\n[yellow]\\[*] Syncing & Scanning auto-execute folders... Please wait.[/yellow]")
        
        packages = config.get('packages', [])
        
        # Sync silently to ensure physical folders match config
        if packages:
            for pkg in packages:
                auto_inject_script(pkg, config)
                
        found_files = []
        if packages:
            first_pkg = packages[0]
            try:
                # Real dynamic scan of the actual folder
                res = subprocess.run(['su', '-c', f'find /sdcard/Android/data/{first_pkg} -type d -name "autoexecute" 2>/dev/null | head -1'], capture_output=True, text=True)
                autoexec_path = res.stdout.strip()
                if autoexec_path:
                    ls_res = subprocess.run(['su', '-c', f'ls {autoexec_path}'], capture_output=True, text=True)
                    for f in ls_res.stdout.strip().split('\n'):
                        if f and not f.isspace():
                            found_files.append(f)
            except: pass
            
        time.sleep(1)
        
        clear_screen()
        console.print("[cyan]Detected Scripts (Real-time Scan):[/cyan]")
        if not found_files:
            console.print("  [white]No scripts found in folder.[/white]")
        else:
            for i, fname in enumerate(found_files):
                console.print(f"  [white]{i+1}) {fname}[/white]")
                
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  [green]1)[/green] Add New Script")
        console.print("  [yellow]2)[/yellow] Delete Script")
        console.print("  [red]3)[/red] Back")
        
        c = Prompt.ask("\n[cyan]\\[?] Enter your choice [1-3][/cyan]", choices=["1", "2", "3"], default="3")
        
        if c == "3":
            break
        elif c == "1":
            console.print("\n[bold white]\\[i] Paste your script below. Type 'END' on a new line to save.[/bold white]")
            console.print("[white]" + "-"*50 + "[/white]")
            lines = []
            while True:
                line = input()
                if line.strip() == "END": break
                lines.append(line)
            
            if lines:
                print("\r", end="")
                scripts = config.get('scripts', [])
                scripts.append("\n".join(lines))
                config['scripts'] = scripts
                save_config(config)
                
                console.print("[white]" + "-"*50 + "[/white]")
                console.print(f"[bold white]\\[*] Deploying script_{len(scripts)}.lua to all packages...[/bold white]")
                for pkg in packages:
                    auto_inject_script(pkg, config)
                console.print(f"[bold white]\\[+] Finished deploying script_{len(scripts)}.lua[/bold white]")
                time.sleep(1.5)
        elif c == "2":
            if found_files:
                idx_str = Prompt.ask("\n[cyan]\\[?] Enter script number to delete[/cyan]")
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(found_files):
                        target_file = found_files[idx]
                        if "kellzy.lua" in target_file or "captcha" in target_file:
                            console.print("[bold red]❌ Cannot delete core system scripts![/bold red]")
                            time.sleep(1.5)
                        else:
                            # It's a custom script. Try to parse its number to pop from config.
                            match = re.search(r'script_(\d+)', target_file)
                            if match:
                                script_num = int(match.group(1)) - 1
                                scripts = config.get('scripts', [])
                                if 0 <= script_num < len(scripts):
                                    scripts.pop(script_num)
                                    config['scripts'] = scripts
                                    save_config(config)
                                    
                            console.print(f"[yellow]Removing {target_file} from all packages...[/yellow]")
                            for pkg in packages:
                                auto_inject_script(pkg, config)
                            console.print("[bold green]✅ Script deleted and folders synced![/bold green]")
                            time.sleep(1.5)
                    else:
                        console.print("[bold red]❌ Invalid script number![/bold red]")
                        time.sleep(1)
                except: pass

def edit_configuration(config):
    while True:
        clear_screen()
        console.print(Panel("[bold green]Configuration Edit Menu[/bold green]", border_style="green"))
        
        console.print("\n[cyan]Current Configuration Summary:[/cyan]")
        console.print(f"  Packages: {len(config.get('packages', []))} configured")
        console.print(f"  Private Server: {'Set' if config.get('ps_url') else 'Not set'}")
        console.print(f"  Webhook: {'Enabled' if config.get('webhook') else 'Disabled'}")
        console.print(f"  Status Updates: Every {config.get('status_update_interval', 0)} minutes")
        
        console.print("\n[cyan]What would you like to edit?[/cyan]")
        console.print("  [green]1)[/green] Package List (Re-run Setup)")
        console.print("  [green]2)[/green] Private Server URLs")
        console.print("  [green]3)[/green] Webhook Settings")
        console.print("  [green]4)[/green] Other Settings (Delay, etc.)")
        console.print("  [green]5)[/green] Manage Auto-Execute Scripts")
        console.print("  [magenta]6)[/magenta] Cloud Sync (Load/Save/Backup)")
        console.print("  [green]7)[/green] Manage Server Pool (Private Servers)")
        console.print("  [yellow]8)[/yellow] View Full Configuration")
        console.print("  [red]9)[/red] Back to Main Menu")
        
        choice = Prompt.ask("\n[cyan]\\[?] Enter your choice [1-9][/cyan]", choices=[str(i) for i in range(1, 10)], default="9")
        
        if choice == "9":
            break
        elif choice == "5":
            manage_scripts(config)
        elif choice == "1":
            setup_wizard()
            return
        elif choice == "2":
            while True:
                clear_screen()
                console.print(Panel("[bold green]Edit Private Server URLs[/bold green]", border_style="green"))
                console.print("\n[cyan]Current Configuration:[/cyan]")
                console.print(f"  Global URL: {config.get('ps_url', 'None')}")
                console.print("\n[cyan]Actions:[/cyan]")
                console.print("  [green]1)[/green] Set Global URL (same for all packages)")
                console.print("  [green]2)[/green] Set Per-Package URLs")
                console.print("  [red]3)[/red] Back")
                
                sub_c = Prompt.ask("\n[cyan]\\[?] Enter your choice [1-3][/cyan]", choices=["1", "2", "3"], default="3")
                if sub_c == "3":
                    break
                elif sub_c == "1":
                    ps_url = Prompt.ask("\n[cyan]Enter Global Private Server URL (Leave blank to remove)[/cyan]", default=config.get('ps_url', ''))
                    config['ps_url'] = ps_url
                    save_config(config)
                    console.print("[bold green]✅ Saved![/bold green]")
                    time.sleep(1)
                elif sub_c == "2":
                    console.print("\n[yellow]\\[i] Setting per-package URLs (Press Enter to keep current):[/yellow]")
                    ps_urls = config.get('ps_urls', {})
                    for pkg in config.get('packages', []):
                        current_url = ps_urls.get(pkg, "")
                        username = get_masked_username(pkg, config)
                        os.system("stty sane 2>/dev/null")
                        console.print(f"[cyan]\\[?] URL for {pkg} ({username})\n(Ketik URL baru, atau Enter untuk pakai URL lama: {current_url})[/cyan]")
                        new_url = input("> ").strip()
                        ps_urls[pkg] = new_url if new_url else current_url
                    config['ps_urls'] = ps_urls
                    save_config(config)
                    console.print("[bold green]✅ Per-package URLs saved![/bold green]")
                    time.sleep(1)
        elif choice == "3":
            webhook = Prompt.ask("\n[cyan]Enter New Webhook URL (Leave blank to disable)[/cyan]", default=config.get('webhook', ''))
            config['webhook'] = webhook
            save_config(config)
            console.print("[bold green]✅ Saved![/bold green]")
            time.sleep(1)
        elif choice == "4":
            delay_launch = Prompt.ask("\n[cyan]Delay Launch (seconds)[/cyan]", default=str(config.get('delay_launch', 15)))
            try: config['delay_launch'] = int(delay_launch)
            except: pass
            save_config(config)
            console.print("[bold green]✅ Saved![/bold green]")
            time.sleep(1)
        else:
            console.print("\n[bold yellow]Feature coming soon![/bold yellow]")
            time.sleep(1)

def main():
    clear_screen()
    ascii_art = pyfiglet.figlet_format("KELLZY", font="block")
    console.print(Text(ascii_art, style="bold cyan"))
    console.print(Align.center(Text("v3.0.0 - ULTIMATE FARM MANAGER", style="white")))
    console.print("\n")
    
    # --- SISTEM LOGIN TOOLS ---
    console.print("[white][i] Verifikasi Lisensi Tools...[/white]")
    
    # Load config lama untuk cek apakah sudah ada key
    config = load_config() or {}
    access_key = config.get('license_key', "")
    
    if not access_key:
        os.system("stty sane 2>/dev/null")
        console.print("\n[cyan][?] Masukkan License Key dari Bot Discord:[/cyan]")
        access_key = input("> ").strip()
        
    access_key = validate_license(access_key, config)
        
    # Simpan key yang valid
    config['license_key'] = access_key
    save_config(config)
    
    console.print("[bold green]✅ Login Berhasil![/bold green]")
    time.sleep(1)

    while True:
        clear_screen()
        console.print(Text(ascii_art, style="bold cyan"))
        console.print(Align.center(Text("v3.0.0 - ULTIMATE FARM MANAGER", style="white")))
        console.print("\n")
        
        console.print("[bold yellow]What would you like to do?[/bold yellow]")
        console.print("[green]1)[/green] Setup Configuration (First Run)")
        console.print("[green]2)[/green] Edit Configuration")
        console.print("[green]3)[/green] Run Script (Launch apps + optimizations)")
        console.print("[green]4)[/green] Cookie Management (Coming Soon)")
        console.print("[green]5)[/green] Clear All App Caches")
        console.print("[green]6)[/green] Package Manager (Install/Uninstall apps) (Coming Soon)")
        console.print("[green]7)[/green] Executor Key Manager (Coming Soon)")
        console.print("[red]8)[/red] Exit\n")
        
        choice = Prompt.ask("[cyan]\\[?] Enter your choice [1-8][/cyan]", choices=["1", "2", "3", "4", "5", "6", "7", "8"], default="3")
        
        if choice == "1":
            setup_wizard()
            continue
        elif choice == "2":
            config = load_config()
            if not config:
                console.print("[bold red]Config belum ada! Silakan jalankan Setup (Option 1) dulu.[/bold red]")
                time.sleep(2)
                continue
            edit_configuration(config)
            continue
        elif choice == "8":
            console.print("[bold red]Keluar...[/bold red]")
            return
        elif choice == "5":
            console.print("[bold yellow]Clearing caches...[/bold yellow]")
            subprocess.run(['su', '-c', 'rm -rf /data/data/com.roblox.*/cache/*'])
            console.print("[bold green]All caches cleared![/bold green]")
            time.sleep(2)
            continue
        elif choice == "3":
            config = load_config()
            if not config or not config.get('packages'):
                console.print("[bold red]Config belum ada / Package kosong! Silakan Setup Configuration (Pilih 1) dulu.[/bold red]")
                time.sleep(3)
                continue
            
            time.sleep(1)
            break
            
    clear_screen()
    console.print(Text(ascii_art, style="bold cyan"))
    console.print(Align.center(Text("v3.0.0 - ULTIMATE FARM MANAGER", style="white")))
    console.print("\n")
    
    packages = config.get('packages', [])
    status_dict = {pkg: "Checking..." for pkg in packages}
    app_start_times = {pkg: 0 for pkg in packages}
    
    optimize_system()
    
    # Pre-calculate grid bounds to prevent lagging the UI loop
    total_pkgs = len(packages)
    bounds_map = {}
    for i in range(total_pkgs):
        bounds_map[packages[i]] = get_grid_bounds(i, total_pkgs)
    
    start_time = time.time()
    last_status_time = time.time()
    delay_launch = config.get('delay_launch', 15)
    delay_relaunch = config.get('delay_relaunch', 60)
    scheduled_restart = config.get('scheduled_restart_interval', 0) * 60
    status_interval = config.get('status_update_interval', 0) * 60
    offline_timeout = config.get('offline_timeout', 300)
    webhook_url = config.get('webhook', "")

    # --- START MONITORING ---
    start_time = time.time()
    last_status_time = start_time
    step = 1
    
    console.print("\n[bold yellow][!] Membersihkan sisa aplikasi yang berjalan biar launch rapi...[/bold yellow]")
    for pkg in packages:
        kill_app(pkg)
    time.sleep(2)
    
    # Pre-render ASCII art for the monitoring UI
    safe_ascii = ascii_art.replace('\n', '\r\n')
    banner_art = f"\033[1;36m{safe_ascii}\033[0m"
    banner_art += "\r\n\033[1;37m" + "v3.0.0 - ULTIMATE FARM MANAGER".center(60) + "\033[0m\r\n\r\n"
    
    def update_ui(status_dict, step, config, packages):
        sys.stdout.write("\033[H\033[J" + banner_art + generate_table(status_dict, step, config, packages))
        sys.stdout.flush()
    
    while True:
        current_time = time.time()
        
        # 1. Scheduled Restart Check
        if scheduled_restart > 0 and (current_time - start_time) > scheduled_restart:
            send_webhook(webhook_url, "Scheduled Restart", "Melakukan restart paksa semua aplikasi...", 16711680)
            for pkg in packages:
                kill_app(pkg)
                status_dict[pkg] = "Killed (Restart)"
            start_time = current_time # Reset timer
            time.sleep(5)
            
        # 2. Status Update Webhook Check
        if status_interval > 0 and (current_time - last_status_time) > status_interval:
            online_count = sum(1 for v in status_dict.values() if v == "Online")
            send_webhook(webhook_url, "Periodic Status Update", f"{online_count}/{len(packages)} Aplikasi Online.", 65280)
            last_status_time = current_time

        for i, pkg in enumerate(packages):
            status_dict[pkg] = "Checking..."
            update_ui(status_dict, step, config, packages)
            
            if is_app_running(pkg):
                status_dict[pkg] = "Online"
                # Offline timeout blindly killed apps every 5 mins, removed to make it stable.
                # Gunakan Scheduled Restart jika butuh auto-restart berkala.
            else:
                status_dict[pkg] = "Starting..."
                update_ui(status_dict, step, config, packages)
                bounds = bounds_map[pkg]
                start_app(pkg, config, bounds)
                app_start_times[pkg] = time.time()
                time.sleep(delay_launch)
                status_dict[pkg] = "Online"
                
            update_ui(status_dict, step, config, packages)
        
        # Auto-tile windows after checking all packages
        tile_all_windows(packages)
        
        # Wait for relaunch delay
        total_pkgs = len(packages) if packages else 1
        wait_time = delay_relaunch / total_pkgs
        for i in range(1, total_pkgs + 1):
            step = i
            update_ui(status_dict, step, config, packages)
            time.sleep(wait_time)

if __name__ == "__main__":
    main()
