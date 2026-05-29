# WEBD Explorer API + Tracker PWA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python FastAPI backend (port 5556) that adds pool proxy, market proxy, and batch address lookup to the existing explorer; then build a Vue 3 PWA tracker app that shows WEBD address balances with smart local caching.

**Architecture:** Python API coexists with the existing Node.js explorer (port 5555) — nginx routes specific paths to each. The Tracker PWA is a standalone Vue 3 app hosted at `/tracker/` that stores addresses in localStorage and uses a smart refresh strategy (only fetches when chain block has advanced).

**Tech Stack:** Python 3 + FastAPI + uvicorn + httpx (async HTTP); Vue 3 + Vite + TypeScript; nginx reverse proxy; systemd service management.

---

## ⚠️ Reguli de deploy (citește înainte de orice)

- **Nu opri niciodată** port 5555 (Node.js explorer) sau nginx
- Orice modificare nginx: testează cu `sudo nginx -t` înainte de `sudo systemctl reload nginx`
- Python API rulează pe port **5556** — nu atinge alte porturi
- SSH: `ssh -i ~/.ssh/github_actions_vps ubuntu@webdollar.cloudns.nz`
- Repo local: `D:\Webdollar_2026\` — commit + push după fiecare task

---

## File Map

### Faza 1 — Python API

```
webd-explorer-next/api/
  ├── config.py            # constante: NODE_URL, POOLS, rate limit
  ├── rate_limiter.py      # logică rate limiting per IP (testabilă separat)
  ├── main.py              # FastAPI app, middleware CORS, include routere
  ├── routes/
  │   ├── __init__.py
  │   ├── addresses.py     # GET /api/addresses/batch
  │   ├── pools.py         # GET /pool-proxy/{pool}/{endpoint}
  │   └── market.py        # GET /market-proxy/vindax/ticker/24hr
  ├── requirements.txt
  ├── webd-api.service     # systemd unit
  └── tests/
      ├── __init__.py
      ├── test_rate_limiter.py
      ├── test_addresses.py
      ├── test_pools.py
      └── test_market.py
```

### Faza 2 — Tracker PWA

```
webd-tracker/
  ├── package.json
  ├── vite.config.ts
  ├── tsconfig.json
  ├── index.html
  ├── public/
  │   └── manifest.json
  └── src/
      ├── main.ts
      ├── App.vue
      ├── style.css
      ├── types.ts                  # TrackerEntry interface
      ├── services/
      │   ├── storageService.ts     # localStorage CRUD
      │   └── apiService.ts         # /api/chain + /api/addresses/batch
      └── components/
          ├── AddressCard.vue
          ├── AddDialog.vue
          └── SettingsBar.vue
```

---

# FAZA 1 — Python API

---

## Task 1: Structură proiect + config + rate limiter

**Files:**
- Create: `webd-explorer-next/api/config.py`
- Create: `webd-explorer-next/api/requirements.txt`
- Create: `webd-explorer-next/api/rate_limiter.py`
- Create: `webd-explorer-next/api/tests/__init__.py`
- Create: `webd-explorer-next/api/tests/test_rate_limiter.py`

- [ ] **Step 1: Crează directoarele**

```powershell
mkdir D:\Webdollar_2026\webd-explorer-next\api\routes
mkdir D:\Webdollar_2026\webd-explorer-next\api\tests
```

- [ ] **Step 2: Scrie `requirements.txt`**

`webd-explorer-next/api/requirements.txt`:
```
fastapi==0.115.5
uvicorn[standard]==0.32.1
httpx==0.27.2
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 3: Scrie `config.py`**

`webd-explorer-next/api/config.py`:
```python
NODE_SECRET_URL = "http://127.0.0.1:8081/SECRET_SECRET_SECRET_LONG_SECRET_123456"
EXPLORER_URL = "http://127.0.0.1:5555"
MAX_REQUESTS_PER_HOUR = 120
BATCH_ADDRESS_LIMIT = 50

POOLS = {
    "daniuda": "http://daniuda.ddns.net:8080",
    "spyclub": "https://node.spyclub.ro:8080",
    "timi": "https://pool.timi.ro",
}

VINDAX_BASE_URL = "https://api.vindax.com"
```

- [ ] **Step 4: Scrie testul pentru rate limiter**

`webd-explorer-next/api/tests/test_rate_limiter.py`:
```python
import time
import pytest
from rate_limiter import RateLimiter


def test_allows_requests_under_limit():
    rl = RateLimiter(max_per_hour=5)
    for _ in range(5):
        assert rl.is_allowed("1.2.3.4") is True


def test_blocks_request_over_limit():
    rl = RateLimiter(max_per_hour=3)
    for _ in range(3):
        rl.is_allowed("1.2.3.4")
    assert rl.is_allowed("1.2.3.4") is False


def test_different_ips_are_independent():
    rl = RateLimiter(max_per_hour=2)
    rl.is_allowed("1.1.1.1")
    rl.is_allowed("1.1.1.1")
    assert rl.is_allowed("2.2.2.2") is True


def test_old_timestamps_are_pruned():
    rl = RateLimiter(max_per_hour=2)
    ip = "1.2.3.4"
    # Injectăm timestamp-uri vechi (> 3600s)
    rl._store[ip] = [time.time() - 3700, time.time() - 3700]
    assert rl.is_allowed(ip) is True  # slot liber după prune
```

- [ ] **Step 5: Rulează testul să verifici că pică**

```powershell
cd D:\Webdollar_2026\webd-explorer-next\api
python -m pytest tests/test_rate_limiter.py -v
```
Expected: `ModuleNotFoundError: No module named 'rate_limiter'`

- [ ] **Step 6: Scrie `rate_limiter.py`**

`webd-explorer-next/api/rate_limiter.py`:
```python
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_per_hour: int):
        self.max_per_hour = max_per_hour
        self._store: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - 3600
        self._store[ip] = [t for t in self._store[ip] if t > cutoff]
        if len(self._store[ip]) >= self.max_per_hour:
            return False
        self._store[ip].append(now)
        return True
```

- [ ] **Step 7: Rulează testele să verifici că trec**

```powershell
python -m pytest tests/test_rate_limiter.py -v
```
Expected: 4 PASSED

- [ ] **Step 8: Commit**

```powershell
cd D:\Webdollar_2026
git add webd-explorer-next/api/
git commit -m "feat(api): add config, requirements, rate limiter with tests"
```

---

## Task 2: FastAPI app + endpoint addresses/batch

**Files:**
- Create: `webd-explorer-next/api/main.py`
- Create: `webd-explorer-next/api/routes/__init__.py`
- Create: `webd-explorer-next/api/routes/addresses.py`
- Create: `webd-explorer-next/api/tests/test_addresses.py`

- [ ] **Step 1: Scrie testul pentru batch addresses**

`webd-explorer-next/api/tests/test_addresses.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_batch_empty_returns_empty():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/addresses/batch?addrs=")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_batch_returns_balance_for_address():
    from main import app

    mock_response = {"balance": 1599830, "height": 5777721}

    with patch("routes.addresses.fetch_address_balance", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_response
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/addresses/batch?addrs=WEBD%24abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["address"] == "WEBD$abc123"
    assert data[0]["balance"] == 1599830


@pytest.mark.asyncio
async def test_batch_limit_enforced():
    from main import app
    # 51 adrese — trebuie să returneze 422 sau să taie la 50
    addrs = ",".join([f"WEBD$addr{i}" for i in range(51)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/addresses/batch?addrs={addrs}")
    assert resp.status_code == 400
```

- [ ] **Step 2: Rulează testul să verifici că pică**

```powershell
python -m pytest tests/test_addresses.py -v
```
Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Scrie `routes/__init__.py`**

`webd-explorer-next/api/routes/__init__.py`:
```python
```
(fișier gol)

- [ ] **Step 4: Scrie `routes/addresses.py`**

`webd-explorer-next/api/routes/addresses.py`:
```python
import asyncio
import httpx
from fastapi import APIRouter, Query, HTTPException
from config import EXPLORER_URL, BATCH_ADDRESS_LIMIT

router = APIRouter()


async def fetch_address_balance(address: str) -> dict:
    url = f"{EXPLORER_URL}/address"
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.get(url, params={"address": address})
            resp.raise_for_status()
            data = resp.json()
            return {
                "balance": data.get("balance"),
                "height": data.get("lastSeenHeight") or data.get("height"),
            }
        except Exception:
            return {"balance": None, "height": None}


@router.get("/api/addresses/batch")
async def batch_addresses(addrs: str = Query(default="")):
    if not addrs.strip():
        return []

    address_list = [a.strip() for a in addrs.split(",") if a.strip()]

    if len(address_list) > BATCH_ADDRESS_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Max {BATCH_ADDRESS_LIMIT} addresses per request",
        )

    results = await asyncio.gather(*[fetch_address_balance(addr) for addr in address_list])

    return [
        {"address": addr, "balance": res["balance"], "lastBlock": res["height"]}
        for addr, res in zip(address_list, results)
    ]
```

- [ ] **Step 5: Scrie `main.py`**

`webd-explorer-next/api/main.py`:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from rate_limiter import RateLimiter
from config import MAX_REQUESTS_PER_HOUR
from routes.addresses import router as addresses_router

app = FastAPI(title="WEBD Explorer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_rate_limiter = RateLimiter(max_per_hour=MAX_REQUESTS_PER_HOUR)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    if not _rate_limiter.is_allowed(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": "3600"},
        )
    return await call_next(request)


app.include_router(addresses_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Instalează dependențele și rulează testele**

```powershell
cd D:\Webdollar_2026\webd-explorer-next\api
pip install -r requirements.txt
python -m pytest tests/test_addresses.py -v
```
Expected: 3 PASSED

- [ ] **Step 7: Testează manual că serverul pornește**

```powershell
cd D:\Webdollar_2026\webd-explorer-next\api
uvicorn main:app --port 5556 --reload
```
Accesează `http://localhost:5556/health` → `{"status": "ok"}`
Accesează `http://localhost:5556/docs` → Swagger UI cu endpoint-ul batch

Oprește serverul (Ctrl+C).

- [ ] **Step 8: Commit**

```powershell
cd D:\Webdollar_2026
git add webd-explorer-next/api/
git commit -m "feat(api): add FastAPI app with /api/addresses/batch endpoint"
```

---

## Task 3: Pool proxy + market proxy

**Files:**
- Create: `webd-explorer-next/api/routes/pools.py`
- Create: `webd-explorer-next/api/routes/market.py`
- Create: `webd-explorer-next/api/tests/test_pools.py`
- Create: `webd-explorer-next/api/tests/test_market.py`
- Modify: `webd-explorer-next/api/main.py` (include routerele noi)

- [ ] **Step 1: Scrie testele pentru pool proxy**

`webd-explorer-next/api/tests/test_pools.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_unknown_pool_returns_404():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/pool-proxy/inexistent/miners")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_known_pool_miners_proxied():
    from main import app
    mock_data = [{"address": "WEBD$abc", "totalPOSBalance": "10000"}]

    with patch("routes.pools.proxy_get", new_callable=AsyncMock) as mock_proxy:
        mock_proxy.return_value = mock_data
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/pool-proxy/daniuda/miners")
    assert resp.status_code == 200
    assert resp.json() == mock_data


@pytest.mark.asyncio
async def test_pool_endpoint_validates_allowed_paths():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/pool-proxy/daniuda/delete_all")
    assert resp.status_code == 404
```

- [ ] **Step 2: Scrie testele pentru market proxy**

`webd-explorer-next/api/tests/test_market.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_market_ticker_proxied():
    from main import app
    mock_data = {"symbol": "WEBDUSDT", "lastPrice": "0.00042"}

    with patch("routes.market.proxy_vindax", new_callable=AsyncMock) as mock_proxy:
        mock_proxy.return_value = mock_data
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/market-proxy/vindax/ticker/24hr?symbol=WEBDUSDT")
    assert resp.status_code == 200
    assert resp.json()["lastPrice"] == "0.00042"
```

- [ ] **Step 3: Rulează testele să verifici că pică**

```powershell
python -m pytest tests/test_pools.py tests/test_market.py -v
```
Expected: ImportError sau 404 pentru toate

- [ ] **Step 4: Scrie `routes/pools.py`**

`webd-explorer-next/api/routes/pools.py`:
```python
import httpx
from fastapi import APIRouter, HTTPException
from config import POOLS

router = APIRouter()

ALLOWED_ENDPOINTS = {"miners", "stats", "top"}


async def proxy_get(url: str) -> object:
    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


@router.get("/pool-proxy/{pool}/{endpoint}")
async def pool_proxy(pool: str, endpoint: str):
    if pool not in POOLS:
        raise HTTPException(status_code=404, detail=f"Unknown pool: {pool}")
    if endpoint not in ALLOWED_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint}")
    url = f"{POOLS[pool]}/{endpoint}"
    try:
        return await proxy_get(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pool unreachable: {exc}")
```

- [ ] **Step 5: Scrie `routes/market.py`**

`webd-explorer-next/api/routes/market.py`:
```python
import httpx
from fastapi import APIRouter, Query, HTTPException
from config import VINDAX_BASE_URL

router = APIRouter()


async def proxy_vindax(symbol: str) -> object:
    url = f"{VINDAX_BASE_URL}/api/v1/ticker/24hr"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={"symbol": symbol})
        resp.raise_for_status()
        return resp.json()


@router.get("/market-proxy/vindax/ticker/24hr")
async def vindax_ticker(symbol: str = Query(...)):
    try:
        return await proxy_vindax(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Market API unreachable: {exc}")
```

- [ ] **Step 6: Actualizează `main.py` să includă routerele noi**

`webd-explorer-next/api/main.py` — modifică secțiunea imports și include_router:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from rate_limiter import RateLimiter
from config import MAX_REQUESTS_PER_HOUR
from routes.addresses import router as addresses_router
from routes.pools import router as pools_router
from routes.market import router as market_router

app = FastAPI(title="WEBD Explorer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_rate_limiter = RateLimiter(max_per_hour=MAX_REQUESTS_PER_HOUR)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    if not _rate_limiter.is_allowed(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": "3600"},
        )
    return await call_next(request)


app.include_router(addresses_router)
app.include_router(pools_router)
app.include_router(market_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Rulează toate testele**

```powershell
python -m pytest tests/ -v
```
Expected: toate PASSED (7+ teste)

- [ ] **Step 8: Commit**

```powershell
cd D:\Webdollar_2026
git add webd-explorer-next/api/
git commit -m "feat(api): add pool proxy and market proxy routes"
```

---

## Task 4: Systemd service + deploy pe VPS

**Files:**
- Create: `webd-explorer-next/api/webd-api.service`

- [ ] **Step 1: Scrie `webd-api.service`**

`webd-explorer-next/api/webd-api.service`:
```ini
[Unit]
Description=WEBD Explorer Python API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/webd-explorer-next/api
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 5556 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit și push**

```powershell
cd D:\Webdollar_2026
git add webd-explorer-next/api/webd-api.service
git commit -m "feat(api): add systemd service file"
git push origin master
```

- [ ] **Step 3: SSH pe VPS și pull**

```powershell
ssh -i ~/.ssh/github_actions_vps ubuntu@webdollar.cloudns.nz
```

Pe VPS:
```bash
cd /home/ubuntu/webd-explorer-next
git pull origin master
```

- [ ] **Step 4: Instalează Python dependencies pe VPS**

```bash
cd /home/ubuntu/webd-explorer-next/api
pip3 install -r requirements.txt
```

- [ ] **Step 5: Testează că API-ul pornește manual pe VPS**

```bash
cd /home/ubuntu/webd-explorer-next/api
python3 -m uvicorn main:app --host 127.0.0.1 --port 5556
```
Într-un alt terminal:
```bash
curl http://127.0.0.1:5556/health
```
Expected: `{"status":"ok"}`

Oprește cu Ctrl+C.

- [ ] **Step 6: Instalează serviciul systemd**

```bash
sudo cp /home/ubuntu/webd-explorer-next/api/webd-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable webd-api
sudo systemctl start webd-api
sudo systemctl status webd-api
```
Expected: `Active: active (running)`

- [ ] **Step 7: Verifică că funcționează pe 5556**

```bash
curl http://127.0.0.1:5556/health
curl "http://127.0.0.1:5556/pool-proxy/daniuda/miners" | head -c 200
```
Expected: health = `{"status":"ok"}`, miners = array JSON cu mineri

- [ ] **Step 8: Adaugă nginx routing (fără să atingi /api/ existent)**

Găsește configul nginx:
```bash
ls /etc/nginx/sites-enabled/
```
Deschide fișierul (probabil `webd-explorer-https` sau `default`):
```bash
sudo nano /etc/nginx/sites-enabled/<nume-fisier>
```

Adaugă blocurile noi **ÎNAINTE** de `location /api/` existent:
```nginx
location /pool-proxy/ {
    proxy_pass http://127.0.0.1:5556/pool-proxy/;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Host $host;
}
location /market-proxy/ {
    proxy_pass http://127.0.0.1:5556/market-proxy/;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Host $host;
}
location /api/addresses/ {
    proxy_pass http://127.0.0.1:5556/api/addresses/;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Host $host;
}
```

- [ ] **Step 9: Testează și reloadează nginx**

```bash
sudo nginx -t
```
Expected: `syntax is ok` + `test is successful`

```bash
sudo systemctl reload nginx
```

- [ ] **Step 10: Testează endpoint-urile prin nginx**

```bash
curl https://webdollar.cloudns.nz/pool-proxy/daniuda/miners | head -c 200
curl "https://webdollar.cloudns.nz/market-proxy/vindax/ticker/24hr?symbol=WEBDUSDT"
curl "https://webdollar.cloudns.nz/api/addresses/batch?addrs=WEBD%24gAAqp48%24Ix7vfm%404LAxzdAWI4dZJMS2wXL%24"
```
Expected: răspunsuri JSON valide de la fiecare endpoint

---

# FAZA 2 — Tracker PWA

---

## Task 5: Scaffolding Vue 3 + types + storage service

**Files:**
- Create: `webd-tracker/` (proiect nou Vite)
- Create: `webd-tracker/src/types.ts`
- Create: `webd-tracker/src/services/storageService.ts`
- Create: `webd-tracker/src/services/storageService.test.ts`

- [ ] **Step 1: Crează proiectul Vue 3**

```powershell
cd D:\Webdollar_2026
npm create vite@latest webd-tracker -- --template vue-ts
cd webd-tracker
npm install
```

- [ ] **Step 2: Instalează vitest pentru teste**

```powershell
npm install -D vitest @vitest/ui jsdom @vue/test-utils
```

Adaugă în `webd-tracker/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

Adaugă în `webd-tracker/package.json` la `scripts`:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 3: Scrie `src/types.ts`**

`webd-tracker/src/types.ts`:
```typescript
export interface TrackerEntry {
  address: string
  label: string
  balance: number | null
  lastBlock: number
  lastUpdated: string
  error?: boolean
}

export type RefreshInterval = 0 | 5 | 15 | 30 | 60
```

- [ ] **Step 4: Scrie testul pentru storage service**

`webd-tracker/src/services/storageService.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { getEntries, saveEntry, deleteEntry } from './storageService'

beforeEach(() => {
  localStorage.clear()
})

describe('storageService', () => {
  it('returns empty array when no entries', () => {
    expect(getEntries()).toEqual([])
  })

  it('saves and retrieves an entry', () => {
    const entry = {
      address: 'WEBD$abc123',
      label: 'Test wallet',
      balance: 1000,
      lastBlock: 5000000,
      lastUpdated: '2026-05-29T10:00:00Z',
    }
    saveEntry(entry)
    const entries = getEntries()
    expect(entries).toHaveLength(1)
    expect(entries[0].address).toBe('WEBD$abc123')
  })

  it('updates existing entry by address', () => {
    const entry = { address: 'WEBD$abc', label: 'A', balance: 100, lastBlock: 1, lastUpdated: '' }
    saveEntry(entry)
    saveEntry({ ...entry, balance: 200, lastBlock: 2 })
    const entries = getEntries()
    expect(entries).toHaveLength(1)
    expect(entries[0].balance).toBe(200)
  })

  it('deletes entry by address', () => {
    saveEntry({ address: 'WEBD$abc', label: 'A', balance: 0, lastBlock: 0, lastUpdated: '' })
    deleteEntry('WEBD$abc')
    expect(getEntries()).toHaveLength(0)
  })

  it('ignores delete of non-existent address', () => {
    expect(() => deleteEntry('WEBD$notexist')).not.toThrow()
  })
})
```

- [ ] **Step 5: Rulează testul să verifici că pică**

```powershell
cd D:\Webdollar_2026\webd-tracker
npm test
```
Expected: `Cannot find module './storageService'`

- [ ] **Step 6: Scrie `src/services/storageService.ts`**

`webd-tracker/src/services/storageService.ts`:
```typescript
import type { TrackerEntry } from '../types'

const STORAGE_KEY = 'webd-tracker-entries'
const INTERVAL_KEY = 'webd-tracker-refresh-interval'

export function getEntries(): TrackerEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as TrackerEntry[]) : []
  } catch {
    return []
  }
}

export function saveEntry(entry: TrackerEntry): void {
  const entries = getEntries()
  const idx = entries.findIndex((e) => e.address === entry.address)
  if (idx >= 0) {
    entries[idx] = entry
  } else {
    entries.push(entry)
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
}

export function deleteEntry(address: string): void {
  const entries = getEntries().filter((e) => e.address !== address)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
}

export function clearAll(): void {
  localStorage.removeItem(STORAGE_KEY)
}

export function getRefreshInterval(): number {
  return Number(localStorage.getItem(INTERVAL_KEY) ?? '15')
}

export function setRefreshInterval(minutes: number): void {
  localStorage.setItem(INTERVAL_KEY, String(minutes))
}
```

- [ ] **Step 7: Rulează testele să verifici că trec**

```powershell
npm test
```
Expected: 5 PASSED

- [ ] **Step 8: Commit**

```powershell
cd D:\Webdollar_2026
git add webd-tracker/
git commit -m "feat(tracker): scaffold Vue 3 project with types and storageService"
```

---

## Task 6: API service + logica de refresh

**Files:**
- Create: `webd-tracker/src/services/apiService.ts`
- Create: `webd-tracker/src/services/apiService.test.ts`

- [ ] **Step 1: Scrie testul pentru API service**

`webd-tracker/src/services/apiService.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchCurrentBlock, fetchBatchBalances } from './apiService'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchCurrentBlock', () => {
  it('returns height from chain response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ height: 5777721 }),
    } as Response)

    const block = await fetchCurrentBlock()
    expect(block).toBe(5777721)
  })

  it('returns null on network error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network'))
    const block = await fetchCurrentBlock()
    expect(block).toBeNull()
  })
})

describe('fetchBatchBalances', () => {
  it('returns array of {address, balance, lastBlock} for given addresses', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { address: 'WEBD$abc', balance: 1000, lastBlock: 5777721 },
      ],
    } as Response)

    const results = await fetchBatchBalances(['WEBD$abc'])
    expect(results).toHaveLength(1)
    expect(results[0].balance).toBe(1000)
  })

  it('returns empty array on error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('fail'))
    const results = await fetchBatchBalances(['WEBD$abc'])
    expect(results).toEqual([])
  })

  it('returns empty array for empty input', async () => {
    const results = await fetchBatchBalances([])
    expect(results).toEqual([])
  })
})
```

- [ ] **Step 2: Rulează testul să verifici că pică**

```powershell
npm test
```
Expected: `Cannot find module './apiService'`

- [ ] **Step 3: Scrie `src/services/apiService.ts`**

`webd-tracker/src/services/apiService.ts`:
```typescript
const BASE = 'https://webdollar.cloudns.nz'

export async function fetchCurrentBlock(): Promise<number | null> {
  try {
    const resp = await fetch(`${BASE}/api/chain`)
    if (!resp.ok) return null
    const data = await resp.json() as { height?: number }
    return typeof data.height === 'number' ? data.height : null
  } catch {
    return null
  }
}

export interface BatchResult {
  address: string
  balance: number | null
  lastBlock: number | null
}

export async function fetchBatchBalances(addresses: string[]): Promise<BatchResult[]> {
  if (addresses.length === 0) return []
  try {
    const addrs = addresses.map(encodeURIComponent).join(',')
    const resp = await fetch(`${BASE}/api/addresses/batch?addrs=${addrs}`)
    if (!resp.ok) return []
    return await resp.json() as BatchResult[]
  } catch {
    return []
  }
}
```

- [ ] **Step 4: Rulează testele să verifici că trec**

```powershell
npm test
```
Expected: toate PASSED

- [ ] **Step 5: Commit**

```powershell
cd D:\Webdollar_2026
git add webd-tracker/src/services/
git commit -m "feat(tracker): add apiService with fetchCurrentBlock and fetchBatchBalances"
```

---

## Task 7: Componente Vue + App principal

**Files:**
- Modify: `webd-tracker/src/App.vue`
- Create: `webd-tracker/src/components/AddressCard.vue`
- Create: `webd-tracker/src/components/AddDialog.vue`
- Create: `webd-tracker/src/components/SettingsBar.vue`
- Modify: `webd-tracker/src/style.css`

- [ ] **Step 1: Scrie `src/components/AddressCard.vue`**

`webd-tracker/src/components/AddressCard.vue`:
```vue
<template>
  <div class="card" :class="statusClass">
    <div class="card-header">
      <span class="status-dot">{{ statusIcon }}</span>
      <span class="label">{{ entry.label || 'Fără label' }}</span>
      <button class="delete-btn" @click="$emit('delete', entry.address)">✕</button>
    </div>
    <div class="address">{{ shortAddress }}</div>
    <div class="balance" v-if="entry.balance !== null">
      {{ formatBalance(entry.balance) }} WEBD
    </div>
    <div class="balance error" v-else-if="entry.error">Eroare la interogare</div>
    <div class="balance loading" v-else>Se încarcă...</div>
    <div class="meta">
      bloc {{ entry.lastBlock > 0 ? entry.lastBlock.toLocaleString() : '—' }}
      <span v-if="entry.lastUpdated"> · {{ timeAgo(entry.lastUpdated) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TrackerEntry } from '../types'

const props = defineProps<{ entry: TrackerEntry; currentBlock: number | null }>()
defineEmits<{ (e: 'delete', address: string): void }>()

const shortAddress = computed(() => {
  const a = props.entry.address
  return a.length > 20 ? a.slice(0, 12) + '...' + a.slice(-6) : a
})

const statusClass = computed(() => {
  if (props.entry.error) return 'status-red'
  if (props.entry.balance === null) return 'status-gray'
  if (props.currentBlock && props.entry.lastBlock >= props.currentBlock) return 'status-green'
  if (props.currentBlock && props.currentBlock - props.entry.lastBlock < 100) return 'status-yellow'
  return 'status-red'
})

const statusIcon = computed(() => {
  if (statusClass.value === 'status-green') return '🟢'
  if (statusClass.value === 'status-yellow') return '🟡'
  if (statusClass.value === 'status-gray') return '⚪'
  return '🔴'
})

function formatBalance(b: number): string {
  return b.toLocaleString('ro-RO')
}

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}min`
  return `${Math.floor(diff / 3600)}h`
}
</script>
```

- [ ] **Step 2: Scrie `src/components/AddDialog.vue`**

`webd-tracker/src/components/AddDialog.vue`:
```vue
<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>Adaugă adresă WEBD</h3>
      <input
        v-model="address"
        placeholder="WEBD$..."
        class="input"
        @keyup.enter="submit"
      />
      <input
        v-model="label"
        placeholder="Label (opțional, ex: Wallet tipbot)"
        class="input"
        @keyup.enter="submit"
      />
      <div class="error-msg" v-if="error">{{ error }}</div>
      <div class="dialog-actions">
        <button @click="$emit('close')" class="btn-cancel">Anulează</button>
        <button @click="submit" class="btn-add">Adaugă</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  (e: 'add', address: string, label: string): void
  (e: 'close'): void
}>()

const address = ref('')
const label = ref('')
const error = ref('')

function submit() {
  const trimmed = address.value.trim()
  if (!trimmed) {
    error.value = 'Adresa nu poate fi goală'
    return
  }
  if (!trimmed.startsWith('WEBD$') && !trimmed.match(/^[0-9a-fA-F]{40}$/)) {
    error.value = 'Format adresă invalid (trebuie să înceapă cu WEBD$)'
    return
  }
  error.value = ''
  emit('add', trimmed, label.value.trim())
  address.value = ''
  label.value = ''
}
</script>
```

- [ ] **Step 3: Scrie `src/components/SettingsBar.vue`**

`webd-tracker/src/components/SettingsBar.vue`:
```vue
<template>
  <div class="settings-bar">
    <span>Auto-refresh:</span>
    <select :value="modelValue" @change="onChange" class="select-interval">
      <option :value="0">Off</option>
      <option :value="5">5 min</option>
      <option :value="15">15 min</option>
      <option :value="30">30 min</option>
      <option :value="60">60 min</option>
    </select>
  </div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: number): void }>()
function onChange(e: Event) {
  emit('update:modelValue', Number((e.target as HTMLSelectElement).value))
}
</script>
```

- [ ] **Step 4: Scrie `src/App.vue`**

`webd-tracker/src/App.vue`:
```vue
<template>
  <div class="app">
    <header class="app-header">
      <div class="header-left">
        <h1>WEBD Tracker</h1>
        <span class="block-info" v-if="currentBlock">
          Bloc: {{ currentBlock.toLocaleString() }}
        </span>
        <span class="block-info error" v-else-if="apiError">⚠ API offline</span>
      </div>
      <div class="header-right">
        <button @click="refresh" :disabled="refreshing" class="btn-refresh">
          {{ refreshing ? '...' : '↻ Refresh' }}
        </button>
        <button @click="showAdd = true" class="btn-add">+ Add</button>
      </div>
    </header>

    <main class="entries-list">
      <div v-if="entries.length === 0" class="empty-state">
        Nicio adresă adăugată. Apasă "+ Add" pentru a începe.
      </div>
      <AddressCard
        v-for="entry in entries"
        :key="entry.address"
        :entry="entry"
        :currentBlock="currentBlock"
        @delete="removeEntry"
      />
    </main>

    <footer>
      <SettingsBar v-model="refreshInterval" />
      <button @click="exportJson" class="btn-export">Export JSON</button>
    </footer>

    <AddDialog
      v-if="showAdd"
      @add="addEntry"
      @close="showAdd = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { TrackerEntry } from './types'
import {
  getEntries, saveEntry, deleteEntry, getRefreshInterval, setRefreshInterval,
} from './services/storageService'
import { fetchCurrentBlock, fetchBatchBalances } from './services/apiService'
import AddressCard from './components/AddressCard.vue'
import AddDialog from './components/AddDialog.vue'
import SettingsBar from './components/SettingsBar.vue'

const entries = ref<TrackerEntry[]>(getEntries())
const currentBlock = ref<number | null>(null)
const showAdd = ref(false)
const refreshing = ref(false)
const apiError = ref(false)
const refreshInterval = ref(getRefreshInterval())

let intervalId: ReturnType<typeof setInterval> | null = null

async function refresh() {
  refreshing.value = true
  apiError.value = false
  try {
    const block = await fetchCurrentBlock()
    if (block === null) { apiError.value = true; return }
    currentBlock.value = block

    const stale = entries.value.filter((e) => e.lastBlock < block)
    if (stale.length === 0) return

    const results = await fetchBatchBalances(stale.map((e) => e.address))
    const now = new Date().toISOString()

    for (const result of results) {
      const entry = entries.value.find((e) => e.address === result.address)
      if (!entry) continue
      const updated: TrackerEntry = {
        ...entry,
        balance: result.balance,
        lastBlock: result.lastBlock ?? block,
        lastUpdated: now,
        error: result.balance === null,
      }
      saveEntry(updated)
    }
    entries.value = getEntries()
  } finally {
    refreshing.value = false
  }
}

function addEntry(address: string, label: string) {
  const entry: TrackerEntry = {
    address,
    label,
    balance: null,
    lastBlock: 0,
    lastUpdated: '',
  }
  saveEntry(entry)
  entries.value = getEntries()
  showAdd.value = false
  refresh()
}

function removeEntry(address: string) {
  deleteEntry(address)
  entries.value = getEntries()
}

function exportJson() {
  const blob = new Blob([JSON.stringify(entries.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'webd-tracker-backup.json'
  a.click()
  URL.revokeObjectURL(url)
}

function startAutoRefresh() {
  if (intervalId) clearInterval(intervalId)
  if (refreshInterval.value > 0) {
    intervalId = setInterval(refresh, refreshInterval.value * 60 * 1000)
  }
}

watch(refreshInterval, (val) => {
  setRefreshInterval(val)
  startAutoRefresh()
})

onMounted(() => {
  refresh()
  startAutoRefresh()
})

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>
```

- [ ] **Step 5: Testează că aplicația compilează**

```powershell
cd D:\Webdollar_2026\webd-tracker
npm run build
```
Expected: fișiere generate în `dist/` fără erori TypeScript

- [ ] **Step 6: Rulează local și verifică UI**

```powershell
npm run dev
```
Deschide `http://localhost:5173` — verifică:
- Header cu "WEBD Tracker" + bloc curent
- Buton "+ Add" deschide dialogul
- Adaugă o adresă reală (ex: `WEBD$gAAqp48$Ix7vfm@4LAxzdAWI4dZJMS2wXL$`)
- Cardul apare cu balanța

- [ ] **Step 7: Commit**

```powershell
cd D:\Webdollar_2026
git add webd-tracker/
git commit -m "feat(tracker): add Vue components and App with smart refresh logic"
git push origin master
```

---

## Task 8: PWA manifest + deploy pe VPS

**Files:**
- Create: `webd-tracker/public/manifest.json`
- Modify: `webd-tracker/index.html`
- Modify: `webd-tracker/vite.config.ts`

- [ ] **Step 1: Scrie `public/manifest.json`**

`webd-tracker/public/manifest.json`:
```json
{
  "name": "WEBD Tracker",
  "short_name": "WEBD",
  "description": "Monitor adrese WebDollar",
  "start_url": "/tracker/",
  "display": "standalone",
  "background_color": "#1a1a2e",
  "theme_color": "#16213e",
  "icons": [
    {
      "src": "vite.svg",
      "sizes": "any",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ]
}
```

- [ ] **Step 2: Actualizează `index.html` cu link manifest**

`webd-tracker/index.html` — adaugă în `<head>`:
```html
<link rel="manifest" href="/tracker/manifest.json">
<meta name="theme-color" content="#16213e">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="WEBD Tracker">
```

- [ ] **Step 3: Configurează Vite pentru base path `/tracker/`**

`webd-tracker/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: process.env.NODE_ENV === 'production' ? '/tracker/' : '/',
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 4: Build pentru producție**

```powershell
cd D:\Webdollar_2026\webd-tracker
npm run build
```
Expected: `dist/` generat cu `index.html` și assets cu prefix `/tracker/`

- [ ] **Step 5: Commit și push**

```powershell
cd D:\Webdollar_2026
git add webd-tracker/
git commit -m "feat(tracker): add PWA manifest and configure base path /tracker/"
git push origin master
```

- [ ] **Step 6: Deploy pe VPS**

```powershell
ssh -i ~/.ssh/github_actions_vps ubuntu@webdollar.cloudns.nz
```

Pe VPS:
```bash
sudo mkdir -p /var/www/tracker
sudo cp -r /home/ubuntu/webd-tracker/dist/. /var/www/tracker/
sudo chown -R www-data:www-data /var/www/tracker
```

Sau dacă dist nu e pe VPS, copiază de pe local:
```powershell
scp -i ~/.ssh/github_actions_vps -r D:\Webdollar_2026\webd-tracker\dist\* ubuntu@webdollar.cloudns.nz:/tmp/tracker-dist/
```
Pe VPS:
```bash
sudo mkdir -p /var/www/tracker
sudo cp -r /tmp/tracker-dist/. /var/www/tracker/
```

- [ ] **Step 7: Adaugă nginx location pentru `/tracker/`**

Pe VPS, deschide configul nginx:
```bash
sudo nano /etc/nginx/sites-enabled/<nume-fisier>
```

Adaugă:
```nginx
location /tracker/ {
    root /var/www;
    index index.html;
    try_files $uri $uri/ /tracker/index.html;
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

- [ ] **Step 8: Verifică în browser**

Deschide `https://webdollar.cloudns.nz/tracker/` — aplicația trebuie să se încarce.

Pe Android Chrome: meniu → "Add to Home Screen" → instalează ca PWA.

- [ ] **Step 9: Test complet end-to-end**

1. Adaugă adresa `WEBD$gAAqp48$Ix7vfm@4LAxzdAWI4dZJMS2wXL$` cu label "Pool staking"
2. Verifică că apare balanța și blocul curent
3. Setează auto-refresh la 15 min
4. Reîncarcă pagina — datele trebuie să persist din localStorage
5. Testează butonul "Export JSON"

---

## Checklist final

- [ ] API Python pornit pe 5556 (`systemctl status webd-api`)
- [ ] Nginx rutează corect `/pool-proxy/`, `/market-proxy/`, `/api/addresses/` → 5556
- [ ] Nginx rutează `/api/` → 5555 (neatins, verifică că explorer-ul funcționează)
- [ ] Tracker PWA accesibil la `https://webdollar.cloudns.nz/tracker/`
- [ ] Toate testele trec (`pytest` + `vitest`)
- [ ] Git push pe master după fiecare task
