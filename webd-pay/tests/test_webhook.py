import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'webd-pay'))

from unittest.mock import patch, Mock, call
import webhook

PAYMENT = {
    'id': 'test-uuid',
    'merchant_id': 'shop1',
    'amount_webd': 50.0,
    'paid_amount': 50.0,
    'tx_hash': 'abc',
    'confirmations': 1,
    'metadata': None,
    'webhook_url': 'https://example.com/hook',
    'secret': 'mysecret',
    'webhook_attempts': 0,
}

def test_signature_correct():
    import hmac, hashlib, json
    body = b'{"test": 1}'
    sig = webhook.compute_signature('mysecret', body)
    expected = hmac.new(b'mysecret', body, hashlib.sha256).hexdigest()
    assert sig == expected

def test_send_success():
    mock_resp = Mock()
    mock_resp.status_code = 200
    with patch('webhook.requests.post', return_value=mock_resp) as mock_post, \
         patch('webhook.db.update_webhook_status') as mock_db:
        webhook.send_webhook(PAYMENT)
    mock_post.assert_called_once()
    mock_db.assert_called_with('test-uuid', 'sent', 1)

def test_send_retry_then_success():
    fail = Mock()
    fail.status_code = 500
    ok = Mock()
    ok.status_code = 200
    with patch('webhook.requests.post', side_effect=[fail, fail, ok]), \
         patch('webhook.db.update_webhook_status') as mock_db, \
         patch('webhook.time.sleep'):
        webhook.send_webhook(PAYMENT)
    assert mock_db.call_args[0][1] == 'sent'

def test_send_all_fail():
    fail = Mock()
    fail.status_code = 500
    with patch('webhook.requests.post', return_value=fail), \
         patch('webhook.db.update_webhook_status') as mock_db, \
         patch('webhook.time.sleep'):
        webhook.send_webhook(PAYMENT)
    assert mock_db.call_args[0][1] == 'failed'
