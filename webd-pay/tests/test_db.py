import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'webd-pay'))

import db

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    db.init_db()

def test_create_and_get_payment():
    p = db.create_payment(amount_webd=50.0, pay_to_address='WEBD$test',
                          expires_at='2030-01-01T00:00:00Z', secret='abc')
    got = db.get_payment(p['id'])
    assert got['amount_webd'] == 50.0
    assert got['status'] == 'pending'

def test_update_payment_status():
    p = db.create_payment(amount_webd=10.0, pay_to_address='WEBD$x',
                          expires_at='2030-01-01T00:00:00Z', secret='s')
    db.update_payment_paid(p['id'], paid_amount=10.0, tx_hash='abc123')
    got = db.get_payment(p['id'])
    assert got['status'] == 'paid'
    assert got['tx_hash'] == 'abc123'

def test_address_pool():
    db.seed_address_pool(['WEBD$addr1', 'WEBD$addr2'])
    addr = db.get_available_address()
    assert addr in ('WEBD$addr1', 'WEBD$addr2')
    db.release_address(addr)
    addr2 = db.get_available_address()
    assert addr2 is not None

def test_get_pending_payments():
    db.create_payment(amount_webd=1.0, pay_to_address='WEBD$p',
                      expires_at='2030-01-01T00:00:00Z', secret='s')
    pending = db.get_pending_payments()
    assert len(pending) == 1

def test_expire_old_payments():
    db.create_payment(amount_webd=1.0, pay_to_address='WEBD$p',
                      expires_at='2020-01-01T00:00:00Z', secret='s')
    db.expire_old_payments()
    pending = db.get_pending_payments()
    assert len(pending) == 0
