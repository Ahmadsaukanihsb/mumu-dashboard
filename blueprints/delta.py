from flask import Blueprint, request, jsonify

from models import accounts
from services.delta import delta_refresh_key_for_acc

delta_bp = Blueprint('delta', __name__)

@delta_bp.route('/api/delta/refresh-key', methods=['POST'])
def delta_refresh_key():
    data = request.json or {}
    acc_id = data.get('account_id')
    results = []
    for acc in accounts:
        if acc_id and acc['id'] != acc_id:
            continue
        r = delta_refresh_key_for_acc(acc)
        r['account_id'] = acc['id']
        r['account_name'] = acc['name']
        results.append(r)
    return jsonify({'results': results})

@delta_bp.route('/api/delta/refresh-key/<acc_id>', methods=['POST'])
def delta_refresh_key_one(acc_id):
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc:
        return jsonify({'error': 'Account not found'}), 404
    r = delta_refresh_key_for_acc(acc)
    r['account_id'] = acc['id']
    return jsonify(r)
