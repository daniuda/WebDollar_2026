# webd-pay Transfer Feature — Design Spec (v1)

Date: 2026-05-24  
Branch: feat/webd-pay  
Status: Approved for implementation

## Overview

Add a browser-based WEBD transfer page to `pay.webdollar.cloudns.nz/transfer`. Users can send WEBD between any two wallets directly in the browser. The private key is transmitted over HTTPS to the Flask server, which uses the local node's private API to import the wallet temporarily and create the transaction. The key is never logged or stored.

A v2 (true client-side signing, key never leaves browser) is planned for a future iteration.

## Pages & Navigation

- `/` — landing page gains two new buttons: **Transfer WEBD** (`/transfer`) and **API Docs** (`/api/v1/docs`)
- `/transfer` — new transfer page (static HTML served by Flask)
- `/api/v1/docs` — unchanged

## Transfer Page (`/transfer`)

### Layout

1. **Disclaimer banner** (red/orange, prominent at top):  
   *"Nu ne asumăm nicio responsabilitate pentru tranzacțiile trimise la adrese greșite. Verificați de două ori adresa destinatarului. Tranzacțiile blockchain sunt ireversibile."*

2. **Form fields:**
   - Cheie privată (hex, 64 chars) — `type="password"`, autocomplete off
   - Adresă destinatar — text input with basic format validation (`WEBD$...`)
   - Sumă WEBD — number input, min 0.0001
   - Comision (fee) — pre-filled default 0.0001, editable

3. **"Verifică adresa mea"** button:
   - Calls `GET /api/v1/transfer/derive-address?privkey=<hex>` 
   - Displays the derived sender address for visual confirmation before sending

4. **"Trimite WEBD"** button:
   - POSTs `{from_privkey, to_address, amount, fee}` to `POST /api/v1/transfer/send`
   - Shows spinner while waiting
   - On success: shows tx ID with link to status check
   - On error: shows error message

## Backend

### New Flask endpoints

#### `GET /api/v1/transfer/derive-address`
- Params: `?privkey=<hex64>`
- Derives public key and WEBD address from private key using same algorithm as `gen_addresses.py`
- Returns: `{"address": "WEBD$..."}`
- Rate limit: 10/minute per IP (separate from payment rate limit)

#### `POST /api/v1/transfer/send`
- Body: `{"from_privkey": "<hex>", "to_address": "WEBD$...", "amount": 1.0, "fee": 0.0001}`
- Steps:
  1. Validate inputs (privkey format, to_address format, amount > 0, fee > 0)
  2. Derive address and public key from privkey
  3. Call node: `GET SECRET/wallets/import/{address}/{publicKey}/{privateKey}`
  4. Call node: `GET SECRET/wallets/create-transaction/{from}/{to}/{amount}/{fee}`
  5. Return `{"txId": "...", "result": true}`
- Rate limit: 5/minute per IP
- Private key: never logged, not stored after request completes

### New module: `transfer.py`
- `derive_address(privkey_hex) -> (address, pubkey_hex)` — reuses crypto logic from `gen_addresses.py`
- `send_transaction(from_privkey_hex, to_address, amount_webd, fee_webd) -> dict` — orchestrates import + create-transaction node calls

## Security Notes

- Private key travels over HTTPS (TLS 1.2+, Let's Encrypt cert) — encrypted in transit
- Flask logging: request bodies not logged (default Flask behavior)
- Private key is not stored in DB, not written to disk, not included in any response
- The imported wallet persists in the node's wallet file — acceptable for v1 (small set of one-time-use addresses)
- v2 will eliminate server-side key handling entirely

## Rate Limits

| Endpoint | Limit |
|---|---|
| `/api/v1/transfer/derive-address` | 10/minute per IP |
| `/api/v1/transfer/send` | 5/minute per IP |
| Existing `/api/v1/payment/*` | 10/hour per IP (unchanged) |

## Files Changed

- `webd-pay/transfer.py` — new module
- `webd-pay/server.py` — 2 new routes + new rate limiter
- `webd-pay/static/transfer.html` — new page
- `webd-pay/static/index.html` — add navigation buttons
