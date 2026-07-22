import re
import time
import uuid

from flask import Blueprint, request, jsonify

from models import accounts, settings, custom_scripts, log_activity, save_data
from services.adb import (
    get_serial, adb_connect, adb_check_roblox, push_custom_script_to_vm
)

scripts_bp = Blueprint('scripts', __name__)

MAX_SCRIPT_SIZE = 100 * 1024  # 100 KB
MAX_SCRIPTS = 50
SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9_\-\. ]{1,50}$')
SAFE_FILENAME_RE = re.compile(r'^[A-Za-z0-9_\-\.]{1,60}$')


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _normalize_filename(name, filename):
    """Return a safe .luau filename based on provided filename or name."""
    candidate = (filename or '').strip() or (name or '').strip() or 'script'
    if '/' in candidate or '\\' in candidate or '..' in candidate:
        return None
    if not SAFE_FILENAME_RE.match(candidate):
        return None
    if not candidate.lower().endswith(('.luau', '.lua')):
        candidate += '.luau'
    return candidate


def _find_script(script_id):
    return next((s for s in custom_scripts if s.get('id') == script_id), None)


def _script_meta(s):
    return {
        'id': s.get('id'),
        'name': s.get('name'),
        'filename': s.get('filename'),
        'size': len(s.get('content', '') or ''),
        'created_at': s.get('created_at'),
        'updated_at': s.get('updated_at'),
    }


# ---------------------------------------------------------------- CRUD

@scripts_bp.route('/api/scripts', methods=['GET'])
def list_scripts():
    return jsonify({'scripts': [_script_meta(s) for s in custom_scripts]})


@scripts_bp.route('/api/scripts/<script_id>', methods=['GET'])
def get_script(script_id):
    s = _find_script(script_id)
    if not s:
        return jsonify({'error': 'Script not found'}), 404
    data = _script_meta(s)
    data['content'] = s.get('content', '')
    return jsonify(data)


@scripts_bp.route('/api/scripts', methods=['POST'])
def create_script():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    content = data.get('content') or ''
    filename = data.get('filename') or ''

    if not name or not SAFE_NAME_RE.match(name):
        return jsonify({'error': 'Nama script tidak valid (1-50 karakter: huruf, angka, spasi, - _ .)'}), 400
    if not content.strip():
        return jsonify({'error': 'Isi script tidak boleh kosong'}), 400
    if len(content.encode('utf-8')) > MAX_SCRIPT_SIZE:
        return jsonify({'error': 'Ukuran script melebihi 100 KB'}), 400

    safe_filename = _normalize_filename(name, filename)
    if not safe_filename:
        return jsonify({'error': 'Nama file tidak valid'}), 400

    if len(custom_scripts) >= MAX_SCRIPTS:
        return jsonify({'error': f'Maksimal {MAX_SCRIPTS} script tersimpan'}), 400

    if any(s.get('name') == name for s in custom_scripts):
        return jsonify({'error': 'Nama script sudah dipakai'}), 400

    script = {
        'id': uuid.uuid4().hex[:12],
        'name': name,
        'filename': safe_filename,
        'content': content,
        'created_at': _now(),
        'updated_at': _now(),
    }
    custom_scripts.append(script)
    save_data()
    log_activity(f'Custom script "{name}" disimpan')
    return jsonify({'success': True, 'script': _script_meta(script)})


@scripts_bp.route('/api/scripts/<script_id>', methods=['PUT'])
def update_script(script_id):
    s = _find_script(script_id)
    if not s:
        return jsonify({'error': 'Script not found'}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    content = data.get('content')
    filename = data.get('filename') or ''

    if name:
        if not SAFE_NAME_RE.match(name):
            return jsonify({'error': 'Nama script tidak valid'}), 400
        if any(x.get('name') == name and x.get('id') != script_id for x in custom_scripts):
            return jsonify({'error': 'Nama script sudah dipakai'}), 400
        s['name'] = name

    if content is not None:
        if not content.strip():
            return jsonify({'error': 'Isi script tidak boleh kosong'}), 400
        if len(content.encode('utf-8')) > MAX_SCRIPT_SIZE:
            return jsonify({'error': 'Ukuran script melebihi 100 KB'}), 400
        s['content'] = content

    if filename:
        safe_filename = _normalize_filename(s.get('name', ''), filename)
        if not safe_filename:
            return jsonify({'error': 'Nama file tidak valid'}), 400
        s['filename'] = safe_filename

    s['updated_at'] = _now()
    save_data()
    log_activity(f'Custom script "{s.get("name")}" diupdate')
    return jsonify({'success': True, 'script': _script_meta(s)})


@scripts_bp.route('/api/scripts/<script_id>', methods=['DELETE'])
def delete_script(script_id):
    s = _find_script(script_id)
    if not s:
        return jsonify({'error': 'Script not found'}), 404
    custom_scripts.remove(s)
    save_data()
    log_activity(f'Custom script "{s.get("name")}" dihapus')
    return jsonify({'success': True})


# ---------------------------------------------------------------- PUSH

def _push_to_account(s, acc):
    """Push script s to the VM of a single account. Returns result dict."""
    instance = acc.get('mumu_instance', 0)
    serial = get_serial(instance)
    if not serial:
        return {'account': acc.get('name', '?'), 'instance': instance,
                'status': 'error', 'message': f'No serial for instance {instance}'}
    ok, msg = adb_connect(serial)
    if not ok:
        return {'account': acc.get('name', '?'), 'instance': instance,
                'status': 'error', 'message': f'ADB: {msg}'}
    success, result_msg = push_custom_script_to_vm(
        s.get('content', ''), s.get('filename', 'script.luau'), acc, serial.strip()
    )
    return {
        'account': acc.get('name', '?'),
        'instance': instance,
        'status': 'ok' if success else 'error',
        'message': 'Script pushed' if success else result_msg,
    }


@scripts_bp.route('/api/scripts/<script_id>/push', methods=['POST'])
def push_script(script_id):
    s = _find_script(script_id)
    if not s:
        return jsonify({'error': 'Script not found'}), 404

    data = request.get_json(silent=True) or {}
    target = data.get('target', 'all')  # 'all' | 'active' | account id

    results = []

    if target == 'active':
        # Push to all instances with running Roblox (like /api/push-all-active)
        serials = settings.get('mumu_serials', [])
        for idx, serial in enumerate(serials):
            if not serial or not serial.strip():
                continue
            serial = serial.strip()
            ok, _ = adb_connect(serial)
            if not ok:
                results.append({'instance': idx, 'serial': serial,
                                'status': 'error', 'message': 'ADB connect failed'})
                continue
            if not adb_check_roblox(serial):
                results.append({'instance': idx, 'serial': serial,
                                'status': 'skipped', 'message': 'Roblox not running'})
                continue
            acc = next((a for a in accounts
                        if a.get('mumu_instance') == idx and a.get('cookie')), None)
            if not acc:
                acc = {'id': f'vm{idx}', 'name': f'VM #{idx}',
                       'mumu_instance': idx, 'package_name': ''}
            success, result_msg = push_custom_script_to_vm(
                s.get('content', ''), s.get('filename', 'script.luau'), acc, serial
            )
            results.append({'instance': idx, 'serial': serial,
                            'account': acc.get('name', '?'),
                            'status': 'ok' if success else 'error',
                            'message': 'Script pushed' if success else result_msg})

    elif target == 'all':
        # Push to every account
        if not accounts:
            return jsonify({'error': 'Tidak ada akun terdaftar'}), 400
        for acc in accounts:
            results.append(_push_to_account(s, acc))

    else:
        # target = specific account id
        acc = next((a for a in accounts if a.get('id') == target), None)
        if not acc:
            return jsonify({'error': 'Account not found'}), 404
        results.append(_push_to_account(s, acc))

    ok_count = sum(1 for r in results if r['status'] == 'ok')
    if ok_count:
        log_activity(f'Custom script "{s.get("name")}" dipush ke {ok_count} target')
    return jsonify({'success': True, 'results': results,
                    'pushed': ok_count, 'total': len(results)})
