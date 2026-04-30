"""
WebDollar transaction builder — Python port of txBuilder.ts
Requires: pip3 install cryptography
"""
import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

WEBD_UNITS = 10_000
MIN_FEE_WEBD = 10
MIN_AMOUNT_WEBD = 10
TX_VERSION = 0x02
WEBD_TOKEN_ID = bytes([0x01])
WIF_PREFIX = bytes([0x58, 0x40, 0x43, 0xfe])


# ── serialization helpers ──────────────────────────────────────────────────────

def u1(v: int) -> bytes:
    return bytes([v & 0xff])

def u2(v: int) -> bytes:
    return bytes([(v >> 8) & 0xff, v & 0xff])

def u3(v: int) -> bytes:
    return bytes([(v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff])

def u7le(v: int) -> bytes:
    out = bytearray(7)
    n = int(v)
    for i in range(7):
        out[i] = n & 0xff
        n >>= 8
    return bytes(out)

def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def bytes_to_hex(b: bytes) -> str:
    return b.hex()

def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


# ── address helpers ────────────────────────────────────────────────────────────

def decode_webd_address(wif: str) -> bytes:
    """Decode WEBD$... address to 20-byte unencoded form."""
    normalized = wif.strip().replace('$', '/').replace('#', 'O').replace('@', 'l')
    # base64 padding
    pad = len(normalized) % 4
    if pad:
        normalized += '=' * (4 - pad)
    raw = base64.b64decode(normalized)
    if len(raw) != 30:
        raise ValueError(f'Adresă invalidă (lungime {len(raw)}, expected 30)')
    if raw[:4] != WIF_PREFIX:
        raise ValueError('Adresă invalidă (prefix)')
    if raw[29] != 0xff:
        raise ValueError('Adresă invalidă (suffix)')
    return raw[5:25]  # 20 bytes


# ── crypto helpers ─────────────────────────────────────────────────────────────

def _load_private_key(seed_hex: str) -> Ed25519PrivateKey:
    seed = hex_to_bytes(seed_hex)
    # Legacy .webd format: [0x80] + seed(32) + pubkey(32) + checksum(4) = 69 bytes
    if len(seed) == 69 and seed[0] == 0x80:
        seed = seed[1:33]
    if len(seed) == 138 // 2:  # 69 hex bytes passed as hex string
        seed_bytes = seed
        if seed_bytes[0] == 0x80:
            seed = seed_bytes[1:33]
    if len(seed) != 32:
        raise ValueError(f'Seed cheie privată trebuie 32 bytes (primit {len(seed)})')
    return Ed25519PrivateKey.from_private_bytes(seed)

def sign_ed25519(seed_hex: str, message: bytes) -> bytes:
    key = _load_private_key(seed_hex)
    return key.sign(message)

def get_public_key_from_seed(seed_hex: str) -> bytes:
    key = _load_private_key(seed_hex)
    pub = key.public_key()
    # Export raw 32-byte public key
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


# ── main builder ───────────────────────────────────────────────────────────────

def build_signed_tx(
    from_address: str,
    private_key_hex: str,
    public_key_hex: str,
    to_address: str,
    amount_webd: float,
    fee_webd: float = MIN_FEE_WEBD,
    nonce: int = None,
    time_lock: int = 0,
) -> dict:
    """
    Build and sign a WebDollar transaction.
    Returns dict with: tx_id, serialized_hex, tx_json
    """
    if nonce is None:
        nonce = int.from_bytes(os.urandom(2), 'big')

    if amount_webd < MIN_AMOUNT_WEBD:
        raise ValueError(f'Suma minimă: {MIN_AMOUNT_WEBD} WEBD')
    if fee_webd < MIN_FEE_WEBD:
        raise ValueError(f'Fee minim: {MIN_FEE_WEBD} WEBD')

    amount_units = round(amount_webd * WEBD_UNITS)
    fee_units = round(fee_webd * WEBD_UNITS)
    from_amount_units = amount_units + fee_units

    from_unencoded = decode_webd_address(from_address)
    to_unencoded = decode_webd_address(to_address)
    from_public_key = hex_to_bytes(public_key_hex)

    if len(from_unencoded) != 20:
        raise ValueError('Adresă sursă invalidă')
    if len(to_unencoded) != 20:
        raise ValueError('Adresă destinatar invalidă')
    if len(from_public_key) != 32:
        raise ValueError('Cheie publică invalidă (trebuie 32 bytes)')

    # Signing payload — identic cu txBuilder.ts
    signing_payload = (
        u1(TX_VERSION) +
        u2(nonce) +
        u3(time_lock) +
        from_unencoded +
        from_public_key +
        from_public_key +       # repeated — protocol WebDollar
        u1(1) +
        u7le(from_amount_units) +
        u1(1) + to_unencoded + u7le(amount_units)
    )

    signature = sign_ed25519(private_key_hex, signing_payload)
    if len(signature) != 64:
        raise ValueError('Semnătură Ed25519 invalidă')

    # Tranzacție serializată
    serialized = (
        u1(TX_VERSION) +
        u2(nonce) +
        u3(time_lock) +
        # from section
        u1(1) +
        from_public_key +
        signature +
        u7le(from_amount_units) +
        u1(len(WEBD_TOKEN_ID)) +
        WEBD_TOKEN_ID +
        # to section
        u1(1) +
        to_unencoded +
        u7le(amount_units)
    )

    tx_id = bytes_to_hex(double_sha256(serialized))

    return {
        'tx_id': tx_id,
        'serialized_hex': bytes_to_hex(serialized),
        'tx_json': {
            'version': TX_VERSION,
            'nonce': nonce,
            'time_lock': time_lock,
            'from': [{
                'unencoded_address': bytes_to_hex(from_unencoded),
                'public_key': public_key_hex,
                'amount': from_amount_units,
                'signature': bytes_to_hex(signature),
            }],
            'to': [{
                'unencoded_address': bytes_to_hex(to_unencoded),
                'amount': amount_units,
            }],
            'fee': fee_units,
        },
    }


# ── test self-check ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('tx_builder.py OK — import test passed')
    print(f'  u7le(10000) = {u7le(10000).hex()}')
    print(f'  u7le(0)     = {u7le(0).hex()}')
