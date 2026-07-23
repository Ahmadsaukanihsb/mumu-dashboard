import time, threading, sys

# Bug #1 fix: import models as _models di atas sebelum fungsi-fungsi didefinisikan
import models as _models

def debug(*args):
    sys.stderr.write('[MONITOR] ' + ' '.join(str(a) for a in args) + '\n')
    sys.stderr.flush()

from models import accounts, servers, settings, monitor_state, _data_lock, _join_threads, _join_threads_lock, _join_timestamps, user_shutdown_instances, log_account, log_activity, save_data, get_package_name, decrypt_cookie
from services.adb import get_serial, adb_connect, adb_check_roblox, adb_get_thread_count, adb_dismiss_dialogs, adb_check_in_game, adb_detect_kicked_dialog, adb_force_stop_roblox, adb_check_in_foreground, adb_check_network_active, adb_check_udp_active
from services.mumu import ensure_vm_running, launch_mumu, send_join_intent
from services.roblox import verify_cookie, build_public_link
from services.webhook import send_webhook
from config import JOIN_COOLDOWN

def should_join(st):
    return time.time() - st.get('last_intent', 0) >= 60

def monitor_loop():
    while _models.monitor_running:
        try:
            interval = settings.get('monitor_interval', 5)
            rejoin_interval = settings.get('rejoin_interval', 2400)
            now = time.time()
            debug('cycle start', len(list(accounts)), 'accounts')
            for acc in list(accounts):
                aj = acc.get('auto_join')
                if not aj:
                    continue
                acc_id = acc.get('id', '')
                debug('processing', acc.get("name","?"), f'(id={acc_id}, auto_join={aj})')
                if acc.get('package_name') and acc.get('remote'):
                    debug(acc.get("name","?"), 'remote account, skipping (managed by Termux)')
                    continue
                instance = acc.get('mumu_instance', 0)
                package = acc.get('package_name', '') or 'com.roblox.client'
                serial = get_serial(instance)
                if not serial:
                    debug(acc.get("name","?"), 'serial None (instance={})'.format(instance))
                    continue
                ok, msg = adb_connect(serial)
                if not ok:
                    debug(acc.get("name","?"), f'ADB connect fail ({serial}):', msg)
                    if settings.get('auto_restart_vm', True) and instance not in user_shutdown_instances:
                        ensure_vm_running(serial, instance)
                    continue
                user_shutdown_instances.discard(instance)
                running = adb_check_roblox(serial, package)
                was_active = acc.get('status') in ('connected', 'monitoring', 'active')
                cur_status = acc.get('status', 'idle')
                debug(acc.get("name","?"), f'running={running} was_active={was_active} cur_status={cur_status} pkg={package}')

                if running and not was_active:
                    with _data_lock:
                        acc['status'] = 'monitoring'
                        acc['active'] = True
                        st = monitor_state.setdefault(acc_id, {})
                        if 'last_intent' not in st:
                            st['last_intent'] = time.time()
                        st['tc_history'] = []
                    save_data()

                if not running and (was_active or cur_status in ('idle', 'error', 'disconnected')):
                    st = monitor_state.setdefault(acc_id, {})
                    last_intent = st.get('last_intent', 0)
                    now = time.time()
                    if now - last_intent < 60:
                        debug(acc.get("name","?"), f'cooldown ({int(60 - (now - last_intent))}s left), skipping')
                        continue
                    debug(acc.get("name","?"), f'rejoin trigger (status={cur_status})')
                    with _data_lock:
                        acc['status'] = 'disconnected'
                        acc['active'] = False
                        st['last_intent'] = now
                        st['in_game'] = False
                    if was_active:
                        log_account(acc_id, acc['name'], 'Roblox exited, rejoining...')
                        send_webhook(
                            f'🔄 {acc["name"]} — Roblox Closed',
                            f'Auto-rejoin aktif\n**Instance:** MuMu-{acc.get("mumu_instance", "?")}\n**Package:** {package}',
                            0x3498db,
                            acc.get('verified_avatar')
                        )
                    else:
                        log_account(acc_id, acc['name'], f'Auto-join: {cur_status} → joining...')
                    sv = next((s for s in servers if s['id'] == acc.get('server_id')), None)
                    if not sv and servers:
                        sv = servers[0]
                    if sv:
                        c = acc.get('cookie', '')
                        cookie = decrypt_cookie(c) if c and c.startswith('enc:') else c
                        link = build_public_link(sv)
                        if link:
                            with _join_threads_lock:
                                if acc_id not in _join_threads:
                                    _join_threads.add(acc_id)
                                    _join_timestamps[acc_id] = now
                                elif now - _join_timestamps.get(acc_id, 0) > 15:
                                    _join_timestamps[acc_id] = now
                                else:
                                    link = None
                            if link:
                                threading.Thread(target=launch_mumu, args=(acc, link, sv, acc_id), daemon=True).start()
                    continue

                if running and was_active:
                    with _data_lock:
                        st = monitor_state.setdefault(acc_id, {})
                        was_in_game = st.get('in_game', False)
                    tc = adb_get_thread_count(serial, package)
                    foreground = adb_check_in_foreground(serial, package)
                    network = adb_check_network_active(serial, package)
                    udp_active = adb_check_udp_active(serial, package)

                    if tc is not None:
                        with _data_lock:
                            st['last_tc'] = tc
                        threshold = settings.get('thread_threshold', 80)
                        in_game = tc >= threshold and foreground
                        if not in_game and tc >= threshold:
                            # Fallback: check UI directly when thread count is high but foreground check fails
                            ui_check = adb_check_in_game(serial, package)
                            if ui_check is True:
                                in_game = True
                                foreground = True

                        # HYSTERESIS: prevent false "home screen" when tc drops slightly below threshold
                        # but UDP is still active (Roblox still connected to game server)
                        if not in_game and was_in_game and udp_active is True and tc >= (threshold - 15):
                            in_game = True
                            debug(acc.get("name","?"), f'hysteresis: tc={tc} < {threshold} but UDP active, still in-game')

                        # UDP-only detection: if thread count unreliable but UDP is very active, likely in-game
                        if not in_game and udp_active is True and tc >= 50:
                            in_game = True
                            debug(acc.get("name","?"), f'udp-based detection: tc={tc}, UDP active, in-game')

                        game_start = st.get('in_game_since', 0)
                        if in_game and game_start == 0:
                            st['in_game_since'] = now
                        elif not in_game:
                            st['in_game_since'] = 0

                        last_intent = st.get('last_intent', 0)
                        if now - last_intent < 60:
                            debug(acc.get("name","?"), f'loading (tc={tc}, fg={foreground}), waiting...')
                            continue

                        if not in_game and foreground and tc < threshold and (now - st.get('last_dismiss_check', 0)) >= 30:
                            st['last_dismiss_check'] = now
                            adb_dismiss_dialogs(serial)

                        last_act = st.get('last_activity_check', 0)
                        if in_game and (now - last_act) >= 15:
                            st['last_activity_check'] = now
                            activity_check = adb_check_in_game(serial, package)
                            if activity_check is False:
                                log_account(acc_id, acc['name'], f'activity check: home screen (tc={tc}), trusting thread count')
                            elif activity_check is True:
                                log_account(acc_id, acc['name'], f'activity check: in-game confirmed (tc={tc})')
                            st['activity_fail_count'] = 0

                        if (now - st.get('last_kicked_check', 0)) >= 15:
                            st['last_kicked_check'] = now
                            kick_result = adb_detect_kicked_dialog(serial, package)
                            if kick_result:
                                log_account(acc_id, acc['name'], f'kicked detected [{kick_result}], rejoining...')
                                send_webhook(f'⚠️ {acc["name"]} — Kicked/Disconnect', f'Dialog detected [{kick_result}]\n**Package:** {package}', 0xffaa00, acc.get('verified_avatar'))
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()
                                st['in_game'] = False
                                st['in_game_since'] = 0
                                continue

                        prev_in_game = st.get('in_game')
                        if prev_in_game is True and tc < threshold:
                            st['drop_count'] = st.get('drop_count', 0) + 1
                            in_game_since = st.get('in_game_since', 0)
                            if st['drop_count'] >= 3 and in_game_since > 0 and (now - in_game_since) >= 30:
                                log_account(acc_id, acc['name'], f'thread drop detected [tc={tc}, drop_count={st["drop_count"]}], rejoining...')
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()
                                st['in_game'] = False
                                st['in_game_since'] = 0
                                st['drop_count'] = 0
                                continue
                        else:
                            st['drop_count'] = 0

                        if in_game:
                            if not was_in_game and not st.get('in_game_notified', False):
                                st['in_game_notified'] = True
                                log_account(acc_id, acc['name'], f'in-game detected (tc={tc}, fg={foreground}, net={network}, udp={udp_active})')
                                send_webhook(f'✅ {acc["name"]} — In Game', f'Account berhasil masuk ke game\n**Package:** {package}\n**TC:** {tc}', 0x43e97b, acc.get('verified_avatar'))
                            st['in_game'] = True
                        elif was_in_game:
                            st['in_game_notified'] = False
                            if should_join(st):
                                log_account(acc_id, acc['name'], f'home screen (threads={tc}, fg={foreground}, udp={udp_active}), rejoining...')
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()
                            st['in_game'] = False
                        else:
                            last_rejoin = st.get('last_intent', 0)
                            if now - last_rejoin >= JOIN_COOLDOWN:
                                log_account(acc_id, acc['name'], f'still home (threads={tc}, udp={udp_active}), rejoining...')
                                send_join_intent(acc, serial)
                                st['last_intent'] = time.time()

                    else:
                        last_rejoin = st.get('last_intent', 0)
                        if was_active and (now - last_rejoin) >= 600:
                            log_account(acc_id, acc['name'], 'fallback rejoin (threads unknown for 10min)')
                            send_join_intent(acc, serial)
                            st['last_intent'] = time.time()
                        elif not was_active and (now - last_rejoin) >= 120:
                            log_account(acc_id, acc['name'], 'fallback rejoin (threads unknown)')
                            send_join_intent(acc, serial)
                            st['last_intent'] = time.time()

                last_join = acc.get('last_join_time', 0)
                if running and rejoin_interval > 0 and (now - last_join) >= rejoin_interval:
                    st = monitor_state.setdefault(acc_id, {})
                    log_account(acc_id, acc['name'], f'rejoin periodik ({int(rejoin_interval//60)} menit)')
                    send_join_intent(acc, serial)
                    st['last_intent'] = time.time()
                    st['in_game_since'] = 0

            av_interval = settings.get('auto_verify_interval', 0)
            if av_interval > 0:
                last_v = getattr(monitor_loop, '_last_auto_verify', 0)
                if now - last_v >= av_interval * 3600:
                    monitor_loop._last_auto_verify = now
                    log_activity('Auto-verify: memverifikasi semua cookie...')
                    for acc in accounts:
                        cookie = acc.get('cookie', '')
                        if cookie:
                            result = verify_cookie(cookie)
                            if result.get('valid'):
                                with _data_lock:
                                    acc['verified_username'] = result['username']
                                    acc['verified_robux'] = result['robux']
                                    acc['verified_avatar'] = result.get('avatar', '')
                                    acc['verified_id'] = result.get('id', '')
                    save_data()
                    log_activity(f'Auto-verify selesai ({len(accounts)} akun)')

            time.sleep(interval)
        except Exception as e:
            print(f'[MONITOR ERROR] {e}')
            import traceback
            traceback.print_exc()
            time.sleep(5)

def delta_key_loop():
    from services.delta import delta_key_store, delta_refresh_key_for_acc
    while _models.monitor_running:
        if settings.get('delta_auto_key', False):
            now = time.time()
            interval = 22 * 3600
            for acc in list(accounts):
                if not _models.monitor_running:
                    return
                acc_id = acc.get('id', '')
                entry = delta_key_store.get(acc_id, {})
                last_upd = entry.get('updated_at', 0)
                if entry.get('key') and now - last_upd < interval:
                    continue
                delta_refresh_key_for_acc(acc)
                time.sleep(10)
        for _ in range(60):
            # Bug #2 fix: gunakan _models.monitor_running bukan monitor_running lokal (stale reference)
            if not _models.monitor_running:
                return
            time.sleep(1)

_monitor_thread = None
_dk_thread = None

def start_monitor():
    global _monitor_thread, _dk_thread
    if _models.monitor_running:
        return
    _models.monitor_running = True
    _monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    _monitor_thread.start()
    _dk_thread = threading.Thread(target=delta_key_loop, daemon=True)
    _dk_thread.start()
    debug('started', f'({len(_models.accounts)} accounts, interval={_models.settings.get("monitor_interval", 5)}s)')

def stop_monitor():
    _models.monitor_running = False
