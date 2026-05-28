# WEBD Explorer API + Tracker PWA — Design Spec

**Data:** 2026-05-28  
**Autor:** daniuda  
**Status:** Aprobat

---

## 1. Scopul proiectului

Două componente livrate împreună:

1. **API Python (FastAPI)** — backend nou care completează explorer-ul existent (Node.js, port 5555) cu endpoint-uri lipsă: pool proxy, market proxy, batch address lookup, wallets top, stake total, peers. Rulează pe port `5556`, coexistă cu 5555.

2. **Tracker PWA (Vue 3)** — aplicație web standalone instalabilă pe Android și Windows. Utilizatorul adaugă adrese WEBD cu un label, aplicația interogează API-ul și afișează balanța + blocul la care a fost verificată. Cache local în `localStorage`, refresh smart (actualizează doar dacă blocul curent e mai mare decât cel stocat).

---

## 2. Arhitectură generală

```
[Android / Windows Browser]
  └── Tracker PWA (webdollar.cloudns.nz/tracker/)
        ├── localStorage: [{address, label, balance, lastBlock, lastUpdated}]
        ├── GET /api/chain                    → bloc curent (→ 5555)
        └── GET /api/addresses/batch?addrs=…  → balanțe (→ 5556 Python API)

[webdollar.cloudns.nz — nginx]
  ├── /api/addresses/   → 127.0.0.1:5556 (Python API nou)
  ├── /api/wallets/     → 127.0.0.1:5556
  ├── /api/stake/       → 127.0.0.1:5556
  ├── /api/peers        → 127.0.0.1:5556
  ├── /pool-proxy/      → 127.0.0.1:5556
  ├── /market-proxy/    → 127.0.0.1:5556
  └── /api/             → 127.0.0.1:5555  (explorer existent, nemodificat)

[Python API — port 5556]
  ├── Proxy → WebDollar node (127.0.0.1:8081/SECRET_…)
  ├── Proxy → Pool servers (daniuda, spyclub, timi)
  └── Proxy → Vindax market API
```

---

## 3. API Python

### 3.1 Stack și structură

- **Limbaj:** Python 3
- **Framework:** FastAPI + uvicorn
- **Port:** 5556
- **Deploy:** systemd service (`webd-api.service`)
- **Director:** `webd-explorer-next/api/`

```
webd-explorer-next/api/
  ├── main.py            # FastAPI app, rate limiter, CORS
  ├── config.py          # constante configurabile
  ├── routes/
  │   ├── addresses.py   # /api/addresses/batch
  │   ├── pools.py       # /pool-proxy/{pool}/miners|stats|top
  │   ├── market.py      # /market-proxy/vindax/ticker/24hr
  │   └── network.py     # /api/peers, /api/wallets/top, /api/stake/total
  └── webd-api.service   # systemd unit file
```

### 3.2 Configurare (`config.py`)

```python
NODE_SECRET_URL = "http://127.0.0.1:8081/SECRET_SECRET_SECRET_LONG_SECRET_123456"
EXPLORER_URL    = "http://127.0.0.1:5555"
MAX_REQUESTS_PER_HOUR = 120   # per IP, configurabil
BATCH_ADDRESS_LIMIT   = 50    # max adrese per cerere batch

POOLS = {
    "daniuda": "http://daniuda.ddns.net:8080",
    "spyclub": "https://node.spyclub.ro:8080",
    "timi":    "https://pool.timi.ro",
}
```

### 3.3 Endpoint-uri

| Method | Path | Descriere |
|--------|------|-----------|
| GET | `/api/addresses/batch?addrs=A1,A2,…` | Balanță pentru max 50 adrese simultan |
| GET | `/pool-proxy/{pool}/miners` | Lista mineri pool (`daniuda`, `spyclub`, `timi`) |
| GET | `/pool-proxy/{pool}/stats` | Statistici pool |
| GET | `/pool-proxy/{pool}/top` | Bloc top pool |
| GET | `/market-proxy/vindax/ticker/24hr?symbol=WEBDUSDT` | Prețuri Vindax |
| GET | `/api/wallets/top?limit=50` | Top wallets după balanță |
| GET | `/api/stake/total` | Total WEBD staked |
| GET | `/api/peers` | Peers conectați la nod |

### 3.4 Rate limiting

- Implementat în `main.py` cu un dict în memorie: `{ip: [timestamp, …]}`
- La fiecare request: elimină timestamps mai vechi de 3600s, numără restul
- Dacă count ≥ `MAX_REQUESTS_PER_HOUR` → HTTP 429, header `Retry-After`
- IP-ul e citit din `X-Real-IP` (pus de nginx) sau `request.client.host`
- Rate limiting se aplică pe toate endpoint-urile Python API

### 3.5 Nginx routing (adăugat la config existent)

```nginx
location /pool-proxy/ {
    proxy_pass http://127.0.0.1:5556/pool-proxy/;
    proxy_set_header X-Real-IP $remote_addr;
}
location /market-proxy/ {
    proxy_pass http://127.0.0.1:5556/market-proxy/;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/addresses/ {
    proxy_pass http://127.0.0.1:5556/api/addresses/;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/wallets/ {
    proxy_pass http://127.0.0.1:5556/api/wallets/;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/stake/ {
    proxy_pass http://127.0.0.1:5556/api/stake/;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/peers {
    proxy_pass http://127.0.0.1:5556/api/peers;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 4. Tracker PWA

### 4.1 Stack și hosting

- **Tehnologie:** Vue 3 + Vite + TypeScript
- **Director sursă:** `webd-tracker/` (repo separat sau subdirector în Webdollar_2026)
- **Hosting:** fișiere statice în `/var/www/tracker/` pe VPS, servite de nginx la `/tracker/`
- **PWA:** `manifest.json` + service worker simplu pentru funcționalitate offline (afișează ultimele date din cache)

### 4.2 Schema localStorage

```typescript
interface TrackerEntry {
  address: string       // ex: "WEBD$51576fb4...e7"
  label: string         // ex: "Wallet tipbot"
  balance: number       // WEBD (ex: 1599830)
  lastBlock: number     // blocul la care a fost verificat (ex: 5777721)
  lastUpdated: string   // ISO timestamp
}
```

Cheia în localStorage: `"webd-tracker-entries"` → JSON array de `TrackerEntry`.

### 4.3 Logica de refresh (smart cache)

```
1. GET /api/chain → currentBlock
2. Colectează adresele unde entry.lastBlock < currentBlock
3. GET /api/addresses/batch?addrs=A1,A2,… (max 50)
4. Actualizează localStorage cu {balance, lastBlock: currentBlock, lastUpdated: now}
5. Afișează toate intrările (actualizate + din cache)
```

Dacă `/api/chain` eșuează → afișează toate intrările din cache cu indicator ⚠.

### 4.4 Interfață utilizator

```
┌─────────────────────────────────┐
│  WEBD Tracker          [+ Add]  │
│  Bloc: 5,777,721  [↻ Refresh]  │
├─────────────────────────────────┤
│ 🟢 Wallet tipbot                │
│    WEBD$51576fb4...e7           │
│    1,599,830 WEBD               │
│    bloc 5,777,721 · acum 2 min  │
├─────────────────────────────────┤
│ 🟢 Solo miner                   │
│    WEBD$gD1M#aI3...j$           │
│    14,045,461 WEBD              │
│    bloc 5,777,720 · acum 3 min  │
├─────────────────────────────────┤
│ ⚙ Auto-refresh: [15 min ▼]     │
└─────────────────────────────────┘
```

**Componente:**
- **Header:** bloc curent + buton refresh manual
- **AddressCard:** label, adresă (truncată), balanță formatată, bloc + timp relativ, indicator status, buton delete
- **AddDialog:** input adresă + label opțional, validare format WEBD$
- **Settings bar:** selector interval auto-refresh (Off / 5 / 15 / 30 / 60 min)

**Status indicators:**
- 🟢 Verde — date fresh (lastBlock == currentBlock)
- 🟡 Galben — date mai vechi (lastBlock < currentBlock cu mai puțin de 100 blocuri)
- 🔴 Roșu — eroare la ultima interogare sau date foarte vechi

**Export/Import:** buton "Export JSON" descarcă lista de adrese; buton "Import JSON" încarcă dintr-un fișier (pentru backup și sync manual între dispozitive).

### 4.5 Auto-refresh

- Interval stocat în localStorage: `"webd-tracker-refresh-interval"` (minute, 0 = off)
- `setInterval` pornit la mount cu intervalul configurat
- La schimbarea intervalului: clearInterval + restart

---

## 5. Ordinea de implementare (incremental)

**Faza 1 — API Python MVP**
1. `config.py` + `main.py` cu FastAPI, rate limiter, CORS
2. `/api/addresses/batch` — interogare balanță via explorer 5555 sau nod 8081
3. `/pool-proxy/` — proxy pentru cele 3 pool-uri
4. `/market-proxy/vindax/` — proxy Vindax
5. `webd-api.service` + deploy pe VPS + nginx routing

**Faza 2 — Tracker PWA MVP**
1. Structură Vue 3 proiect `webd-tracker/`
2. localStorage service (CRUD entries)
3. API service (chain + batch addresses)
4. AddressCard component + refresh logic
5. AddDialog + validare adresă
6. `manifest.json` + service worker PWA
7. Deploy pe VPS la `/tracker/`

**Faza 3 — Completare API**
1. `/api/wallets/top` — din MongoDB explorer existent
2. `/api/stake/total`
3. `/api/peers`

**Faza 4+ — Îmbunătățiri tracker (viitor)**
- Notificări când balanța se schimbă
- Grafic evoluție balanță (history în localStorage)
- QR code scanner pentru adăugare adresă

---

## 6. Constrângeri și decizii

- **Python pentru API** — consistent cu celelalte servicii pe VPS (webd-staking, node-manager)
- **Vue 3 pentru tracker** — consistent cu webd-explorer-next
- **Coexistență cu 5555** — nu modificăm explorer-ul existent, nginx rutează selectiv
- **localStorage pentru tracker** — simplu, fără backend propriu; dezavantaj: nu se sincronizează între dispozitive (acceptat pentru MVP)
- **Batch endpoint** — reduce cererile de la N+1 la 2 per refresh, respectă rate limiting
