import hmac, hashlib, json, time, threading
from datetime import datetime, timezone

import requests
import db

RETRY_DELAYS = [0, 30, 120, 600, 3600]  # seconds between attempts
TIMEOUT = 10


def compute_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def send_webhook(payment: dict):
    url = payment['webhook_url']
    secret = payment['secret']
    payload = {
        'event': 'payment.confirmed',
        'payment_id': payment['id'],
        'merchant_id': payment.get('merchant_id'),
        'amount_webd': payment['amount_webd'],
        'paid_amount_webd': payment.get('paid_amount'),
        'tx_hash': payment.get('tx_hash', ''),
        'confirmations': payment.get('confirmations', 1),
        'metadata': json.loads(payment['metadata']) if payment.get('metadata') else None,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload, separators=(',', ':')).encode()
    sig = compute_signature(secret, body)
    headers = {
        'Content-Type': 'application/json',
        'X-WEBD-Signature': sig,
    }
    attempts = payment.get('webhook_attempts', 0)
    for delay in RETRY_DELAYS:
        if delay > 0:
            time.sleep(delay)
        try:
            r = requests.post(url, data=body, headers=headers, timeout=TIMEOUT)
            attempts += 1
            if 200 <= r.status_code < 300:
                db.update_webhook_status(payment['id'], 'sent', attempts)
                return
        except Exception:
            attempts += 1
    db.update_webhook_status(payment['id'], 'failed', attempts)


def dispatch(payment: dict):
    """Fire-and-forget webhook in a daemon thread."""
    t = threading.Thread(target=send_webhook, args=(payment,), daemon=True)
    t.start()
