import hashlib
import base64
import math
import requests
from urllib.parse import quote
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import config

_PREFIX_BYTES  = bytes.fromhex("584043fe")
_VERSION_BYTES = bytes.fromhex("00")
_SUFFIX_BYTES  = bytes.fromhex("FF")
_CHECKSUM_LEN  = 4
_PRIVKEY_WIF_VERSION = bytes.fromhex("80")


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _ripemd160(data: bytes) -> bytes:
    return hashlib.new("ripemd160", data).digest()


def _encode_base64_webd(data: bytes) -> str:
    raw = base64.b64encode(data).decode("ascii")
    return raw.replace("O", "#").replace("l", "@").replace("/", "$")


def _seed_to_wif_hex(seed_bytes: bytes, pubkey_bytes: bytes) -> str:
    """Return 69-byte WIF hex: 0x80 + seed(32B) + pubkey(32B) + checksum(4B)."""
    body = _PRIVKEY_WIF_VERSION + seed_bytes + pubkey_bytes
    checksum = _sha256(_sha256(body))[:_CHECKSUM_LEN]
    return (body + checksum).hex()


def derive_address_from_privkey(privkey_hex: str) -> tuple[str, str]:
    """Returns (webd_address, pubkey_hex). Raises ValueError if privkey_hex is invalid."""
    try:
        priv_bytes = bytes.fromhex(privkey_hex)
    except ValueError:
        raise ValueError("invalid private key: not valid hex")
    if len(priv_bytes) != 32:
        raise ValueError("invalid private key: must be 32 bytes (64 hex chars)")

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
    if not (math.isfinite(amount_webd) and amount_webd > 0):
        raise ValueError("amount_webd must be a finite positive number")
    if not (math.isfinite(fee_webd) and fee_webd >= 0):
        raise ValueError("fee_webd must be a finite non-negative number")

    # Node expects WIF format (0x80 + seed + pubkey + checksum = 69B) so validatePrivateKeyWIF passes
    wif_hex = _seed_to_wif_hex(bytes.fromhex(privkey_hex), bytes.fromhex(pubkey_hex))

    base = config.NODE_URL
    secret = config.NODE_SECRET

    # Check balance before importing — "Nonce is not right" from node means address not in chain
    try:
        r_bal = requests.get(f"{base}/address/balance/{quote(from_address, safe='')}", timeout=10)
        bal = r_bal.json().get('balance', 0) if r_bal.ok else 0
    except Exception:
        bal = None
    if bal is not None:
        needed = amount_webd + fee_webd
        if bal < needed:
            raise ValueError(f"sold insuficient: {bal:.4f} WEBD disponibil, necesar {needed:.4f} WEBD (suma + comision)")

    import_url = (
        f"{base}/{secret}/wallets/import"
        f"/{quote(from_address, safe='')}"
        f"/{quote(pubkey_hex, safe='')}"
        f"/{quote(wif_hex, safe='')}"
    )
    # SECURITY: import_url contains the private key — never log this URL
    try:
        r_import = requests.get(import_url, timeout=10)
        r_import.raise_for_status()
    except Exception:
        raise RuntimeError("wallet import request failed") from None
    imp = r_import.json()
    # Node returns {'result': False, 'message': 'wallet already exists'} for duplicates
    if not imp.get('result') and 'already' not in str(imp.get('message', '')).lower():
        raise RuntimeError(imp.get('message', 'wallet import failed'))

    tx_url = (
        f"{base}/{secret}/wallets/create-transaction"
        f"/{quote(from_address, safe='')}"
        f"/{quote(to_address, safe='')}"
        f"/{amount_webd}"
        f"/{fee_webd}"
    )
    try:
        r_tx = requests.get(tx_url, timeout=15)
        r_tx.raise_for_status()
    except Exception:
        raise RuntimeError("create-transaction request failed") from None
    tx = r_tx.json()

    if not tx.get('result'):
        msg = tx.get('message', 'transaction failed')
        reason = tx.get('reason')
        if reason and reason != msg:
            msg = f"{msg}: {reason}"
        raise RuntimeError(msg)

    return {'result': True, 'txId': tx.get('txId', '')}
