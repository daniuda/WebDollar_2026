import hashlib
import base64
import requests
from urllib.parse import quote

import config

_PREFIX_BYTES  = bytes.fromhex("584043fe")
_VERSION_BYTES = bytes.fromhex("00")
_SUFFIX_BYTES  = bytes.fromhex("FF")
_CHECKSUM_LEN  = 4


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _ripemd160(data: bytes) -> bytes:
    return hashlib.new("ripemd160", data).digest()


def _encode_base64_webd(data: bytes) -> str:
    raw = base64.b64encode(data).decode("ascii")
    return raw.replace("O", "#").replace("l", "@").replace("/", "$")


def derive_address_from_privkey(privkey_hex: str) -> tuple[str, str]:
    """Returns (webd_address, pubkey_hex). Raises ValueError if privkey_hex is invalid."""
    try:
        priv_bytes = bytes.fromhex(privkey_hex)
    except ValueError:
        raise ValueError("invalid private key: not valid hex")
    if len(priv_bytes) != 32:
        raise ValueError("invalid private key: must be 32 bytes (64 hex chars)")

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    hash20 = _ripemd160(_sha256(pub_raw))
    version_plus_hash = _VERSION_BYTES + hash20
    cksum = _sha256(_sha256(version_plus_hash))[:_CHECKSUM_LEN]
    wif_bytes = _PREFIX_BYTES + version_plus_hash + cksum + _SUFFIX_BYTES
    address = _encode_base64_webd(wif_bytes)

    return address, pub_raw.hex()


def send_webd(privkey_hex: str, to_address: str, amount_webd: float, fee_webd: float) -> dict:
    """Imports wallet into local node and creates a transaction. Returns {'result': True, 'txId': '...'}."""
    from_address, pubkey_hex = derive_address_from_privkey(privkey_hex)

    base = config.NODE_URL
    secret = config.NODE_SECRET

    import_url = (
        f"{base}/{secret}/wallets/import"
        f"/{quote(from_address, safe='')}"
        f"/{quote(pubkey_hex, safe='')}"
        f"/{quote(privkey_hex, safe='')}"
    )
    r_import = requests.get(import_url, timeout=10)
    r_import.raise_for_status()
    imp = r_import.json()
    if not imp.get('result') and 'already' not in str(imp.get('message', '')).lower():
        raise RuntimeError(imp.get('message', 'wallet import failed'))

    tx_url = (
        f"{base}/{secret}/wallets/create-transaction"
        f"/{quote(from_address, safe='')}"
        f"/{quote(to_address, safe='')}"
        f"/{amount_webd}"
        f"/{fee_webd}"
    )
    r_tx = requests.get(tx_url, timeout=15)
    r_tx.raise_for_status()
    tx = r_tx.json()

    if not tx.get('result'):
        raise RuntimeError(tx.get('message', 'transaction failed'))

    return {'result': True, 'txId': tx.get('txId', '')}
