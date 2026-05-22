import os, secrets, threading
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from flask import Flask, request, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

import config, db, node_client, webhook

app = Flask(__name__, static_folder='static')

# In-memory rate limiter: ip -> list of timestamps
_rate_buckets: dict[str, list] = defaultdict(list)
_rate_lock = threading.Lock()


def _check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)
    with _rate_lock:
        timestamps = [t for t in _rate_buckets[ip] if t > cutoff]
        if len(timestamps) >= config.RATE_LIMIT:
            return False
        timestamps.append(now)
        _rate_buckets[ip] = timestamps
    return True


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post('/api/v1/payment/create')
def create_payment():
    ip = request.remote_addr
    if not _check_rate_limit(ip):
        return jsonify({'error': 'rate limit exceeded'}), 429

    body = request.get_json(silent=True) or {}
    amount = body.get('amount')
    if not amount or not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'error': 'amount must be a positive number'}), 400

    address = db.get_available_address()
    if not address:
        return jsonify({'error': 'no payment addresses available, try again later'}), 503

    secret = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=config.TTL_MINUTES)).isoformat()

    payment = db.create_payment(
        amount_webd=float(amount),
        pay_to_address=address,
        expires_at=expires_at,
        secret=secret,
        merchant_id=body.get('merchant_id'),
        webhook_url=body.get('webhook_url'),
        redirect_url=body.get('redirect_url'),
        metadata=body.get('metadata'),
    )

    return jsonify({
        'payment_id': payment['id'],
        'pay_to': payment['pay_to_address'],
        'amount_webd': payment['amount_webd'],
        'expires_at': payment['expires_at'],
        'payment_url': f"{config.BASE_URL}/p/{payment['id']}",
        'secret': secret,
    })


@app.get('/api/v1/payment/<payment_id>/status')
def payment_status(payment_id):
    p = db.get_payment(payment_id)
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'payment_id': p['id'],
        'status': p['status'],
        'amount_webd': p['amount_webd'],
        'paid_amount_webd': p.get('paid_amount'),
        'confirmations': p.get('confirmations', 0),
        'tx_hash': p.get('tx_hash'),
    })


@app.get('/p/<payment_id>')
def payment_page(payment_id):
    return send_from_directory('static', 'pay.html')


@app.get('/')
def index():
    return send_from_directory('static', 'index.html')


# ── Background worker ─────────────────────────────────────────────────────────

def check_pending_payments():
    db.expire_old_payments()
    for p in db.get_pending_payments():
        bal = node_client.get_address_balance(p['pay_to_address'])
        if bal is None:
            continue
        if bal >= p['amount_webd']:
            db.update_payment_paid(p['id'], paid_amount=bal, tx_hash='')
            if p.get('webhook_url'):
                updated = db.get_payment(p['id'])
                webhook.dispatch(updated)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    db.init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_pending_payments, 'interval', seconds=15)
    scheduler.start()
    app.run(host='0.0.0.0', port=config.FLASK_PORT)
