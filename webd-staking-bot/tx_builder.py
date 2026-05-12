"""
WebDollar transaction builder — Python port of txBuilder.ts
Requires: pip3 install cryptography
"""
import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

WEBD_UNITS = 10_000
MIN_FEE_WEBD = 10
MIN_AMOUNT_WEBD = 10
PAYOUT_FEE_PCT = 0.5   # procent din total_out pentru tranzacții multi-output
WEBD_TOKEN_ID = bytes([0x01])
WIF_PREFIX = bytes([0x58, 0x40, 0x43, 0xfe])

# Hard-fork heights — aceleași valori ca în Node-WebDollar/src/consts/const_global.js
HARD_FORK_BUG_2_BYTES   = 46_950   # < → version 0x00 (nonce 1 byte)
HARD_FORK_OPTIMIZATION  = 153_065  # >= → version 0x02

def compute_version(time_lock: int) -> int:
    if time_lock < HARD_FORK_BUG_2_BYTES:
        return 0x00
    elif time_lock < HARD_FORK_OPTIMIZATION:
        return 0x01
    else:
        return 0x02


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
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)

def ripemd160_sha256(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data)) — adresă WebDollar din cheie publică (identic cu Node-WebDollar)."""
    sha = hashlib.sha256(data).digest()
    try:
        h = hashlib.new('ripemd160')
        h.update(sha)
        return h.digest()
    except ValueError:
        # OpenSSL >=3 poate dezactiva RIPEMD-160 — fallback: importă din cryptography
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        d = hashes.Hash(hashes.RIPEMD160(), backend=default_backend())
        d.update(sha)
        return d.finalize()


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
    time_lock TREBUIE să fie currentBlockHeight-1 (fetch din /top), nu 0!
    Version este derivat automat din time_lock (ca în Node-WebDollar const_global.js).
    Returns dict with: tx_id, serialized_hex, tx_json
    """
    if nonce is None:
        nonce = int.from_bytes(os.urandom(2), 'big') % 0x10000

    if amount_webd < MIN_AMOUNT_WEBD:
        raise ValueError(f'Suma minimă: {MIN_AMOUNT_WEBD} WEBD')
    if fee_webd < MIN_FEE_WEBD:
        raise ValueError(f'Fee minim: {MIN_FEE_WEBD} WEBD')

    version = compute_version(time_lock)
    amount_units = round(amount_webd * WEBD_UNITS)
    fee_units = round(fee_webd * WEBD_UNITS)
    from_amount_units = amount_units + fee_units

    from_unencoded = decode_webd_address(from_address)
    to_unencoded = decode_webd_address(to_address)

    # Derivă cheia publică din cheia privată — NU folosi public_key_hex direct
    # (dacă e diferit de cheia reală, semnătura nu va verifica)
    from_public_key = get_public_key_from_seed(private_key_hex)
    if len(from_public_key) != 32:
        raise ValueError('Cheie publică derivată invalidă')

    # Verifică consistența: adresa WIF trebuie să corespundă cu cheia publică derivată
    try:
        derived_unencoded = ripemd160_sha256(from_public_key)
        if derived_unencoded != from_unencoded:
            import sys as _sys
            print(
                f'[TX_BUILDER WARNING] Adresă incompatibilă cu cheia privată!\n'
                f'  from_address→unencoded: {from_unencoded.hex()}\n'
                f'  RIPEMD160(SHA256(privKey→pubKey)): {derived_unencoded.hex()}\n'
                f'  Semnătura NU va verifica pe nod! Verifică config: address ↔ private_key_hex.',
                file=_sys.stderr, flush=True
            )
            raise ValueError(
                f'Adresă incompatibilă cu cheia privată — from_address nu corespunde private_key_hex.\n'
                f'  WIF unencoded:  {from_unencoded.hex()}\n'
                f'  Derived:        {derived_unencoded.hex()}'
            )
    except ValueError:
        raise
    except Exception as _e:
        print(f'[TX_BUILDER] Nu pot verifica adresa: {_e}', flush=True)

    if len(from_unencoded) != 20:
        raise ValueError('Adresă sursă invalidă')
    if len(to_unencoded) != 20:
        raise ValueError('Adresă destinatar invalidă')

    nonce_bytes = u2(nonce) if version >= 0x01 else u1(nonce % 0x100)

    # Signing payload — identic cu txBuilder.ts / serializeForSigning
    signing_payload = (
        u1(version) +
        nonce_bytes +
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
        u1(version) +
        nonce_bytes +
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
            'version': version,
            'nonce': nonce,
            'time_lock': time_lock,
            'from': [{
                'unencoded_address': bytes_to_hex(from_unencoded),
                'public_key': bytes_to_hex(from_public_key),
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


# ── multi-output builder ───────────────────────────────────────────────────────

def build_signed_tx_multi(
    from_address: str,
    private_key_hex: str,
    public_key_hex: str,
    outputs: list,          # [{'address': 'WEBD$...', 'amount_webd': float}, ...]
    fee_pct: float = PAYOUT_FEE_PCT,
    nonce: int = None,
    time_lock: int = 0,
) -> dict:
    """
    Tranzacție cu N destinatari — o singură taxă pentru toți.
    fee = max(MIN_FEE_WEBD, fee_pct% din total_out).
    Reduce costul per staker la fee_pct% indiferent de numărul de destinatari.
    """
    if not outputs:
        raise ValueError('Lista de destinatari e goală')
    if nonce is None:
        nonce = int.from_bytes(os.urandom(2), 'big') % 0x10000

    decoded = []
    total_out = 0.0
    for o in outputs:
        addr_bytes   = decode_webd_address(o['address'])
        amount_webd  = float(o['amount_webd'])
        if amount_webd <= 0:
            raise ValueError(f"Sumă invalidă pentru {o['address']}: {amount_webd}")
        amount_units = round(amount_webd * WEBD_UNITS)
        decoded.append((addr_bytes, amount_units, o['address'], amount_webd))
        total_out += amount_webd

    fee_webd          = max(MIN_FEE_WEBD, round(total_out * fee_pct / 100.0, 4))
    from_amount_units = round((total_out + fee_webd) * WEBD_UNITS)
    from_unencoded    = decode_webd_address(from_address)
    from_public_key   = get_public_key_from_seed(private_key_hex)

    if len(from_public_key) != 32:
        raise ValueError('Cheie publică derivată invalidă')

    try:
        derived_unencoded = ripemd160_sha256(from_public_key)
        if derived_unencoded != from_unencoded:
            import sys as _sys
            print(
                f'[TX_BUILDER WARNING] Adresă incompatibilă cu cheia privată (multi)!\n'
                f'  from_address→unencoded: {from_unencoded.hex()}\n'
                f'  RIPEMD160(SHA256(privKey→pubKey)): {derived_unencoded.hex()}',
                file=_sys.stderr, flush=True
            )
            raise ValueError(
                f'Adresă incompatibilă cu cheia privată — from_address nu corespunde private_key_hex.\n'
                f'  WIF unencoded:  {from_unencoded.hex()}\n'
                f'  Derived:        {derived_unencoded.hex()}'
            )
    except ValueError:
        raise
    except Exception as _e:
        print(f'[TX_BUILDER] Nu pot verifica adresa (multi): {_e}', flush=True)

    version     = compute_version(time_lock)
    nonce_bytes = u2(nonce) if version >= 0x01 else u1(nonce % 0x100)

    # to section: u1(N) + [addr(20) + amount_7le(7)] × N
    n          = len(decoded)
    to_section = u1(n)
    for addr_bytes, amount_units, _, _ in decoded:
        to_section += addr_bytes + u7le(amount_units)

    signing_payload = (
        u1(version) +
        nonce_bytes +
        u3(time_lock) +
        from_unencoded +
        from_public_key +
        from_public_key +
        u1(1) +
        u7le(from_amount_units) +
        to_section
    )

    signature = sign_ed25519(private_key_hex, signing_payload)
    if len(signature) != 64:
        raise ValueError('Semnătură Ed25519 invalidă')

    serialized = (
        u1(version) +
        nonce_bytes +
        u3(time_lock) +
        u1(1) +
        from_public_key +
        signature +
        u7le(from_amount_units) +
        u1(len(WEBD_TOKEN_ID)) +
        WEBD_TOKEN_ID +
        to_section
    )

    tx_id = bytes_to_hex(double_sha256(serialized))
    return {
        'tx_id': tx_id,
        'serialized_hex': bytes_to_hex(serialized),
        'fee_webd': fee_webd,
        'total_out_webd': round(total_out, 6),
        'n_outputs': n,
        'outputs': [{'address': addr, 'amount_webd': amt} for _, _, addr, amt in decoded],
    }


# ── signature verification ────────────────────────────────────────────────────

def verify_signature(pubkey_hex: str, message: bytes, sig_hex: str) -> bool:
    """Verify an Ed25519 signature. Returns True if valid."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(hex_to_bytes(pubkey_hex))
        pub.verify(hex_to_bytes(sig_hex), message)
        return True
    except Exception:
        return False

def get_public_key_bytes_from_hex(pubkey_hex: str) -> bytes:
    return hex_to_bytes(pubkey_hex)


# ── test self-check ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('tx_builder.py OK — import test passed')
    print(f'  u7le(10000) = {u7le(10000).hex()}')
    print(f'  u7le(0)     = {u7le(0).hex()}')
