import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'webd-pay'))

import db

@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    db.init_db()
    db.seed_address_pool(['WEBD$addr1', 'WEBD$addr2'])

@pytest.fixture
def client(setup):
    import server
    server.app.config['TESTING'] = True
    with server.app.test_client() as c:
        yield c

def test_create_payment(client):
    r = client.post('/api/v1/payment/create',
                    json={'amount': 100.5},
                    environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert r.status_code == 200
    data = r.get_json()
    assert 'payment_id' in data
    assert data['pay_to'] == 'WEBD$addr1'
    assert data['amount_webd'] == 100.5
    assert 'secret' in data
    assert 'payment_url' in data

def test_create_payment_missing_amount(client):
    r = client.post('/api/v1/payment/create', json={},
                    environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert r.status_code == 400

def test_create_payment_no_addresses(client):
    # exhaust pool
    db.get_available_address()
    db.get_available_address()
    r = client.post('/api/v1/payment/create',
                    json={'amount': 1.0},
                    environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert r.status_code == 503

def test_get_status(client):
    r = client.post('/api/v1/payment/create',
                    json={'amount': 50.0},
                    environ_base={'REMOTE_ADDR': '127.0.0.1'})
    pid = r.get_json()['payment_id']
    r2 = client.get(f'/api/v1/payment/{pid}/status')
    assert r2.status_code == 200
    data = r2.get_json()
    assert data['status'] == 'pending'
    assert data['amount_webd'] == 50.0

def test_get_status_not_found(client):
    r = client.get('/api/v1/payment/nonexistent/status')
    assert r.status_code == 404
