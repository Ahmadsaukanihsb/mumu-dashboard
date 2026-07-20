import uuid, time

from models import _data_lock, log_account, log_activity, save_data
from services.roblox import build_deep_link


def is_cloudphone(acc):
    return bool(acc.get('package_name') and acc.get('device_id'))


def queue_remote_join(acc, link, sv):
    from blueprints.mailbox import mailbox_commands, mailbox_results, command_lock
    cmd_id = f'join-{uuid.uuid4().hex[:8]}'
    command = {
        'id': cmd_id,
        'type': 'join',
        'account': acc['name'],
        'package': acc['package_name'],
        'link': link,
        'timestamp': time.time(),
        'status': 'pending'
    }
    with command_lock:
        mailbox_commands.append(command)
        mailbox_results[cmd_id] = {'status': 'pending', 'message': 'Menunggu remote monitor...'}
    log_account(acc['id'], acc['name'], f'Join command queued → remote monitor ({acc.get("device_id")})')
    return cmd_id


def cloudphone_join(acc, sv):
    link = build_deep_link(sv)
    if not link:
        return None, None
    with _data_lock:
        acc['status'] = 'joining'
        acc['active'] = True
    save_data()
    log_account(acc['id'], acc['name'], f'Joining server "{sv["name"]}"')
    cmd_id = queue_remote_join(acc, link, sv)
    return link, cmd_id


def cloudphone_rollback(acc, sv):
    link = build_deep_link(sv)
    if not link:
        return None
    queue_remote_join(acc, link, sv)
    with _data_lock:
        acc['status'] = 'rollback'
    log_account(acc['id'], acc.get('name', '?'), f'Rollback → remote monitor rejoin ke {sv["name"]}')
    log_activity(f'[{acc.get("name", "?")}] Rollback via remote monitor')
    save_data()
    return link
