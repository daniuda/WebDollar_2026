#!/usr/bin/env python3
"""
WebDollar Custodial Staking Service — adresă unică.

POOL_ADDRESS minează și primește depozite de la stakeri.
Scannerul de blocuri detectează automat:
  - depozit normal  → from_address = adresă utilizator
  - recompensă bloc → from_address = null/coinbase (de la protocol)

Requires: pip3 install cryptography
"""
import json, os, secrets, sqlite3, sys, threading, time
import urllib.request, urllib.error, ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from tx_builder import build_signed_tx, build_signed_tx_multi, verify_signature, PAYOUT_FEE_PCT
    HAS_TX_BUILDER = True
except ImportError as _e:
    HAS_TX_BUILDER = False
    _TX_BUILDER_ERR = str(_e)
    PAYOUT_FEE_PCT = 0.5

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
CONFIG_PATH    = BASE_DIR / 'config.json'
DB_PATH        = BASE_DIR / 'staking.db'
DASHBOARD_HTML = BASE_DIR / 'dashboard.html'

# ── config ─────────────────────────────────────────────────────────────────────
def load_config():
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return json.load(f)

cfg         = load_config()
pool_cfg    = cfg['pool']
staking_cfg = cfg.get('staking', {})

NODE_URL      = pool_cfg['node_url'].rstrip('/')
BROADCAST_URL = pool_cfg.get('broadcast_url', 'http://localhost:3001/tx/broadcast')
POOL_ADDRESS  = pool_cfg['address']
POOL_PRIVKEY  = pool_cfg['private_key_hex']
POOL_PUBKEY   = pool_cfg['public_key_hex']
POOL_FEE_PCT  = float(pool_cfg.get('fee_pct', 10)) / 100.0

MIN_STAKE     = float(staking_cfg.get('min_stake_webd', 100))
MIN_PAYOUT    = float(staking_cfg.get('min_payout_webd', 10))
SCAN_INTERVAL = int(staking_cfg.get('scan_interval_sec', 30))
HISTORY_DAYS  = int(staking_cfg.get('history_days', 30))
CHALLENGE_TTL = 300

# ── database ───────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _db_lock, _conn() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_address TEXT NOT NULL,
                amount_webd REAL NOT NULL,
                block_height INTEGER NOT NULL,
                tx_id TEXT,
                ts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_balances (
                address TEXT PRIMARY KEY,
                deposited_total REAL NOT NULL DEFAULT 0,
                rewards_total REAL NOT NULL DEFAULT 0,
                rewards_paid REAL NOT NULL DEFAULT 0,
                withdrawn_total REAL NOT NULL DEFAULT 0,
                first_deposit_ts INTEGER,
                last_activity_ts INTEGER
            );
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                amount_webd REAL NOT NULL,
                tx_hex TEXT,
                tx_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                ts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reward_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                block_height INTEGER,
                reward_amount REAL NOT NULL,
                total_stake REAL NOT NULL,
                distributed REAL NOT NULL,
                pool_fee_taken REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS withdrawal_challenges (
                nonce TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                amount REAL NOT NULL,
                expires_ts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scan_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        c.commit()

def _migrate_db():
    migrations = [
        "ALTER TABLE user_balances ADD COLUMN rewards_paid REAL NOT NULL DEFAULT 0",
        "ALTER TABLE reward_events ADD COLUMN block_height INTEGER",
    ]
    with _db_lock, _conn() as c:
        for sql in migrations:
            try:
                c.execute(sql)
                c.commit()
            except Exception:
                pass

# ── DB helpers ─────────────────────────────────────────────────────────────────
def db_get_balance(address: str) -> dict:
    with _db_lock, _conn() as c:
        row = c.execute('SELECT * FROM user_balances WHERE address=?', (address,)).fetchone()
    if not row:
        return {'address': address, 'deposited_total': 0.0, 'rewards_total': 0.0,
                'rewards_paid': 0.0, 'withdrawn_total': 0.0,
                'rewards_pending': 0.0, 'available': 0.0}
    d = dict(row)
    d['rewards_pending'] = round(d['rewards_total'] - d.get('rewards_paid', 0.0), 4)
    d['available']       = round(d['deposited_total'] + d['rewards_total'] - d['withdrawn_total'], 4)
    return d

def db_credit_deposit(address: str, amount: float, height: int, tx_id: str) -> bool:
    now = int(time.time())
    with _db_lock, _conn() as c:
        if tx_id and c.execute('SELECT 1 FROM deposits WHERE tx_id=?', (tx_id,)).fetchone():
            return False
        c.execute('INSERT INTO deposits (from_address,amount_webd,block_height,tx_id,ts) VALUES (?,?,?,?,?)',
                  (address, amount, height, tx_id, now))
        c.execute('''
            INSERT INTO user_balances (address,deposited_total,first_deposit_ts,last_activity_ts)
            VALUES (?,?,?,?)
            ON CONFLICT(address) DO UPDATE SET
                deposited_total  = deposited_total + excluded.deposited_total,
                last_activity_ts = excluded.last_activity_ts
        ''', (address, amount, now, now))
        c.commit()
    print(f'[DEP] +{amount:.4f} WEBD de la {address[:20]}... (bloc #{height})', flush=True)
    return True

def db_credit_reward(address: str, amount: float):
    now = int(time.time())
    with _db_lock, _conn() as c:
        c.execute('''
            INSERT INTO user_balances (address,rewards_total,last_activity_ts)
            VALUES (?,?,?)
            ON CONFLICT(address) DO UPDATE SET
                rewards_total    = rewards_total + excluded.rewards_total,
                last_activity_ts = excluded.last_activity_ts
        ''', (address, amount, now))
        c.commit()

def db_mark_rewards_paid(address: str, amount: float):
    with _db_lock, _conn() as c:
        c.execute('''UPDATE user_balances
                     SET rewards_paid    = rewards_paid + ?,
                         withdrawn_total = withdrawn_total + ?,
                         last_activity_ts = ?
                     WHERE address = ?''', (amount, amount, int(time.time()), address))
        c.commit()

def db_add_withdrawal(address: str, amount: float, tx_hex=None, tx_id=None, status='pending') -> int:
    with _db_lock, _conn() as c:
        cur = c.execute(
            'INSERT INTO withdrawals (address,amount_webd,tx_hex,tx_id,status,ts) VALUES (?,?,?,?,?,?)',
            (address, amount, tx_hex, tx_id, status, int(time.time())))
        wid = cur.lastrowid
        c.execute('UPDATE user_balances SET withdrawn_total=withdrawn_total+?,last_activity_ts=? WHERE address=?',
                  (amount, int(time.time()), address))
        c.commit()
    return wid

def db_get_all_stakers() -> list:
    with _db_lock, _conn() as c:
        rows = c.execute(
            'SELECT address, deposited_total, rewards_total,'
            ' COALESCE(rewards_paid,0) as rewards_paid, withdrawn_total, last_activity_ts'
            ' FROM user_balances WHERE deposited_total > 0 ORDER BY deposited_total DESC'
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['rewards_pending'] = round(d['rewards_total'] - d['rewards_paid'], 4)
        d['available']       = round(d['deposited_total'] + d['rewards_total'] - d['withdrawn_total'], 4)
        result.append(d)
    return result

def db_get_deposits(address: str) -> list:
    with _db_lock, _conn() as c:
        rows = c.execute('SELECT * FROM deposits WHERE from_address=? ORDER BY ts DESC LIMIT 50', (address,)).fetchall()
    return [dict(r) for r in rows]

def db_get_withdrawals(address: str) -> list:
    with _db_lock, _conn() as c:
        rows = c.execute('SELECT * FROM withdrawals WHERE address=? ORDER BY ts DESC LIMIT 50', (address,)).fetchall()
    return [dict(r) for r in rows]

def db_get_recent_rewards(limit=20) -> list:
    with _db_lock, _conn() as c:
        rows = c.execute('SELECT * FROM reward_events ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
    return [dict(r) for r in rows]

def db_add_reward_event(height, reward, total_stake, distributed, fee_taken):
    with _db_lock, _conn() as c:
        c.execute(
            'INSERT INTO reward_events (ts,block_height,reward_amount,total_stake,distributed,pool_fee_taken)'
            ' VALUES (?,?,?,?,?,?)',
            (int(time.time()), height, reward, total_stake, distributed, fee_taken))
        c.commit()

def db_reward_event_exists(height: int) -> bool:
    with _db_lock, _conn() as c:
        return bool(c.execute('SELECT 1 FROM reward_events WHERE block_height=?', (height,)).fetchone())

def db_get_scan_height() -> int:
    with _db_lock, _conn() as c:
        row = c.execute("SELECT value FROM scan_state WHERE key='last_height'").fetchone()
    return int(row['value']) if row else -1

def db_set_scan_height(h: int):
    with _db_lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO scan_state (key,value) VALUES ('last_height',?)", (str(h),))
        c.commit()

def db_save_challenge(nonce: str, address: str, amount: float) -> int:
    exp = int(time.time()) + CHALLENGE_TTL
    with _db_lock, _conn() as c:
        c.execute('INSERT OR REPLACE INTO withdrawal_challenges (nonce,address,amount,expires_ts) VALUES (?,?,?,?)',
                  (nonce, address, amount, exp))
        c.execute('DELETE FROM withdrawal_challenges WHERE expires_ts < ?', (int(time.time()),))
        c.commit()
    return exp

def db_consume_challenge(nonce: str, address: str, amount: float) -> bool:
    now = int(time.time())
    with _db_lock, _conn() as c:
        row = c.execute(
            'SELECT * FROM withdrawal_challenges WHERE nonce=? AND address=? AND expires_ts>?',
            (nonce, address, now)).fetchone()
        if not row or abs(float(row['amount']) - amount) > 0.001:
            return False
        c.execute('DELETE FROM withdrawal_challenges WHERE nonce=?', (nonce,))
        c.commit()
    return True

def db_prune():
    cutoff = int(time.time()) - HISTORY_DAYS * 86400
    with _db_lock, _conn() as c:
        c.execute('DELETE FROM reward_events WHERE ts < ?', (cutoff,))
        c.commit()

# ── HTTP helpers ───────────────────────────────────────────────────────────────
_insecure_ctx = ssl.create_default_context()
_insecure_ctx.check_hostname = False
_insecure_ctx.verify_mode    = ssl.CERT_NONE

def _get_json(url: str, timeout=8):
    req = urllib.request.Request(url, headers={'Accept': 'application/json',
                                               'User-Agent': 'webd-staking/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except ssl.SSLError:
        with urllib.request.urlopen(req, timeout=timeout, context=_insecure_ctx) as r:
            return json.loads(r.read().decode('utf-8'))

def _post_json(url: str, data: dict, timeout=10):
    body = json.dumps(data).encode('utf-8')
    req  = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except ssl.SSLError:
        with urllib.request.urlopen(req, timeout=timeout, context=_insecure_ctx) as r:
            return json.loads(r.read().decode('utf-8'))

def fetch_height() -> int:
    data = _get_json(f'{NODE_URL}/height')
    return int(data.get('height', data) if isinstance(data, dict) else data)

def fetch_block(height: int) -> dict:
    data = _get_json(f'{NODE_URL}/block/{height}')
    return data if isinstance(data, dict) else {}

def parse_tx_amount(tx: dict) -> float:
    raw = (tx.get('amount') or (tx.get('to') or {}).get('amount') or tx.get('value') or 0)
    try:
        v = float(raw)
        return v / 10_000 if v > 1_000_000 else v
    except Exception:
        return 0.0

def broadcast_tx(tx_hex: str) -> dict:
    try:
        return _post_json(BROADCAST_URL, {'hex': tx_hex})
    except Exception as e:
        return {'result': False, 'error': str(e)}

# ── Block scanner — detectează depozite ȘI recompense de bloc ─────────────────
# Adrese coinbase cunoscute (recompensă de protocol, nu transfer normal)
_COINBASE = {'', 'null', 'none', '0', 'coinbase', 'genesis', 'reward'}

def _is_coinbase(addr: str) -> bool:
    if not addr:
        return True
    a = addr.lower().strip()
    return a in _COINBASE or a.startswith('0x000')

def block_scan_loop():
    if db_get_scan_height() < 0:
        try:
            h = max(0, fetch_height() - 10)
            db_set_scan_height(h)
        except Exception:
            pass

    while True:
        try:
            current = fetch_height()
            last    = db_get_scan_height()
            if current > last:
                for h in range(last + 1, current + 1):
                    _scan_block(h)
                db_set_scan_height(current)
        except Exception as e:
            print(f'[SCAN ERROR] {e}', flush=True)
        time.sleep(SCAN_INTERVAL)

def _scan_block(height: int):
    try:
        block = fetch_block(height)
    except Exception:
        return

    reward_found = False

    # Verifică câmpuri explicite de recompensă din structura blocului
    miner = (block.get('miner') or block.get('minerAddress') or
             block.get('minedBy') or '').strip()
    if miner == POOL_ADDRESS:
        for key in ('reward', 'mining_reward', 'blockReward', 'coinbase', 'miningReward'):
            v = block.get(key)
            if v:
                try:
                    amt = float(v)
                    amt = amt / 10_000 if amt > 1_000_000 else amt
                    if amt > 0:
                        _handle_block_reward(amt, height)
                        reward_found = True
                except Exception:
                    pass
                break

    # Scanează tranzacțiile blocului
    txs = block.get('transactions') or block.get('txs') or []
    for tx in txs:
        to_addr = ((tx.get('to') or {}).get('address') or
                   tx.get('toAddress') or tx.get('recipient') or '')
        if to_addr != POOL_ADDRESS:
            continue

        from_addr = ((tx.get('from') or {}).get('address') or
                     tx.get('fromAddress') or tx.get('sender') or '')
        amount = parse_tx_amount(tx)
        tx_id  = tx.get('id') or tx.get('txId') or tx.get('hash') or f'block-{height}'

        if _is_coinbase(from_addr):
            # Recompensă de bloc primită de pool
            if amount > 0 and not reward_found:
                _handle_block_reward(amount, height)
                reward_found = True
        elif amount >= MIN_STAKE:
            # Depozit de la un staker
            db_credit_deposit(from_addr, amount, height, tx_id)

# ── Reward distribution ────────────────────────────────────────────────────────
def _handle_block_reward(amount: float, height: int):
    if db_reward_event_exists(height):
        return  # deja procesat
    print(f'[REW] Bloc #{height}: +{amount:.4f} WEBD recompensă', flush=True)
    _distribute_reward(amount, height)

def _distribute_reward(reward: float, height: int = None):
    stakers = db_get_all_stakers()
    active  = [s for s in stakers if s['available'] > 0]
    if not active:
        return
    total_stake = sum(s['available'] for s in active)
    if total_stake <= 0:
        return

    fee_taken     = reward * POOL_FEE_PCT
    distributable = reward - fee_taken
    db_add_reward_event(height, reward, total_stake, distributable, fee_taken)

    shares = {}
    for s in active:
        share = round((s['available'] / total_stake) * distributable, 6)
        if share >= 0.0001:
            db_credit_reward(s['address'], share)
            shares[s['address']] = share

    print(f'[REW] Distribuit {distributable:.4f} WEBD la {len(active)} stakers '
          f'(fee pool {fee_taken:.4f} WEBD)', flush=True)

    if HAS_TX_BUILDER and shares:
        _auto_payout(shares)

    db_prune()

def _auto_payout(new_shares: dict):
    """
    O singură tranzacție multi-output pentru toți stakerii cu recompense >= MIN_PAYOUT.
    Taxa = 0.5% din total (o singură taxă împărțită la toți).
    """
    eligible = []
    for address in new_shares:
        bal     = db_get_balance(address)
        pending = bal['rewards_pending']
        if pending >= MIN_PAYOUT:
            eligible.append({'address': address, 'amount_webd': round(pending, 4)})

    if not eligible:
        return

    total = sum(o['amount_webd'] for o in eligible)
    try:
        tx = build_signed_tx_multi(
            from_address=POOL_ADDRESS,
            private_key_hex=POOL_PRIVKEY,
            public_key_hex=POOL_PUBKEY,
            outputs=eligible,
            fee_pct=PAYOUT_FEE_PCT,
        )
        result = broadcast_tx(tx['serialized_hex'])
        status = 'sent' if result.get('result') else 'failed'
        for o in eligible:
            if status == 'sent':
                db_mark_rewards_paid(o['address'], o['amount_webd'])
            db_add_withdrawal(o['address'], o['amount_webd'], tx['serialized_hex'], tx['tx_id'], status)
        pct_eff = tx['fee_webd'] / total * 100 if total > 0 else 0
        print(f'[PAY] {len(eligible)} stakers, {total:.4f} WEBD, '
              f'fee {tx["fee_webd"]:.4f} WEBD ({pct_eff:.2f}%), status={status}', flush=True)
    except Exception as e:
        print(f'[PAY ERROR] {e}', flush=True)

# ── Withdrawal (manual, la cerere) ────────────────────────────────────────────
def process_withdrawal(address: str, amount: float, pubkey_hex: str,
                       nonce: str, sig_hex: str) -> dict:
    if not HAS_TX_BUILDER:
        return {'error': f'tx_builder indisponibil: {_TX_BUILDER_ERR}'}

    if not db_consume_challenge(nonce, address, amount):
        return {'error': 'Challenge invalid sau expirat. Generează unul nou.'}

    message = f'withdraw:{address}:{amount:.4f}:{nonce}'.encode('utf-8')
    if not verify_signature(pubkey_hex, message, sig_hex):
        return {'error': 'Semnătură invalidă. Verifică că ai importat wallet-ul corect.'}

    bal = db_get_balance(address)
    if bal['available'] < amount:
        return {'error': f'Fonduri insuficiente: disponibil {bal["available"]:.4f} WEBD, cerut {amount:.4f}'}

    try:
        tx = build_signed_tx(
            from_address=POOL_ADDRESS,
            private_key_hex=POOL_PRIVKEY,
            public_key_hex=POOL_PUBKEY,
            to_address=address,
            amount_webd=round(amount, 4),
        )
        result = broadcast_tx(tx['serialized_hex'])
        status = 'sent' if result.get('result') else 'failed'
        db_add_withdrawal(address, amount, tx['serialized_hex'], tx['tx_id'], status)
        if status == 'sent':
            return {'ok': True, 'tx_id': tx['tx_id'], 'amount': amount}
        return {'error': f'Broadcast eșuat: {result.get("error", "necunoscut")}'}
    except Exception as e:
        return {'error': str(e)}

# ── Stats ──────────────────────────────────────────────────────────────────────
def get_stats() -> dict:
    stakers      = db_get_all_stakers()
    total_staked = sum(s['available'] for s in stakers)
    rewards      = db_get_recent_rewards(10)
    avg_reward   = sum(r['reward_amount'] for r in rewards) / len(rewards) if rewards else 0
    apy = 0.0
    if avg_reward > 0 and total_staked > 0:
        blocks_per_day = 86400 / max(SCAN_INTERVAL, 30)
        daily = blocks_per_day * avg_reward * (1 - POOL_FEE_PCT)
        apy   = round(daily * 365 / total_staked * 100, 2)
    return {
        'pool_address':      POOL_ADDRESS,
        'staking_address':   POOL_ADDRESS,   # alias pentru dashboard
        'total_staked':      round(total_staked, 4),
        'active_stakers':    len([s for s in stakers if s['available'] > 0]),
        'pool_fee_pct':      pool_cfg.get('fee_pct', 10),
        'payout_fee_pct':    PAYOUT_FEE_PCT,
        'min_stake_webd':    MIN_STAKE,
        'min_payout_webd':   MIN_PAYOUT,
        'estimated_apy_pct': apy,
    }

# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data, status=200):
        body = json.dumps(data, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path   = self.path.split('?')[0].rstrip('/')
        params = {}
        if '?' in self.path:
            for p in self.path.split('?', 1)[1].split('&'):
                if '=' in p:
                    k, v = p.split('=', 1)
                    params[k] = urllib.parse.unquote_plus(v) if hasattr(urllib, 'parse') else v

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

        elif path == '/api/stakers':
            self._json(db_get_all_stakers())

        elif path == '/api/rewards':
            self._json(db_get_recent_rewards(int(params.get('limit', 20))))

        elif path.startswith('/api/balance/'):
            self._json(db_get_balance(path[len('/api/balance/'):]))

        elif path.startswith('/api/deposits/'):
            self._json(db_get_deposits(path[len('/api/deposits/'):]))

        elif path.startswith('/api/withdrawals/'):
            self._json(db_get_withdrawals(path[len('/api/withdrawals/'):]))

        elif path == '/api/withdraw/challenge':
            addr   = params.get('address', '').strip()
            amount = float(params.get('amount', 0) or 0)
            if not addr or amount <= 0:
                self._json({'error': 'address și amount sunt obligatorii'}, 400)
                return
            nonce   = secrets.token_hex(16)
            exp_ts  = db_save_challenge(nonce, addr, amount)
            message = f'withdraw:{addr}:{amount:.4f}:{nonce}'
            self._json({'nonce': nonce, 'message': message, 'expires_ts': exp_ts})

        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = self.path.rstrip('/')
        if path == '/api/withdraw':
            body       = self._body()
            address    = (body.get('address') or '').strip()
            amount     = float(body.get('amount', 0) or 0)
            pubkey_hex = (body.get('pubkey_hex') or '').strip()
            nonce      = (body.get('nonce') or '').strip()
            sig_hex    = (body.get('signature_hex') or '').strip()

            for field, val in [('address', address), ('pubkey_hex', pubkey_hex),
                                ('nonce', nonce), ('signature_hex', sig_hex)]:
                if not val:
                    self._json({'error': f'Câmpul {field} lipsește'}, 400)
                    return
            if amount <= 0:
                self._json({'error': 'amount trebuie > 0'}, 400)
                return

            result = process_withdrawal(address, amount, pubkey_hex, nonce, sig_hex)
            self._json(result, 200 if result.get('ok') else 400)
        else:
            self._json({'error': 'not found'}, 404)

# ── main ───────────────────────────────────────────────────────────────────────
import urllib.parse

if __name__ == '__main__':
    if not CONFIG_PATH.exists():
        print(f'[ERROR] Config lipsă: {CONFIG_PATH}')
        print('        cp config.example.json config.json  și completează valorile.')
        sys.exit(1)

    if not HAS_TX_BUILDER:
        print(f'[WARN] tx_builder indisponibil — retrageri dezactivate. pip3 install cryptography')

    init_db()
    _migrate_db()

    threading.Thread(target=block_scan_loop, daemon=True, name='block-scan').start()

    host = cfg.get('dashboard', {}).get('host', '127.0.0.1')
    port = int(cfg.get('dashboard', {}).get('port', 3004))
    print(f'[WebDollar Staking] http://{host}:{port}', flush=True)
    print(f'[WebDollar Staking] Pool address: {POOL_ADDRESS}', flush=True)
    print(f'[WebDollar Staking] Payout fee: {PAYOUT_FEE_PCT}% din total distribuit', flush=True)

    srv = ThreadingHTTPServer((host, port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nOprit.')
