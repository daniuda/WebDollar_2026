import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import transfer

# ── derive_address_from_privkey ───────────────────────────────────────────────

def test_derive_address_known_vector():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    address, pubkey_hex = transfer.derive_address_from_privkey(priv_hex)

    assert address.startswith('WEBD$')
    assert len(address) > 20
    assert pubkey_hex == pub_raw.hex()
    assert len(pubkey_hex) == 64  # 32 bytes hex


def test_derive_address_invalid_hex():
    with pytest.raises(ValueError, match='invalid'):
        transfer.derive_address_from_privkey('not-hex')


def test_derive_address_wrong_length():
    with pytest.raises(ValueError, match='invalid'):
        transfer.derive_address_from_privkey('abcd')  # too short


# ── send_webd ────────────────────────────────────────────────────────────────

def test_send_webd_success():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()

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


def test_send_webd_import_fails():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()

    mock_import = MagicMock()
    mock_import.status_code = 200
    mock_import.json.return_value = {'result': False, 'message': 'already exists'}

    mock_tx = MagicMock()
    mock_tx.status_code = 200
    mock_tx.json.return_value = {'result': True, 'txId': 'aabbccdd'}

    with patch('requests.get', side_effect=[mock_import, mock_tx]):
        result = transfer.send_webd(priv_hex, 'WEBD$gDest123', 5.0, 0.0001)
    assert result['result'] is True


def test_send_webd_node_error():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()

    mock_import = MagicMock()
    mock_import.status_code = 200
    mock_import.json.return_value = {'result': True}

    mock_tx = MagicMock()
    mock_tx.status_code = 200
    mock_tx.json.return_value = {'result': False, 'message': 'insufficient funds'}

    with patch('requests.get', side_effect=[mock_import, mock_tx]):
        with pytest.raises(RuntimeError, match='insufficient funds'):
            transfer.send_webd(priv_hex, 'WEBD$gDest123', 5.0, 0.0001)
