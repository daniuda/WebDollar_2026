# webd-pay — Payment Server Design

**Date:** 2026-05-18  
**Status:** Approved, ready for implementation

---

## Overview

A public payment server for WebDollar. No registration required — anyone can create a payment session via API. Supports merchant webhooks, status polling, and direct browser payment via wdexperience embed.

---

## Section 1 — Infrastructure

- **VPS:** Contabo VPS S (~5.5€/month, 8GB RAM, 50GB SSD) — no ID copy required
- **Domain:** `pay.webdollar.cloudns.nz` — free, on existing CloudNS account
- **SSL:** Let's Encrypt via Certbot, auto-renew
- **Stack:** Python Flask + SQLite, nginx reverse proxy
- **WebDollar node:** Node-WebDollar legacy full node on `localhost:8080`, read-only (no mining, no staking)
- **nginx routing:**
  - `443 /api/` → `127.0.0.1:3010/api/`
  - `443 /p/` and `/` → static HTML served by Flask

---

## Section 2 — API + Payment Flow

### Create payment session

```
POST /api/v1/payment/create
Content-Type: application/json

{
  "amount": 100.5,
  "merchant_id": "shop123",       // optional, free-form string
  "webhook_url": "https://...",   // optional
  "redirect_url": "https://...",  // optional, shown after paid
  "metadata": { ... }             // optional, any JSON
}

Response 200:
{
  "payment_id": "uuid-v4",
  "pay_to": "WEBD$...",
  "amount_webd": 100.5,
  "expires_at": "2026-05-18T04:00:00Z",
  "payment_url": "https://pay.webdollar.cloudns.nz/p/uuid-v4",
  "secret": "hex64"   // returned ONCE — merchant uses to verify webhook signature
}
```

### Poll status

```
GET /api/v1/payment/:id/status

Response 200:
{
  "payment_id": "uuid",
  "status": "pending" | "paid" | "expired" | "overpaid",
  "amount_webd": 100.5,
  "paid_amount_webd": 100.5,
  "confirmations": 1,
  "tx_hash": "abc123..."
}
```

### SQLite schema

```sql
CREATE TABLE payments (
  id             TEXT PRIMARY KEY,
  merchant_id    TEXT,
  amount_webd    REAL NOT NULL,
  pay_to_address TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'pending',
  webhook_url    TEXT,
  redirect_url   TEXT,
  metadata       TEXT,
  secret         TEXT NOT NULL,
  tx_hash        TEXT,
  paid_amount    REAL,
  confirmations  INTEGER DEFAULT 0,
  created_at     TEXT NOT NULL,
  expires_at     TEXT NOT NULL,
  webhook_status TEXT DEFAULT 'pending'
);
```

### Background worker

- `APScheduler` running every 15 seconds
- Queries all `pending` sessions not yet expired
- For each: `GET http://localhost:8080/SECRET_SECRET_SECRET_LONG_SECRET_123456/address/balance/:addr`
  - Response balance is in raw sub-units (1 WEBD = 10,000 sub-units) — divide by 10,000 before comparing
- If balance >= amount_webd → mark `paid`, trigger webhook delivery
- Sessions past `expires_at` with status `pending` → mark `expired`
- Rate limiting: max 10 session creations per IP per hour (in-memory counter)

---

## Section 3 — Frontend (Public Payment Page)

Single-page at `https://pay.webdollar.cloudns.nz/p/{payment_id}`.  
Plain HTML + vanilla JS + CSS — no framework, no build step.

### Layout

```
┌─────────────────────────────────────┐
│  🪙 WebDollar Payment               │
├─────────────────────────────────────┤
│  Pay:     100.5 WEBD                │
│  To:      WEBD$gXXX...              │
│  Expires: 24:37                     │
│                                     │
│  ┌─────────────────────────────┐    │
│  │   [QR code — address]       │    │
│  └─────────────────────────────┘    │
│                                     │
│  [ Pay from browser ]               │
│                                     │
│  Status: ⏳ Waiting for payment...  │
└─────────────────────────────────────┘
```

### Behaviour

- **Auto-polling** `/api/v1/payment/:id/status` every 10 seconds — no manual refresh needed
- On `paid`: show ✅ success message; if `redirect_url` set, redirect after 3 seconds
- **"Pay from browser"** button opens wdexperience embed with `pay-to` and `pay-amount` pre-filled
- QR code generated client-side (qrcode.js CDN, ~10KB)
- Countdown timer updates every second until `expires_at`
- On `expired`: show ❌ expired message, stop polling
- Fully responsive

### Extra pages

- `/` — landing: "WebDollar Payment Server" + link to API docs
- `/api/v1/docs` — inline API documentation (static HTML)

---

## Section 4 — Webhook Delivery

### Payload

```json
POST {webhook_url}
Content-Type: application/json
X-WEBD-Signature: sha256hex(secret + raw_body)

{
  "event": "payment.confirmed",
  "payment_id": "uuid",
  "merchant_id": "shop123",
  "amount_webd": 100.5,
  "paid_amount_webd": 100.5,
  "tx_hash": "abc123...",
  "confirmations": 1,
  "metadata": { ... },
  "timestamp": "2026-05-18T03:00:00Z"
}
```

### Retry schedule

| Attempt | Delay after previous |
|---------|---------------------|
| 1       | immediate           |
| 2       | 30 seconds          |
| 3       | 2 minutes           |
| 4       | 10 minutes          |
| 5       | 1 hour              |

- Timeout per attempt: 10 seconds
- Success: HTTP 2xx response
- After 5 failed attempts: `webhook_status = 'failed'`; payment remains `paid`
- Merchant can always use polling as fallback

---

## Section 5 — Deployment

### VPS setup order

1. Provision Contabo VPS S — Ubuntu 22.04 LTS
2. SSH hardening (key-only, disable password auth)
3. Install Node.js v16 + Node-WebDollar, configure as read-only node (no mining wallet, no pool)
4. Sync blockchain from genesis (~14GB, several hours) or transfer existing blockchain DB
5. Deploy `webd-pay` Flask app
6. Configure systemd services
7. Install nginx + Certbot SSL for `pay.webdollar.cloudns.nz`
8. End-to-end test: create session → pay → webhook fires

### Directory structure

```
/home/ubuntu/
  webd-pay/
    server.py          # Flask app + APScheduler
    payments.db        # SQLite database
    config.json        # node_url, port, rate_limit settings
    static/
      index.html       # landing page
      pay.html         # payment page template
      qrcode.min.js    # QR code library
  webd-node/           # Node-WebDollar (read-only)
    defaultDB/
```

### systemd services

**`/etc/systemd/system/webd-node-pay.service`**
```ini
[Service]
WorkingDirectory=/home/ubuntu/webd-node
ExecStart=/usr/bin/node index.js
Environment=SERVER_PORT=8080
Environment=MAX_BROWSER=0
Environment=MAX_TERMINAL=0
Restart=always
```

**`/etc/systemd/system/webd-pay.service`**
```ini
[Service]
WorkingDirectory=/home/ubuntu/webd-pay
ExecStart=/usr/bin/python3 server.py
Restart=always
```

### nginx config (relevant block)

```nginx
server {
    listen 443 ssl;
    server_name pay.webdollar.cloudns.nz;

    location /api/ {
        proxy_pass http://127.0.0.1:3010/api/;
    }

    location / {
        proxy_pass http://127.0.0.1:3010/;
    }
}
```

---

## Address generation strategy

Each payment session needs a unique receiving address. Two options:

- **Option A (simple):** Pre-generate a pool of 1000 addresses offline using a WebDollar wallet tool, import public keys only into the DB, assign one per session. Recycle expired sessions' addresses back to the pool. Private keys stay offline.
- **Option B (HD wallet):** Derive address on-the-fly from HD wallet using session index. Requires storing xpub on server.

**Recommendation: Option A** — simpler, no private key material on server, easier to audit.

Funds received accumulate on these addresses. A separate manual or automated sweep script moves WEBD to the merchant's address (out of scope for v1).

---

## Out of scope (v1)

- Automatic fund sweeping to merchant wallets
- Multi-currency support
- Dashboard UI for merchants
- Authentication / API keys
- Refunds
