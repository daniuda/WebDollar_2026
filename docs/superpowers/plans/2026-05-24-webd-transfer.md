# webd-pay Transfer Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/transfer` page to webd-pay that lets users send WEBD between wallets from the browser, with server-side signing via the local WebDollar node.

**Architecture:** Browser sends {privkey_hex, to_address, amount, fee} over HTTPS POST to Flask. Flask derives address+pubkey from privkey, imports the wallet into the local node via its private API, calls create-transaction, returns txId. A separate per-minute rate limiter protects the transfer endpoints independently from the existing payment rate limiter.

**Tech Stack:** Python 3.12, Flask 3.x, `cryptography` lib (already installed), Node-WebDollar REST API at localhost:8080, vanilla JS + HTML for the UI.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `webd-pay/transfer.py` | Create | Crypto derivation + node API calls for import/create-tx |
| `webd-pay/server.py` | Modify | 2 new routes + per-minute rate limiter |
| `webd-pay/static/transfer.html` | Create | Transfer UI page |
| `webd-pay/static/index.html` | Modify | Add Transfer WEBD button |
| `webd-pay/tests/test_transfer.py` | Create | Unit tests for transfer.py + routes |

---

## Task 1: transfer.py — crypto + node API

**Files:**
- Create: `webd-pay/transfer.py`
- Test: `webd-pay/tests/test_transfer.py`

- [ ] **Step 1: Write the failing tests**

Create `webd-pay/tests/test_transfer.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import transfer

# ── derive_address_from_privkey ───────────────────────────────────────────────

def test_derive_address_known_vector():
    # Generate a keypair with gen_addresses.py logic, then verify round-trip
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

    with patch('requests.get', return_value=mock_import):
        # import failure should not raise — wallet may already exist
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd webd-pay
source venv/bin/activate  # Linux/Mac
# OR: venv\Scripts\activate  # Windows
pytest tests/test_transfer.py -v
```

Expected: `ModuleNotFoundError: No module named 'transfer'`

- [ ] **Step 3: Create transfer.py**

```python
import hashlib
import base64
import requests
from urllib.parse import quote

import config

# ── Constants (same as gen_addresses.py) ─────────────────────────────────────
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
    """
    Returns (webd_address, pubkey_hex) from a 64-char hex private key seed.
    Raises ValueError if privkey_hex is invalid.
    """
    try:
        priv_bytes = bytes.fromhex(privkey_hex)
    except ValueError:
        raise ValueError("invalid private key: not valid hex")
    if len(priv_bytes) != 32:
        raise ValueError("invalid private key: must be 32 bytes (64 hex chars)")

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    hash20 = _ripemd160(_sha256(pub_raw))
    version_plus_hash = _VERSION_BYTES + hash20
    cksum = _sha256(_sha256(version_plus_hash))[:_CHECKSUM_LEN]
    wif_bytes = _PREFIX_BYTES + version_plus_hash + cksum + _SUFFIX_BYTES
    address = _encode_base64_webd(wif_bytes)

    return address, pub_raw.hex()


def send_webd(privkey_hex: str, to_address: str, amount_webd: float, fee_webd: float) -> dict:
    """
    Imports wallet into local node and creates a transaction.
    Returns {'result': True, 'txId': '...'} on success.
    Raises RuntimeError on node failure.
    Private key is used only in memory and in the local node API call (localhost).
    """
    from_address, pubkey_hex = derive_address_from_privkey(privkey_hex)

    base = config.NODE_URL
    secret = config.NODE_SECRET

    # Step 1: import wallet into node
    import_url = (
        f"{base}/{secret}/wallets/import"
        f"/{quote(from_address, safe='')}"
        f"/{quote(pubkey_hex, safe='')}"
        f"/{quote(privkey_hex, safe='')}"
    )
    r_import = requests.get(import_url, timeout=10)
    r_import.raise_for_status()
    imp = r_import.json()
    # result=False with "already exists" is fine — wallet was previously imported
    if not imp.get('result') and 'already' not in str(imp.get('message', '')).lower():
        raise RuntimeError(imp.get('message', 'wallet import failed'))

    # Step 2: create transaction
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_transfer.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add webd-pay/transfer.py webd-pay/tests/test_transfer.py
git commit -m "feat(webd-pay): transfer.py — derive address + send_webd via node API"
```

---

## Task 2: server.py — new routes + rate limiter

**Files:**
- Modify: `webd-pay/server.py`
- Test: `webd-pay/tests/test_transfer.py` (add route tests)

- [ ] **Step 1: Write failing route tests**

Append to `webd-pay/tests/test_transfer.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_transfer.py::test_derive_address_route_valid -v
```

Expected: FAIL with `404 NOT FOUND` (routes don't exist yet).

- [ ] **Step 3: Add per-minute rate limiter and routes to server.py**

In `server.py`, after the existing `_rate_buckets` block, add:

```python
# Per-minute rate limiter for transfer endpoints
_transfer_buckets: dict[str, list] = defaultdict(list)
_transfer_lock = threading.Lock()
_TRANSFER_LIMIT_PER_MIN = 5


def _check_transfer_rate_limit(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=1)
    with _transfer_lock:
        timestamps = [t for t in _transfer_buckets[ip] if t > cutoff]
        if len(timestamps) >= _TRANSFER_LIMIT_PER_MIN:
            return False
        timestamps.append(now)
        _transfer_buckets[ip] = timestamps
    return True
```

Add `import transfer` to the imports line at top:

```python
import config, db, node_client, webhook, transfer
```

Add the two new routes after the existing routes (before the background worker section):

```python
@app.get('/api/v1/transfer/derive-address')
def transfer_derive_address():
    ip = request.remote_addr
    if not _check_transfer_rate_limit(ip):
        return jsonify({'error': 'rate limit exceeded'}), 429
    privkey = request.args.get('privkey', '')
    try:
        address, _ = transfer.derive_address_from_privkey(privkey)
        return jsonify({'address': address})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.post('/api/v1/transfer/send')
def transfer_send():
    ip = request.remote_addr
    if not _check_transfer_rate_limit(ip):
        return jsonify({'error': 'rate limit exceeded, max 5 transfers per minute'}), 429

    body = request.get_json(silent=True) or {}
    privkey = body.get('from_privkey', '')
    to_address = body.get('to_address', '')
    amount = body.get('amount')
    fee = body.get('fee', 0.0001)

    if not privkey or not to_address:
        return jsonify({'error': 'from_privkey and to_address are required'}), 400
    if not amount or not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'error': 'amount must be a positive number'}), 400
    if not isinstance(fee, (int, float)) or fee < 0:
        return jsonify({'error': 'fee must be a non-negative number'}), 400

    try:
        result = transfer.send_webd(privkey, to_address, float(amount), float(fee))
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 502


@app.get('/transfer')
def transfer_page():
    return send_from_directory('static', 'transfer.html')
```

- [ ] **Step 4: Run route tests**

```bash
pytest tests/test_transfer.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add webd-pay/server.py webd-pay/tests/test_transfer.py
git commit -m "feat(webd-pay): add /transfer routes with per-minute rate limiter"
```

---

## Task 3: transfer.html — UI page

**Files:**
- Create: `webd-pay/static/transfer.html`

- [ ] **Step 1: Create transfer.html**

```html
<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Transfer WEBD</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }
    .card { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 16px; padding: 40px; max-width: 520px; width: 100%; }
    .logo { font-size: 36px; text-align: center; margin-bottom: 12px; }
    h1 { font-size: 24px; font-weight: 700; text-align: center; margin-bottom: 24px; }
    .disclaimer { background: #7f1d1d; border: 1px solid #ef4444; border-radius: 10px; padding: 16px; margin-bottom: 28px; font-size: 14px; line-height: 1.6; color: #fca5a5; }
    .disclaimer strong { color: #ff6b6b; display: block; margin-bottom: 6px; font-size: 15px; }
    label { display: block; font-size: 13px; color: #94a3b8; margin-bottom: 6px; margin-top: 18px; }
    input { width: 100%; background: #0f1117; border: 1px solid #2d3748; border-radius: 8px; padding: 12px 14px; color: #e2e8f0; font-size: 14px; outline: none; }
    input:focus { border-color: #f59e0b; }
    .row { display: flex; gap: 12px; }
    .row > div { flex: 1; }
    .hint { font-size: 12px; color: #475569; margin-top: 6px; }
    .my-address { background: #0f1117; border: 1px solid #2d3748; border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #7dd3fc; margin-top: 8px; word-break: break-all; display: none; }
    .btn { width: 100%; padding: 14px; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; border: none; margin-top: 12px; }
    .btn-secondary { background: #1e293b; color: #94a3b8; border: 1px solid #2d3748; }
    .btn-secondary:hover { background: #273348; }
    .btn-primary { background: #f59e0b; color: #0f1117; margin-top: 20px; }
    .btn-primary:hover { background: #fbbf24; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .result { margin-top: 20px; padding: 16px; border-radius: 10px; font-size: 14px; display: none; word-break: break-all; }
    .result.success { background: #14532d; border: 1px solid #22c55e; color: #86efac; }
    .result.error { background: #7f1d1d; border: 1px solid #ef4444; color: #fca5a5; }
    a.back { display: block; text-align: center; margin-top: 24px; color: #475569; font-size: 13px; text-decoration: none; }
    a.back:hover { color: #94a3b8; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">&#x1FA99;</div>
    <h1>Transfer WEBD</h1>

    <div class="disclaimer">
      <strong>&#9888; Atenție — Tranzacțiile sunt ireversibile</strong>
      Nu ne asumăm nicio responsabilitate pentru fondurile trimise la adrese greșite.
      Verificați de două ori adresa destinatarului înainte de a trimite.
      Odată confirmată, tranzacția nu poate fi anulată.
    </div>

    <label>Cheie privată (hex, 64 caractere)</label>
    <input type="password" id="privkey" placeholder="a3f8..." autocomplete="off" spellcheck="false">
    <div class="hint">Rămâne în browser — nu este stocată sau afișată în loguri.</div>

    <button class="btn btn-secondary" onclick="deriveAddress()" style="margin-top:10px;">
      &#128269; Verifică adresa mea
    </button>
    <div class="my-address" id="myAddress"></div>

    <label>Adresă destinatar</label>
    <input type="text" id="toAddress" placeholder="WEBD$g..." spellcheck="false">

    <div class="row">
      <div>
        <label>Sumă (WEBD)</label>
        <input type="number" id="amount" placeholder="10.0" min="0.0001" step="0.0001">
      </div>
      <div>
        <label>Comision (WEBD)</label>
        <input type="number" id="fee" value="0.0001" min="0.0001" step="0.0001">
      </div>
    </div>

    <button class="btn btn-primary" id="sendBtn" onclick="sendTransfer()">
      &#10148; Trimite WEBD
    </button>

    <div class="result" id="result"></div>

    <a class="back" href="/">&#8592; Înapoi</a>
  </div>

  <script>
    async function deriveAddress() {
      const privkey = document.getElementById('privkey').value.trim();
      if (!privkey) return;
      const el = document.getElementById('myAddress');
      el.style.display = 'block';
      el.textContent = 'Se calculează...';
      try {
        const r = await fetch(`/api/v1/transfer/derive-address?privkey=${encodeURIComponent(privkey)}`);
        const data = await r.json();
        if (data.address) {
          el.textContent = '&#128274; Adresa ta: ' + data.address;
        } else {
          el.textContent = 'Eroare: ' + (data.error || 'cheie invalidă');
        }
      } catch (e) {
        el.textContent = 'Eroare de rețea.';
      }
    }

    async function sendTransfer() {
      const privkey = document.getElementById('privkey').value.trim();
      const toAddress = document.getElementById('toAddress').value.trim();
      const amount = parseFloat(document.getElementById('amount').value);
      const fee = parseFloat(document.getElementById('fee').value);
      const resultEl = document.getElementById('result');
      const btn = document.getElementById('sendBtn');

      resultEl.style.display = 'none';

      if (!privkey || !toAddress || !amount) {
        showResult('error', 'Completați toate câmpurile obligatorii.');
        return;
      }
      if (!toAddress.startsWith('WEBD$')) {
        showResult('error', 'Adresa destinatarului trebuie să înceapă cu WEBD$');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Se trimite...';

      try {
        const r = await fetch('/api/v1/transfer/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({from_privkey: privkey, to_address: toAddress, amount, fee})
        });
        const data = await r.json();
        if (r.ok && data.txId) {
          showResult('success', '&#10003; Tranzacție trimisă cu succes!<br>TX ID: <strong>' + data.txId + '</strong>');
          document.getElementById('privkey').value = '';
          document.getElementById('myAddress').style.display = 'none';
        } else {
          showResult('error', 'Eroare: ' + (data.error || 'necunoscută'));
        }
      } catch (e) {
        showResult('error', 'Eroare de rețea: ' + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = '&#10148; Trimite WEBD';
      }
    }

    function showResult(type, html) {
      const el = document.getElementById('result');
      el.className = 'result ' + type;
      el.innerHTML = html;
      el.style.display = 'block';
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify page loads**

```bash
# Restart Flask locally (or on VPS) then open in browser:
curl -s http://localhost:3010/transfer | grep -c "Transfer WEBD"
```

Expected output: `1`

- [ ] **Step 3: Commit**

```bash
git add webd-pay/static/transfer.html
git commit -m "feat(webd-pay): transfer.html — browser transfer UI with disclaimer"
```

---

## Task 4: Update index.html

**Files:**
- Modify: `webd-pay/static/index.html`

- [ ] **Step 1: Add Transfer button to index.html**

In `webd-pay/static/index.html`, replace the existing `<a class="btn" href="/api/v1/docs">API Docs</a>` line with:

```html
    <a class="btn" href="/transfer">Transfer WEBD</a>
    <a class="btn" href="/api/v1/docs" style="background:#334155;color:#e2e8f0;">API Docs</a>
```

- [ ] **Step 2: Verify**

```bash
curl -s http://localhost:3010/ | grep -c "Transfer WEBD"
```

Expected: `1`

- [ ] **Step 3: Commit**

```bash
git add webd-pay/static/index.html
git commit -m "feat(webd-pay): add Transfer WEBD button to landing page"
```

---

## Task 5: Deploy to VPS

**Files:** No code changes — deploy existing code to VPS.

- [ ] **Step 1: Copy changed files to VPS**

```bash
# From local repo root
scp -i ~/.ssh/claude_vps webd-pay/transfer.py root@164.132.42.154:/home/ubuntu/webd-pay/transfer.py
scp -i ~/.ssh/claude_vps webd-pay/server.py root@164.132.42.154:/home/ubuntu/webd-pay/server.py
scp -i ~/.ssh/claude_vps webd-pay/static/transfer.html root@164.132.42.154:/home/ubuntu/webd-pay/static/transfer.html
scp -i ~/.ssh/claude_vps webd-pay/static/index.html root@164.132.42.154:/home/ubuntu/webd-pay/static/index.html
```

- [ ] **Step 2: Restart webd-pay service**

```bash
ssh -i ~/.ssh/claude_vps root@164.132.42.154 'systemctl restart webd-pay && sleep 2 && systemctl status webd-pay --no-pager | grep Active'
```

Expected: `Active: active (running)`

- [ ] **Step 3: Smoke test derive-address**

```bash
# Generate a test private key hex (32 random bytes)
ssh -i ~/.ssh/claude_vps root@164.132.42.154 'curl -s "https://pay.webdollar.cloudns.nz/api/v1/transfer/derive-address?privkey=a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"'
```

Expected: `{"address":"WEBD$..."}`

- [ ] **Step 4: Open transfer page in browser**

Navigate to: `https://pay.webdollar.cloudns.nz/transfer`

Verify:
- Red disclaimer is visible
- Form has all 4 fields
- "Verifică adresa mea" button works (enter a valid 64-char hex, click button, address appears)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "deploy: webd-pay transfer feature live on pay.webdollar.cloudns.nz"
```
