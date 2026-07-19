import time, threading
from datetime import datetime, timedelta

from core.state import accounts, schedules, schedule_history, _data_lock
from core.persistence import save_data, log_activity


def calculate_next_run(schedule):
    now = datetime.now()
    time_parts = schedule.get('time', '12:00').split(':')
    hour = int(time_parts[0]) if len(time_parts) > 0 else 12
    minute = int(time_parts[1]) if len(time_parts) > 1 else 0
    repeat = schedule.get('repeat', 'daily')

    if repeat == 'once':
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
    elif repeat == 'daily':
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
    elif repeat.startswith('every_'):
        hours = int(repeat.split('_')[1]) if repeat.split('_')[1].isdigit() else 1
        next_run = now + timedelta(hours=hours)
    else:
        next_run = now + timedelta(days=1)

    return next_run.strftime('%Y-%m-%d %H:%M:%S')


def check_schedules():
    now = datetime.now()
    with _data_lock:
        for sched in schedules:
            if not sched.get('enabled'):
                continue
            next_run_str = sched.get('next_run', '')
            if not next_run_str:
                continue
            try:
                next_run = datetime.strptime(next_run_str, '%Y-%m-%d %H:%M:%S')
            except:
                continue
            if next_run > now:
                continue
            account = sched.get('account', '')
            target = sched.get('target', '')
            items = sched.get('items', [])
            if not account or not target or not items:
                continue
            target_id = 0
            for acc in accounts:
                if acc.get('name', '').lower() == target.lower():
                    target_id = int(acc.get('verified_id', 0))
                    break
            if not target_id:
                from blueprints.mailbox import lookup_user_id
                target_id = lookup_user_id(target)
            if not target_id:
                log_activity(f'Schedule {sched["id"]}: target "{target}" not found', 'warning')
                continue
            from blueprints.mailbox import mailbox_commands, command_lock
            cmd_id = f"mail_{int(time.time() * 1000)}"
            cmd_items = [{'name': item.get('name', ''), 'id': item.get('id', ''), 'category': item.get('category', 'Other'), 'count': item.get('qty', 1)} for item in items]
            command = {'id': cmd_id, 'type': 'send_mail', 'account': account, 'target': target, 'target_id': target_id, 'items': cmd_items, 'note': 'Scheduled send', 'timestamp': time.time(), 'status': 'pending'}
            with command_lock:
                mailbox_commands.append(command)
            history_entry = {'id': f"hist_{int(time.time() * 1000)}", 'schedule_id': sched['id'], 'account': account, 'target': target, 'items_sent': sum(item.get('qty', 1) for item in items), 'status': 'queued', 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'), 'message': f'{len(items)} items queued'}
            schedule_history.append(history_entry)
            if len(schedule_history) > 500:
                schedule_history.pop(0)
            sched['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
            sched['next_run'] = calculate_next_run(sched)
            log_activity(f'Schedule executed: {account} → {target} ({len(items)} items)')
            from services.webhook import send_webhook
            send_webhook(f'📤 Scheduled Send', f'**From:** {account}\n**To:** {target}\n**Items:** {len(items)} items\n**Time:** {time.strftime("%H:%M:%S")}', 0x3498db)
    save_data()


def start_scheduler():
    def scheduler_loop():
        while True:
            try:
                check_schedules()
            except Exception as e:
                print(f'[Scheduler] Error: {e}')
            time.sleep(60)
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    print('[Scheduler] Started (checks every 60s)')
