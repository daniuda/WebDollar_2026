#!/usr/bin/env python3
"""
WebDollar Delegated Staking Service — non-custodial, off-chain automated.
Fondurile rămân în wallet-ul delegatorului. Serviciul verifică balanța on-chain
și plătește automat recompensele proporțional cu stake-ul declarat.

Requires: pip3 install cryptography
"""
import json, os, sqlite3, ssl, subprocess, sys, threading, time
import urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# tx_builder.py must be in same directory
sys.path.insert(0, str(Path(__file__).parent))
try:
    from tx_builder import build_signed_tx
    HAS_TX_BUILDER = True
except ImportError as _e:
    HAS_TX_BUILDER = False
    _TX_BUILDER_ERR = str(_e)

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'config.json'
DB_PATH = BASE_DIR / 'staking.db'
DASHBOARD_HTML = BASE_DIR / 'dashboard.html'

# ── config ─────────────────────────────────────────────────────────────────────
def load_config():
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return json.load(f)

cfg = load_config()
pool_cfg = cfg['pool']
staking_cfg = cfg.get('staking', {})

NODE_URL      = pool_cfg['node_url'].rstrip('/')
BROADCAST_URL = pool_cfg.get('broadcast_url', 'http://localhost:3001/tx/broadcast')
POOL_ADDRESS  = pool_cfg['address']
POOL_PRIVKEY  = pool_cfg['private_key_hex']
POOL_PUBKEY   = pool_cfg['public_key_hex']
POOL_FEE_PCT  = float(pool_cfg.get('fee_pct', 10)) / 100.0

MIN_STAKE     = float(staking_cfg.get('min_stake_webd', 100))
MIN_PAYOUT    = float(staking_cfg.get('min_payout_webd', 10))
BAL_INTERVAL  = int(staking_cfg.get('balance_check_interval_sec', 300))
REW_INTERVAL  = int(staking_cfg.get('reward_check_interval_sec', 30))
HISTORY_DAYS  = int(staking_cfg.get('history_days', 30))

# ── database ───────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _db_lock, _conn() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS delegations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                amount_claimed REAL NOT NULL,
                amount_verified REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                registered_ts INTEGER NOT NULL,
                last_check_ts INTEGER
            );
            CREATE TABLE IF NOT EXISTS balance_history (
                ts INTEGER NOT NULL,
                address TEXT NOT NULL,
                balance REAL NOT NULL,
                PRIMARY KEY (ts, address)
            );
            CREATE TABLE IF NOT EXISTS reward_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                pool_balance_before REAL NOT NULL,
                pool_balance_after REAL NOT NULL,
                reward_amount REAL NOT NULL,
                total_stake REAL NOT NULL,
                distributed REAL NOT NULL,
                pool_fee_taken REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reward_event_id INTEGER REFERENCES reward_events(id),
                ts INTEGER NOT NULL,
                to_address TEXT NOT NULL,
                amount_webd REAL NOT NULL,
                tx_hex TEXT,
                tx_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
            );
        ''')
        c.commit()

# ── DB helpers ─────────────────────────────────────────────────────────────────
def db_get_delegation(address: str):
    with _db_lock, _conn() as c:
        row = c.execute('SELECT * FROM delegations WHERE address=?', (address,)).fetchone()
    return dict(row) if row else None

def db_upsert_delegation(address: str, amount_claimed: float, amount_verified: float, status: str):
    now = int(time.time())
    with _db_lock, _conn() as c:
        c.execute('''
            INSERT INTO delegations (address, amount_claimed, amount_verified, status, registered_ts, last_check_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                amount_claimed=excluded.amount_claimed,
                amount_verified=excluded.amount_verified,
                status=excluded.status,
                last_check_ts=excluded.last_check_ts
        ''', (address, amount_claimed, amount_verified, status, now, now))
        c.commit()

def db_update_delegation_balance(address: str, amount_verified: float, status: str):
    with _db_lock, _conn() as c:
        c.execute('''UPDATE delegations SET amount_verified=?, status=?, last_check_ts=? WHERE address=?''',
                  (amount_verified, status, int(time.time()), address))
        c.commit()

def db_get_active_delegations():
    with _db_lock, _conn() as c:
        rows = c.execute("SELECT * FROM delegations WHERE status='active'").fetchall()
    return [dict(r) for r in rows]

def db_get_all_delegations():
    with _db_lock, _conn() as c:
        rows = c.execute('SELECT * FROM delegations ORDER BY amount_verified DESC').fetchall()
    return [dict(r) for r in rows]

def db_add_reward_event(pool_before, pool_after, reward, total_stake, distributed, fee_taken) -> int:
    with _db_lock, _conn() as c:
        cur = c.execute('''
            INSERT INTO reward_events (ts, pool_balance_before, pool_balance_after, reward_amount, total_stake, distributed, pool_fee_taken)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (int(time.time()), pool_before, pool_after, reward, total_stake, distributed, fee_taken))
        c.commit()
        return cur.lastrowid

def db_add_payout(reward_event_id, to_address, amount_webd, tx_hex=None, tx_id=None, status='pending'):
    with _db_lock, _conn() as c:
        c.execute('''
            INSERT INTO payouts (reward_event_id, ts, to_address, amount_webd, tx_hex, tx_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (reward_event_id, int(time.time()), to_address, amount_webd, tx_hex, tx_id, status))
        c.commit()

def db_update_payout_status(to_address, old_status, tx_hex, tx_id, new_status):
    with _db_lock, _conn() as c:
        c.execute('''UPDATE payouts SET tx_hex=?, tx_id=?, status=?
                     WHERE to_address=? AND status=?''',
                  (tx_hex, tx_id, new_status, to_address, old_status))
        c.commit()

def db_get_recent_rewards(limit=20):
    with _db_lock, _conn() as c:
        rows = c.execute('SELECT * FROM reward_events ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
    return [dict(r) for r in rows]

def db_get_payouts_for_address(address, limit=50):
    with _db_lock, _conn() as c:
        rows = c.execute('SELECT * FROM payouts WHERE to_address=? ORDER BY ts DESC LIMIT ?',
                         (address, limit)).fetchall()
    return [dict(r) for r in rows]

def db_get_pending_payouts():
    with _db_lock, _conn() as c:
        rows = c.execute("SELECT * FROM payouts WHERE status='pending' ORDER BY ts").fetchall()
    return [dict(r) for r in rows]

def db_prune():
    cutoff = int(time.time()) - HISTORY_DAYS * 86400
    with _db_lock, _conn() as c:
        c.execute('DELETE FROM balance_history WHERE ts < ?', (cutoff,))
        c.commit()

# ── http helpers ───────────────────────────────────────────────────────────────
_insecure_ctx = ssl.create_default_context()
_insecure_ctx.check_hostname = False
_insecure_ctx.verify_mode = ssl.CERT_NONE

def _http_get_json(url: str, timeout=8):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'webd-staking/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except ssl.SSLError:
        with urllib.request.urlopen(req, timeout=timeout, context=_insecure_ctx) as r:
            return json.loads(r.read().decode('utf-8'))

def _http_post_json(url: str, data: dict, timeout=10):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except ssl.SSLError:
        with urllib.request.urlopen(req, timeout=timeout, context=_insecure_ctx) as r:
            return json.loads(r.read().decode('utf-8'))

def fetch_balance(address: str) -> float | None:
    """Query balance from node. Returns WEBD float or None on failure."""
    endpoints = [
        f'{NODE_URL}/totalPOSBalance/{address}',
        f'{NODE_URL}/address/{address}/balance',
        f'{NODE_URL}/wallet/{address}',
    ]
    for url in endpoints:
        try:
            data = _http_get_json(url)
            if isinstance(data, (int, float)):
                return float(data) / 10_000
            if isinstance(data, dict):
                for key in ('balance', 'amount', 'total', 'webd', 'totalPOSBalance'):
                    if key in data:
                        v = data[key]
                        if v is not None:
                            raw = float(v)
                            # valori > 10^9 sunt în unități; <= 10^9 sunt în WEBD direct
                            return raw / 10_000 if raw > 1_000_000 else raw
        except Exception:
            continue
    return None

def broadcast_tx(tx_hex: str) -> dict:
    """Send signed tx to local node for WebSocket broadcast."""
    try:
        return _http_post_json(BROADCAST_URL, {'hex': tx_hex})
    except Exception as e:
        return {'result': False, 'error': str(e)}

# ── balance monitoring thread ──────────────────────────────────────────────────
def balance_monitor_loop():
    while True:
        try:
            delegations = db_get_all_delegations()
            for d in delegations:
                addr = d['address']
                balance = fetch_balance(addr)
                if balance is None:
                    print(f'[BAL] Nu s-a putut obține balanța pentru {addr[:20]}...', flush=True)
                    continue
                claimed = d['amount_claimed']
                verified = min(claimed, balance)
                status = 'active' if balance >= claimed else 'inactive'
                db_update_delegation_balance(addr, verified, status)
                with _db_lock, _conn() as c:
                    c.execute('INSERT OR REPLACE INTO balance_history (ts, address, balance) VALUES (?,?,?)',
                              (int(time.time()), addr, balance))
                    c.commit()
                print(f'[BAL] {addr[:20]}... balance={balance:.2f} verified={verified:.2f} status={status}', flush=True)
            db_prune()
        except Exception as e:
            print(f'[BAL ERROR] {e}', flush=True)
        time.sleep(BAL_INTERVAL)

# ── reward detection + auto-payout thread ─────────────────────────────────────
_pool_max_balance = 0.0
_pool_max_lock = threading.Lock()

def reward_monitor_loop():
    global _pool_max_balance
    # Bootstrap: get initial balance
    bal = fetch_balance(POOL_ADDRESS)
    if bal is not None:
        with _pool_max_lock:
            _pool_max_balance = bal
    print(f'[REW] Balanță inițială pool: {_pool_max_balance:.4f} WEBD', flush=True)

    while True:
        time.sleep(REW_INTERVAL)
        try:
            current = fetch_balance(POOL_ADDRESS)
            if current is None:
                continue

            with _pool_max_lock:
                prev_max = _pool_max_balance

            if current > prev_max:
                reward = current - prev_max
                with _pool_max_lock:
                    _pool_max_balance = current
                print(f'[REW] Recompensă detectată: +{reward:.4f} WEBD (pool: {prev_max:.4f} → {current:.4f})', flush=True)
                _distribute_reward(prev_max, current, reward)
            else:
                with _pool_max_lock:
                    _pool_max_balance = max(_pool_max_balance, current)

        except Exception as e:
            print(f'[REW ERROR] {e}', flush=True)

def _distribute_reward(pool_before: float, pool_after: float, reward: float):
    """Calculate and issue payouts for a reward event."""
    delegations = db_get_active_delegations()
    if not delegations:
        print('[REW] Niciun delegator activ — recompensa rămâne la pool.', flush=True)
        return

    total_stake = sum(d['amount_verified'] for d in delegations)
    if total_stake <= 0:
        return

    pool_fee = reward * POOL_FEE_PCT
    distributable = reward - pool_fee

    event_id = db_add_reward_event(pool_before, pool_after, reward, total_stake, distributable, pool_fee)
    print(f'[REW] Distribui {distributable:.4f} WEBD (fee pool: {pool_fee:.4f}) la {len(delegations)} delegatori', flush=True)

    for d in delegations:
        share = (d['amount_verified'] / total_stake) * distributable
        db_add_payout(event_id, d['address'], share)
        print(f'[REW]   → {d["address"][:20]}... +{share:.4f} WEBD', flush=True)

    # Procesează imediat payout-urile acumulate
    _process_pending_payouts()

def _process_pending_payouts():
    """Consolidate accumulated pending payouts per address and send if >= MIN_PAYOUT."""
    if not HAS_TX_BUILDER:
        print(f'[PAY] tx_builder indisponibil: {_TX_BUILDER_ERR}', flush=True)
        return

    pending = db_get_pending_payouts()
    # Grupare pe adresă
    by_addr: dict[str, float] = {}
    for p in pending:
        by_addr[p['to_address']] = by_addr.get(p['to_address'], 0) + p['amount_webd']

    for addr, total in by_addr.items():
        if total < MIN_PAYOUT:
            print(f'[PAY] {addr[:20]}... acumulat {total:.4f} WEBD < {MIN_PAYOUT} WEBD minim, aștept mai mult', flush=True)
            continue
        try:
            tx = build_signed_tx(
                from_address=POOL_ADDRESS,
                private_key_hex=POOL_PRIVKEY,
                public_key_hex=POOL_PUBKEY,
                to_address=addr,
                amount_webd=round(total, 4),
            )
            result = broadcast_tx(tx['serialized_hex'])
            status = 'sent' if result.get('result') else 'failed'
            db_update_payout_status(addr, 'pending', tx['serialized_hex'], tx['tx_id'], status)
            print(f'[PAY] {addr[:20]}... {total:.4f} WEBD → tx {tx["tx_id"][:16]}... [{status}]', flush=True)
        except Exception as e:
            print(f'[PAY ERROR] {addr[:20]}...: {e}', flush=True)

# ── stats helper ───────────────────────────────────────────────────────────────
def get_stats() -> dict:
    delegations = db_get_active_delegations()
    total_stake = sum(d['amount_verified'] for d in delegations)
    rewards = db_get_recent_rewards(10)
    avg_reward = sum(r['reward_amount'] for r in rewards) / len(rewards) if rewards else 0
    # APY estimate: dacă avem date suficiente
    apy = 0.0
    if avg_reward > 0 and total_stake > 0:
        rewards_per_day = (86400 / REW_INTERVAL) * avg_reward
        apy = round((rewards_per_day * 365 / total_stake) * (1 - POOL_FEE_PCT) * 100, 2)
    return {
        'total_stake': round(total_stake, 4),
        'active_delegators': len(delegations),
        'pool_fee_pct': pool_cfg.get('fee_pct', 10),
        'min_stake_webd': MIN_STAKE,
        'min_payout_webd': MIN_PAYOUT,
        'estimated_apy_pct': apy,
        'pool_address': POOL_ADDRESS,
    }

# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0].rstrip('/')
        params = {}
        if '?' in self.path:
            for part in self.path.split('?', 1)[1].split('&'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    params[k] = v

        if path in ('', '/'):
            if DASHBOARD_HTML.exists():
                html = DASHBOARD_HTML.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self._json({'error': 'dashboard.html lipsă'}, 404)

        elif path == '/api/stats':
            self._json(get_stats())

        elif path == '/api/stake/list':
            self._json(db_get_all_delegations())

        elif path.startswith('/api/stake/'):
            addr = path[len('/api/stake/'):]
            d = db_get_delegation(addr)
            if d:
                self._json(d)
            else:
                self._json({'error': 'adresă negăsită'}, 404)

        elif path == '/api/rewards':
            limit = int(params.get('limit', 20))
            self._json(db_get_recent_rewards(limit))

        elif path.startswith('/api/payouts/'):
            addr = path[len('/api/payouts/'):]
            self._json(db_get_payouts_for_address(addr))

        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = self.path.rstrip('/')

        if path == '/api/stake':
            body = self._read_body()
            address = (body.get('address') or '').strip()
            amount_claimed = float(body.get('amount_claimed', 0) or 0)

            if not address.startswith('WEBD'):
                self._json({'error': 'Adresă WEBD invalidă'}, 400)
                return
            if amount_claimed < MIN_STAKE:
                self._json({'error': f'Stake minim: {MIN_STAKE} WEBD'}, 400)
                return

            # Verificare balanță imediată
            balance = fetch_balance(address)
            if balance is None:
                self._json({'error': 'Nu s-a putut verifica balanța adresei. Verifică nodul.'}, 503)
                return

            amount_verified = min(amount_claimed, balance)
            status = 'active' if balance >= amount_claimed else 'inactive'
            db_upsert_delegation(address, amount_claimed, amount_verified, status)

            self._json({
                'ok': True,
                'address': address,
                'amount_claimed': amount_claimed,
                'amount_verified': amount_verified,
                'balance_current': balance,
                'status': status,
                'message': 'Delegare înregistrată!' if status == 'active'
                           else f'Balanță insuficientă: {balance:.2f} < {amount_claimed:.2f} WEBD. Delegarea va deveni activă când transferi fondurile.',
            })

        elif path == '/api/stake/refresh':
            body = self._read_body()
            address = (body.get('address') or '').strip()
            d = db_get_delegation(address)
            if not d:
                self._json({'error': 'Adresă negăsită'}, 404)
                return
            balance = fetch_balance(address)
            if balance is None:
                self._json({'error': 'Balanța indisponibilă'}, 503)
                return
            amount_verified = min(d['amount_claimed'], balance)
            status = 'active' if balance >= d['amount_claimed'] else 'inactive'
            db_update_delegation_balance(address, amount_verified, status)
            self._json({'ok': True, 'status': status, 'amount_verified': amount_verified, 'balance': balance})

        else:
            self._json({'error': 'not found'}, 404)

# ── main ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not CONFIG_PATH.exists():
        print(f'[ERROR] Config lipsă: {CONFIG_PATH}')
        print('        Copiază config.example.json în config.json și completează.')
        sys.exit(1)

    if not HAS_TX_BUILDER:
        print(f'[WARN] tx_builder.py indisponibil ({_TX_BUILDER_ERR}) — payout-urile automate dezactivate.')
        print('       Instalează: pip3 install cryptography')

    init_db()

    threading.Thread(target=balance_monitor_loop, daemon=True, name='balance-monitor').start()
    threading.Thread(target=reward_monitor_loop, daemon=True, name='reward-monitor').start()

    host = cfg.get('dashboard', {}).get('host', '127.0.0.1')
    port = int(cfg.get('dashboard', {}).get('port', 3004))
    print(f'[WebDollar Staking] Dashboard: http://{host}:{port}', flush=True)
    print(f'[WebDollar Staking] Pool: {POOL_ADDRESS}', flush=True)
    print(f'[WebDollar Staking] Node: {NODE_URL}', flush=True)

    srv = ThreadingHTTPServer((host, port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nOprit.')
