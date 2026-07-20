import threading, time

from flask import Blueprint, jsonify

from models import accounts, servers, _data_lock, _join_threads, _join_threads_lock, log_account, log_activity, save_data, decrypt_cookie
from services.cloudphone_service import is_cloudphone, cloudphone_join, cloudphone_rollback
from services.mumu import launch_mumu, mumu_rollback
from services.roblox import build_public_link

join_bp = Blueprint('join', __name__)


def _get_cookie(acc):
    c = acc.get('cookie', '')
    if c:
        return decrypt_cookie(c) if c.startswith('enc:') else c
    return None


@join_bp.route('/api/accounts/<acc_id>/join', methods=['POST'])
def join_server(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    sv = None
    if acc.get('server_id'):
        sv = next((s for s in servers if s['id'] == acc['server_id']), None)
    if not sv and servers:
        sv = servers[0]
    if not sv:
        return jsonify({'error': 'No server configured'}), 400

    if is_cloudphone(acc):
        link, cmd_id = cloudphone_join(acc, sv)
        if not link:
            return jsonify({'error': 'Could not build join link'}), 400
        return jsonify({'status': 'joining', 'link': link, 'via': 'remote_monitor', 'command_id': cmd_id})

    link = build_public_link(sv)
    if not link:
        return jsonify({'error': 'Could not build join link'}), 400
    with _data_lock:
        acc['status'] = 'joining'
        acc['active'] = True
    save_data()
    log_account(acc['id'], acc['name'], f'Joining server "{sv["name"]}"')
    with _join_threads_lock:
        if acc['id'] not in _join_threads:
            _join_threads.add(acc['id'])
            threading.Thread(target=launch_mumu, args=(acc, link, sv, acc['id']), daemon=True).start()
    return jsonify({'status': 'joining', 'link': link})


@join_bp.route('/api/join-all', methods=['POST'])
def join_all():
    if not servers:
        return jsonify({'error': 'No servers configured'}), 400
    sv = servers[0]
    count = 0
    remote_count = 0
    for acc in accounts:
        if not (acc.get('cookie') or is_cloudphone(acc)):
            continue
        with _data_lock:
            acc['status'] = 'joining'
            acc['active'] = True

        if is_cloudphone(acc):
            link, _ = cloudphone_join(acc, sv)
            if link:
                remote_count += 1
        else:
            link = build_public_link(sv)
            if link:
                with _join_threads_lock:
                    if acc['id'] not in _join_threads:
                        _join_threads.add(acc['id'])
                        threading.Thread(target=launch_mumu, args=(acc, link, sv, acc['id']), daemon=True).start()
                        count += 1
    save_data()
    log_activity(f'Join all: {count} MuMu + {remote_count} Cloudphone accounts starting')
    return jsonify({'status': 'joining', 'count': count, 'remote_count': remote_count})


@join_bp.route('/api/accounts/<acc_id>/disconnect', methods=['POST'])
def disconnect_account(acc_id):
    acc = None
    with _data_lock:
        found = next((a for a in accounts if a['id'] == acc_id), None)
        if found:
            found['active'] = False
            found['status'] = 'idle'
            acc = found
    if acc:
        save_data()
        log_account(acc['id'], acc['name'], 'Disconnected')
    return jsonify({'success': True})


@join_bp.route('/api/accounts/<acc_id>/rollback', methods=['POST'])
def rollback_account(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    sv = next((s for s in servers if acc.get('server_ids') and s['id'] in acc.get('server_ids')), None) or (servers[0] if servers else None)
    if not sv:
        return jsonify({'error': 'No server configured'}), 400

    if is_cloudphone(acc):
        link = cloudphone_rollback(acc, sv)
        if link:
            return jsonify({'success': True, 'message': f'Rollback via remote monitor → {sv["name"]}'})
        return jsonify({'error': 'Failed to build join link'}), 500

    link = mumu_rollback(acc, sv)
    if link:
        return jsonify({'success': True, 'message': f'Rollback: force-stop + rejoin {sv["name"]}'})
    return jsonify({'error': 'Rollback failed'}), 500
