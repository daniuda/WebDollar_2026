import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import transfer


@pytest.fixture
def priv_hex():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    return priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()


# ── derive_address_from_privkey ───────────────────────────────────────────────

def test_derive_address_known_vector():
    KNOWN_PRIVKEY = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2'
    EXPECTED_ADDRESS = 'WEBD$gCSiDjWPw+C6PD7NNWoskcX1G@K#QBJQ$7$'
    EXPECTED_PUBKEY = '8233bb03b39099365a86bfead59869e1a17806ef7576da81da9b9bd66f3bf787'
    address, pubkey_hex = transfer.derive_address_from_privkey(KNOWN_PRIVKEY)
    assert address == EXPECTED_ADDRESS
    assert pubkey_hex == EXPECTED_PUBKEY


def test_derive_address_invalid_hex():
    with pytest.raises(ValueError, match='invalid'):
        transfer.derive_address_from_privkey('not-hex')


def test_derive_address_wrong_length():
    with pytest.raises(ValueError, match='invalid'):
        transfer.derive_address_from_privkey('abcd')  # too short


# ── send_webd ────────────────────────────────────────────────────────────────

def test_send_webd_success(priv_hex):
    mock_import = MagicMock()
    mock_import.status_code = 200
    mock_import.json.return_value = {'result': True, 'address': 'WEBD$abc'}

    mock_tx = MagicMock()
    mock_tx.status_code = 200
    mock_tx.json.return_value = {'result': True, 'txId': 'deadbeef01234567'}

    with patch('requests.get', side_effect=[mock_import, mock_tx]):
        result = transfer.send_webd(priv_hex, 'WEBD$gDest123', 5.0, 0.0001)

    assert result['result'] is True
    assert result['txId'] == 'deadbeef01234567'


def test_send_webd_wallet_already_imported(priv_hex):
    mock_import = MagicMock()
    mock_import.status_code = 200
    mock_import.json.return_value = {'result': False, 'message': 'already exists'}

    mock_tx = MagicMock()
    mock_tx.status_code = 200
    mock_tx.json.return_value = {'result': True, 'txId': 'aabbccdd'}

    with patch('requests.get', side_effect=[mock_import, mock_tx]):
        result = transfer.send_webd(priv_hex, 'WEBD$gDest123', 5.0, 0.0001)
    assert result['result'] is True


def test_send_webd_node_error(priv_hex):
    mock_import = MagicMock()
    mock_import.status_code = 200
    mock_import.json.return_value = {'result': True}

    mock_tx = MagicMock()
    mock_tx.status_code = 200
    mock_tx.json.return_value = {'result': False, 'message': 'insufficient funds'}

    with patch('requests.get', side_effect=[mock_import, mock_tx]):
        with pytest.raises(RuntimeError, match='insufficient funds'):
            transfer.send_webd(priv_hex, 'WEBD$gDest123', 5.0, 0.0001)


# ── Flask route tests ─────────────────────────────────────────────────────────

import json

@pytest.fixture
def client():
    import server
    server.app.config['TESTING'] = True
    with server.app.test_client() as c:
        yield c


def test_derive_address_route_valid(client):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    resp = client.get(f'/api/v1/transfer/derive-address?privkey={priv_hex}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['address'].startswith('WEBD$')


def test_derive_address_route_invalid(client):
    resp = client.get('/api/v1/transfer/derive-address?privkey=bad')
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_transfer_send_route_success(client):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    mock_import = MagicMock()
    mock_import.status_code = 200
    mock_import.json.return_value = {'result': True}
    mock_tx = MagicMock()
    mock_tx.status_code = 200
    mock_tx.json.return_value = {'result': True, 'txId': 'abc123'}
    with patch('requests.get', side_effect=[mock_import, mock_tx]):
        resp = client.post('/api/v1/transfer/send',
            data=json.dumps({'from_privkey': priv_hex, 'to_address': 'WEBD$gDest123', 'amount': 5.0, 'fee': 0.0001}),
            content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['txId'] == 'abc123'


def test_transfer_send_missing_fields(client):
    resp = client.post('/api/v1/transfer/send',
        data=json.dumps({'amount': 5.0}),
        content_type='application/json')
    assert resp.status_code == 400
