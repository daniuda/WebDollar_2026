#!/usr/bin/env python3
"""
WebDollar Custodial Staking Service — adresă unică.

POOL_ADDRESS minează și primește depozite de la stakeri.
Scannerul de blocuri detectează automat:
  - depozit normal  → from_address = adresă utilizator
  - recompensă bloc → from_address = null/coinbase (de la protocol)

Requires: pip3 install cryptography
"""
import json, os, secrets, shutil, sqlite3, sys, threading, time
import urllib.request, urllib.error, urllib.parse, ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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

def _decode_pool_addr_hex(wif):
    import base64
    norm = wif.strip().replace('$', '/').replace('#', 'O').replace('@', 'l')
    pad = len(norm) % 4
    if pad:
        norm += '=' * (4 - pad)
    raw = base64.b64decode(norm)
    return raw[5:25].hex() if len(raw) >= 25 else ''

POOL_UNENCODED_HEX = _decode_pool_addr_hex(POOL_ADDRESS)
POOL_FEE_PCT  = float(pool_cfg.get('fee_pct', 10)) / 100.0
NODE_LOCAL_URL  = pool_cfg.get('node_local_url', 'http://127.0.0.1:8081')
NODE_SECRET_KEY = pool_cfg.get('node_secret', 'SECRET_SECRET_SECRET_LONG_SECRET_123456')

MIN_STAKE     = float(staking_cfg.get('min_stake_webd', 100))
MIN_PAYOUT    = float(staking_cfg.get('min_payout_webd', 10))
SCAN_INTERVAL    = int(staking_cfg.get('scan_interval_sec', 30))
HISTORY_DAYS     = int(staking_cfg.get('history_days', 30))
BACKUP_INTERVAL  = int(staking_cfg.get('backup_interval_sec', 3600))   # backup la fiecare oră
BACKUP_KEEP      = int(staking_cfg.get('backup_keep', 168))             # păstrează 7 zile × 24h
BACKUP_DIR       = BASE_DIR / 'backups'
CHALLENGE_TTL    = 300

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
def _addr_variants(address: str):
    """In WebDollar WIF, '#' si 'O' sunt echivalente (acelasi caracter base64).
    Intoarce toate formele posibile ale adresei pentru lookup in DB."""
    variants = [address]
    if '#' in address:
        variants.append(address.replace('#', 'O'))
    if 'O' in address:
        variants.append(address.replace('O', '#'))
    return variants

def db_get_balance(address: str) -> dict:
    with _db_lock, _conn() as c:
        row = None
        for addr in _addr_variants(address):
            row = c.execute('SELECT * FROM user_balances WHERE address=?', (addr,)).fetchone()
            if row:
                break
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

def db_export_ledger() -> dict:
    """Export complet al ledger-ului — folosit pentru backup și audit."""
    now = int(time.time())
    with _db_lock, _conn() as c:
        stakers    = [dict(r) for r in c.execute(
            'SELECT * FROM user_balances ORDER BY deposited_total DESC').fetchall()]
        deposits   = [dict(r) for r in c.execute(
            'SELECT * FROM deposits ORDER BY ts DESC').fetchall()]
        withdrawals = [dict(r) for r in c.execute(
            'SELECT * FROM withdrawals ORDER BY ts DESC').fetchall()]
        rewards    = [dict(r) for r in c.execute(
            'SELECT * FROM reward_events ORDER BY ts DESC').fetchall()]
        scan_h     = c.execute("SELECT value FROM scan_state WHERE key='last_height'").fetchone()

    total_deposited  = sum(s.get('deposited_total', 0) for s in stakers)
    total_rewards    = sum(s.get('rewards_total', 0) for s in stakers)
    total_withdrawn  = sum(s.get('withdrawn_total', 0) for s in stakers)
    total_owed       = sum(
        s.get('deposited_total', 0) + s.get('rewards_total', 0) - s.get('withdrawn_total', 0)
        for s in stakers)

    for s in stakers:
        s['available'] = round(
            s.get('deposited_total', 0) + s.get('rewards_total', 0) - s.get('withdrawn_total', 0), 4)
        s['rewards_pending'] = round(
            s.get('rewards_total', 0) - s.get('rewards_paid', 0), 4)

    return {
        'generated_at':      now,
        'generated_at_iso':  time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
        'pool_address':      POOL_ADDRESS,
        'last_scanned_height': int(scan_h['value']) if scan_h else 0,
        'summary': {
            'total_stakers':    len(stakers),
            'total_deposited':  round(total_deposited, 4),
            'total_rewards':    round(total_rewards, 4),
            'total_withdrawn':  round(total_withdrawn, 4),
            'total_owed':       round(total_owed, 4),
            'reward_events':    len(rewards),
        },
        'stakers':     stakers,
        'deposits':    deposits,
        'withdrawals': withdrawals,
        'reward_events': rewards,
    }

# ── Backup loop ────────────────────────────────────────────────────────────────
def backup_loop():
    """Backup automat al DB-ului la fiecare BACKUP_INTERVAL secunde."""
    BACKUP_DIR.mkdir(exist_ok=True)
    # Backup imediat la pornire
    _do_backup()
    while True:
        time.sleep(BACKUP_INTERVAL)
        _do_backup()

def _do_backup():
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        ts  = time.strftime('%Y%m%d_%H%M%S', time.gmtime())
        dst = BACKUP_DIR / f'staking_{ts}.db'
        with _db_lock:
            shutil.copy2(str(DB_PATH), str(dst))

        # Export JSON paralel pentru lizibilitate
        json_dst = BACKUP_DIR / f'ledger_{ts}.json'
        ledger   = db_export_ledger()
        json_dst.write_text(json.dumps(ledger, indent=2, default=str), encoding='utf-8')

        # Rotire: șterge backup-uri vechi (păstrează ultimele BACKUP_KEEP)
        dbs   = sorted(BACKUP_DIR.glob('staking_*.db'))
        jsons = sorted(BACKUP_DIR.glob('ledger_*.json'))
        for old in dbs[:-BACKUP_KEEP]:
            old.unlink(missing_ok=True)
        for old in jsons[:-BACKUP_KEEP]:
            old.unlink(missing_ok=True)

        print(f'[BCK] Backup: {dst.name} | stakers={ledger["summary"]["total_stakers"]}'
              f' owed={ledger["summary"]["total_owed"]:.2f} WEBD', flush=True)
    except Exception as e:
        print(f'[BCK ERROR] {e}', flush=True)

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
    try:
        data = _get_json(NODE_URL + '/chain')
        return int(data['height'])
    except Exception:
        data = _get_json(NODE_URL + '/height')
        return int(data.get('height', data) if isinstance(data, dict) else data)

def _norm_tx(tx: dict) -> dict:
    """Normalizeaza tx din format explorator (from/to ca liste) la format flat."""
    result = dict(tx)
    for field in ('from', 'to'):
        v = tx.get(field)
        if isinstance(v, list) and v:
            result[field] = v[0]  # primul element din lista
        elif not isinstance(v, dict):
            result[field] = {}
    return result

def fetch_block(height: int) -> dict:
    data = _get_json(NODE_URL + '/block/' + str(height))
    if not isinstance(data, dict):
        return {}
    inner = data.get('data', {})
    if isinstance(inner, dict) and 'data' in inner:
        block_data = inner.get('data', {})
        raw_txs = block_data.get('transactions') or []
        return {
            'height':       data.get('height', height),
            'hash':         data.get('hash', ''),
            'minerAddress': block_data.get('minerAddress', '') or block_data.get('posMinerAddress', ''),
            'reward':       inner.get('reward', 0),
            'transactions': [_norm_tx(t) for t in raw_txs if isinstance(t, dict)],
        }
    return data

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

# Socket.io node URLs to try for direct broadcast (socket.io v2 protocol)
_SIO_NODES = [
    NODE_LOCAL_URL,                     # VPS local: http://127.0.0.1:8081
    'http://daniuda.ddns.net:8080',     # pool acasă, conectat la rețeaua principală
]

def _check_tx_in_pending(tx_id: str, node_url: str) -> bool:
    """Verifică dacă tx_id este în coada pending a nodului."""
    try:
        base = node_url.rstrip('/')
        data = _get_json(f'{base}/transactions/pending', timeout=5)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    tid = item.get('id') or item.get('txId') or item.get('hash') or ''
                else:
                    tid = str(item)
                if tid and tx_id.lower() in tid.lower():
                    return True
        elif isinstance(data, dict):
            for key in ('transactions', 'pending', 'list'):
                lst = data.get(key, [])
                if isinstance(lst, list):
                    for item in lst:
                        tid = (item.get('id') or item.get('txId') or item.get('hash') or ''
                               if isinstance(item, dict) else str(item))
                        if tid and tx_id.lower() in tid.lower():
                            return True
    except Exception:
        pass
    return False


def _socketio_broadcast_tx(tx_hex: str, tx_id: str = '') -> dict:
    """
    Broadcast tx direct la un nod Node-WebDollar via socket.io v2.
    Replica exact Windows miner (legacyPool.ts NodeTxBroadcaster):
    - nodeConsensusType=1 (SERVER), fara UTC
    - Asteapta HelloNode de la server INAINTE de a emite tx
    - Trimite {buffer: <bytes>} ca binary attachment (nu JSON Buffer)
    - Ramane conectat 8s pentru ca nodul sa valideze tx inainte de disconnect
    """
    try:
        import socketio as _sio_lib
    except ImportError:
        return {'result': False, 'error': 'python-socketio indisponibil'}

    import uuid as _uuid_mod

    tx_bytes = bytes.fromhex(tx_hex)

    for node_url in _SIO_NODES:
        result = {'done': False, 'error': None}
        ready_ev   = threading.Event()
        pending_ev = threading.Event()  # confirmă că nodul a acceptat tx în pending queue

        sio = _sio_lib.Client(logger=False, engineio_logger=False, reconnection=False)

        sio_log = []

        @sio.event
        def connect():
            sio_log.append(f'[SIO] Conectat la {node_url}, astept HelloNode...')
            print(f'[SIO] Conectat la {node_url}, astept HelloNode...', flush=True)

        @sio.on('HelloNode')
        def on_hello_node(data):
            try:
                sio.emit('transactions/new-pending-transaction', {'buffer': tx_bytes})
                result['done'] = True
                sio_log.append(f'[SIO] HelloNode primit, tx {len(tx_bytes)} bytes trimis -> {node_url}')
                print(f'[SIO] HelloNode primit, tx {len(tx_bytes)} bytes trimis -> {node_url}', flush=True)
            except Exception as exc:
                result['error'] = str(exc)
                sio_log.append(f'[SIO] Eroare emit: {exc}')
                print(f'[SIO] Eroare emit dupa HelloNode: {exc}', flush=True)
            # Ramane conectat 8s (nu 1.5s) pentru ca validarea sa se termine
            threading.Timer(8.0, ready_ev.set).start()

        @sio.on('transactions/new-pending-transaction-id')
        def on_tx_propagated(data):
            # Nodul a acceptat tx si il propaga la peers → tx este in pending queue
            pending_ev.set()
            sio_log.append(f'[SIO] TX confirmat in pending pool de nod!')
            print(f'[SIO] TX confirmat in pending pool!', flush=True)
            ready_ev.set()  # nu mai trebuie sa asteptam

        @sio.event
        def connect_error(data):
            result['error'] = str(data)
            ready_ev.set()

        @sio.event
        def disconnect():
            # Nu seta ready_ev la disconnect — am putea fi deconectati inainte de validare
            pass

        q = {
            'msg': 'HelloNode',
            'version': '1.3.24',
            'uuid': str(_uuid_mod.uuid4()),
            'nodeType': '0',          # NODE_WEB_PEER (browser)
            'nodeConsensusType': '1', # SERVER — identic cu Windows miner buildQuery()
            'domain': 'browser',
        }
        qs = '&'.join(f'{k}={v}' for k, v in q.items())
        try:
            sio.connect(f'{node_url}?{qs}', transports=['websocket', 'polling'])
            ready_ev.wait(timeout=20)
        except Exception as exc:
            result['error'] = str(exc)
        finally:
            try: sio.disconnect()
            except Exception: pass

        if result['done']:
            in_pending = pending_ev.is_set()
            if not in_pending and tx_id:
                # Verifică direct prin HTTP dacă tx e în pending queue
                in_pending = _check_tx_in_pending(tx_id, node_url)
                if in_pending:
                    sio_log.append('[SIO] TX confirmat in pending queue via HTTP')
            status_msg = '✓ in pending queue' if in_pending else '? neconfirmat (nod validează async)'
            sio_log.append(f'[SIO] Status: {status_msg}')
            return {
                'result': True,
                'node': node_url,
                'bytes': len(tx_bytes),
                'in_pending': in_pending,
                'log': sio_log,
            }
        sio_log.append(f'[SIO] {node_url} esuat: {result["error"]}')
        print(f'[SIO] {node_url} eșuat: {result["error"]}', flush=True)

    return {'result': False, 'error': 'Toate nodurile socket.io indisponibile', 'log': sio_log}

def _wif_to_unencoded_hex(wif: str) -> str:
    """
    Converteste WebDollar WIF (WEBD$...) la cei 20 bytes raw ai adresei (hex).
    Structura WIF: PREFIX(4) + VERSION(1) + ADDRESS(20) + CHECKSUM(4) + SUFFIX(1) = 30 bytes
    Encoding: base64 cu $→/ #→O @→l
    Returneaza hex string de 40 chars sau '' daca esueaza.
    """
    import base64
    if not wif.startswith('WEBD$'):
        return ''
    try:
        norm = ''
        for c in wif:
            if c == '#':  norm += 'O'
            elif c == '@': norm += 'l'
            elif c == '$': norm += '/'
            else:          norm += c
        raw = base64.b64decode(norm)
        if len(raw) != 30:
            return ''
        return raw[5:25].hex()
    except Exception:
        return ''


def fetch_nonce_and_timelock(from_address: str = None) -> tuple:
    """
    Returnează (nonce, time_lock) din nodul local — identic cu Windows miner.
    nonce   = GET /address/nonce/{address} → .nonce
    timeLock = GET /top → .top - 1
    """
    if from_address is None:
        from_address = POOL_ADDRESS
    try:
        addr_enc = urllib.parse.quote(from_address, safe='')
        nonce_data = _get_json(f'{NODE_LOCAL_URL}/address/nonce/{addr_enc}', timeout=5)
        nonce = int(nonce_data.get('nonce', 0))
    except Exception:
        nonce = 0
    try:
        top_data = _get_json(f'{NODE_LOCAL_URL}/top', timeout=5)
        top = int(top_data.get('top', 0))
        time_lock = max(0, top - 1)
    except Exception:
        time_lock = 0
    return nonce, time_lock


def _node_create_transaction(to_address: str, amount_webd: float) -> dict:
    """
    Creare + propagare tx prin API-ul secret al nodului principal.
    - from: WIF URL-encoded (nodul il cauta in wallet)
    - to:   20-byte hex (unencodedAddress) — daca pasam WIF direct, nodul da timeout
            incercand sa obtina publicKey din string in loc de Buffer
    """
    to_hex = _wif_to_unencoded_hex(to_address)
    if not to_hex:
        return {'result': False, 'error': f'Nu pot converti adresa to la hex: {to_address[:30]}'}

    from_enc = urllib.parse.quote(POOL_ADDRESS, safe='')
    url = (f'{NODE_LOCAL_URL}/{NODE_SECRET_KEY}/wallets/create-transaction'
           f'/{from_enc}/{to_hex}/{amount_webd:.4f}/0')
    return _get_json(url, timeout=35)

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
    if miner in (POOL_ADDRESS, POOL_UNENCODED_HEX):
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
        nonce, time_lock = fetch_nonce_and_timelock(POOL_ADDRESS)
        tx = build_signed_tx_multi(
            from_address=POOL_ADDRESS,
            private_key_hex=POOL_PRIVKEY,
            public_key_hex=POOL_PUBKEY,
            outputs=eligible,
            fee_pct=PAYOUT_FEE_PCT,
            nonce=nonce,
            time_lock=time_lock,
        )
        # Încearcă socket.io (primar), fallback la webd-node-modern
        sio_res = _socketio_broadcast_tx(tx['serialized_hex'], tx_id=tx['tx_id'])
        if sio_res.get('result'):
            result_ok = True
            method = f'sio:{sio_res.get("node","?")}'
        else:
            rest_res = broadcast_tx(tx['serialized_hex'])
            result_ok = bool(rest_res.get('result'))
            method = f'rest(peers={rest_res.get("peers_notified",0)})'
        status = 'sent' if result_ok else 'failed'
        for o in eligible:
            if status == 'sent':
                db_mark_rewards_paid(o['address'], o['amount_webd'])
            db_add_withdrawal(o['address'], o['amount_webd'], tx['serialized_hex'], tx['tx_id'], status)
        pct_eff = tx['fee_webd'] / total * 100 if total > 0 else 0
        print(f'[PAY] {len(eligible)} stakers, {total:.4f} WEBD, '
              f'fee {tx["fee_webd"]:.4f} WEBD ({pct_eff:.2f}%), status={status} via {method}', flush=True)
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

    log = []

    # Metoda 1: tx_builder + broadcast socket.io direct la nodul legacy (primar, cel mai fiabil)
    # wallets/create-transaction pe nod dă timeout >35s datorită SemaphoreProcessing PoS mining
    tx = None
    try:
        nonce, time_lock = fetch_nonce_and_timelock(POOL_ADDRESS)
        from tx_builder import compute_version as _cv, get_public_key_from_seed as _gpk
        ver = _cv(time_lock)
        try:
            derived_pub = _gpk(POOL_PRIVKEY)
            log.append(f'[WIT] pubKey derivat: {derived_pub.hex()}')
            if derived_pub.hex() != POOL_PUBKEY:
                log.append(f'[WIT] ⚠ pubKey în config diferit! config={POOL_PUBKEY[:20]}...')
        except Exception as _pe:
            log.append(f'[WIT] Nu pot deriva pubKey: {_pe}')
        log.append(f'[WIT] nonce={nonce}  timeLock={time_lock}  version=0x{ver:02x}')
        print(f'[WIT] nonce={nonce} timeLock={time_lock}', flush=True)
        tx = build_signed_tx(
            from_address=POOL_ADDRESS,
            private_key_hex=POOL_PRIVKEY,
            public_key_hex=POOL_PUBKEY,
            to_address=address,
            amount_webd=round(amount, 4),
            nonce=nonce,
            time_lock=time_lock,
        )
        log.append(f'[WIT] TxID: {tx["tx_id"]}')
        log.append(f'[WIT] Tx: {len(bytes.fromhex(tx["serialized_hex"]))} bytes')
        sio_res = _socketio_broadcast_tx(tx['serialized_hex'], tx_id=tx['tx_id'])
        for l in sio_res.get('log', []):
            log.append(l)
        if sio_res.get('result'):
            status = 'sent'
            db_add_withdrawal(address, amount, tx['serialized_hex'], tx['tx_id'], status)
            in_p = sio_res.get('in_pending', False)
            log.append(f'[WIT] ✓ Tx trimis — {"in pending pool" if in_p else "validare in curs pe nod"}')
            print(f'[WIT sio] {amount:.4f} WEBD -> {address[:20]}... tx={tx["tx_id"][:16]} pending={in_p}', flush=True)
            return {'ok': True, 'tx_id': tx['tx_id'], 'amount': amount, 'log': log}
        log.append(f'[WIT] socket.io esuat: {sio_res.get("error")} — fallback HTTP')
        print(f'[WIT] socket.io eșuat: {sio_res.get("error")}, fallback broadcast', flush=True)
    except Exception as e:
        log.append(f'[WIT] Exceptie socket.io: {e}')
        print(f'[WIT] tx_builder/sio exc: {e}', flush=True)
        tx = None

    # Metoda 2 (fallback): broadcast HTTP la webd-node-modern (poate 0 peers, dar logat)
    try:
        if tx is None:
            nonce2, time_lock2 = fetch_nonce_and_timelock(POOL_ADDRESS)
            tx = build_signed_tx(
                from_address=POOL_ADDRESS,
                private_key_hex=POOL_PRIVKEY,
                public_key_hex=POOL_PUBKEY,
                to_address=address,
                amount_webd=round(amount, 4),
                nonce=nonce2,
                time_lock=time_lock2,
            )
        result = broadcast_tx(tx['serialized_hex'])
        status = 'sent' if result.get('result') else 'failed'
        db_add_withdrawal(address, amount, tx['serialized_hex'], tx['tx_id'], status)
        if status == 'sent':
            peers = result.get('peers_notified', 0)
            log.append(f'[WIT] HTTP broadcast: {peers} peers notificati')
            print(f'[WIT broadcast] {amount:.4f} WEBD -> {address[:20]}... tx={tx["tx_id"][:16]} peers={peers}', flush=True)
            return {'ok': True, 'tx_id': tx['tx_id'], 'amount': amount, 'log': log}
        log.append(f'[WIT] Broadcast esuat: {result.get("error", result)}')
        return {'error': f'Broadcast eșuat: {result.get("error", result)}', 'log': log}
    except Exception as e:
        log.append(f'[WIT] Exceptie HTTP: {e}')
        return {'error': str(e), 'log': log}

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

# ── Node status ────────────────────────────────────────────────────────────────
def get_node_status() -> dict:
    result = {
        'synced': False, 'block_height': None,
        'mining_address': None, 'mining_balance': None,
        'circulating_supply': None, 'stake_pct': None,
        'blocks_per_chance': None, 'estimated_days': None,
        'pool_blocks_found': 0, 'pool_rewards_total': 0.0,
    }
    try:
        top = _get_json(NODE_LOCAL_URL + '/top', timeout=4)
        result['block_height'] = top.get('top') or top.get('height') or top.get('blockHeight')
        result['synced'] = bool(top.get('is_synchronized', result['block_height']))
    except Exception:
        pass

    try:
        mb = _get_json(f'{NODE_LOCAL_URL}/{NODE_SECRET_KEY}/mining/balance', timeout=4)
        result['mining_address'] = mb.get('address')
        bal = mb.get('balance')
        result['mining_balance'] = float(bal) / 10_000 if bal and float(bal) > 1_000_000 else (float(bal) if bal is not None else None)
    except Exception:
        pass

    try:
        chain = _get_json(NODE_URL + '/chain', timeout=5)
        cs = chain.get('circulatingSupply') or chain.get('supply') or chain.get('totalSupply')
        if cs is not None:
            cs = float(cs)
            result['circulating_supply'] = cs / 10_000_000 if cs > 100_000_000_000 else cs / 10_000 if cs > 1_000_000 else cs
        if result['mining_balance'] and result['circulating_supply']:
            bal = result['mining_balance']
            sup = result['circulating_supply']
            pct = bal / sup * 100 if sup > 0 else 0
            result['stake_pct'] = round(pct, 6)
            bpc = round(sup / bal) if bal > 0 else None
            result['blocks_per_chance'] = bpc
            if bpc:
                result['estimated_days'] = round(bpc * 60 / 86400, 1)
    except Exception:
        pass

    with _db_lock, _conn() as c:
        row = c.execute('SELECT COUNT(*) AS cnt, COALESCE(SUM(reward_amount),0) AS total FROM reward_events').fetchone()
        result['pool_blocks_found'] = row['cnt']
        result['pool_rewards_total'] = round(row['total'], 4)

    return result

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
                    params[k] = urllib.parse.unquote(v)  # unquote, nu unquote_plus (+ e valid in adrese WEBD)

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

        elif path == '/api/node-status':
            self._json(get_node_status())

        elif path == '/api/stakers':
            self._json(db_get_all_stakers())

        elif path == '/api/rewards':
            self._json(db_get_recent_rewards(int(params.get('limit', 20))))

        elif path.startswith('/api/balance/'):
            self._json(db_get_balance(urllib.parse.unquote(path[len('/api/balance/'):])))

        elif path.startswith('/api/deposits/'):
            self._json(db_get_deposits(urllib.parse.unquote(path[len('/api/deposits/'):])))

        elif path.startswith('/api/withdrawals/'):
            self._json(db_get_withdrawals(urllib.parse.unquote(path[len('/api/withdrawals/'):])))

        elif path == '/api/export':
            self._json(db_export_ledger())

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
    threading.Thread(target=backup_loop,    daemon=True, name='backup').start()

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
