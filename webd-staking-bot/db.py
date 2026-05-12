import sqlite3
import threading
import time
from config import DB_PATH

_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _lock, _conn() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id   INTEGER PRIMARY KEY,
                username      TEXT    DEFAULT '',
                first_name    TEXT    DEFAULT '',
                webd_wallet   TEXT    DEFAULT '',
                balance       REAL    DEFAULT 0.0,
                total_tipped  REAL    DEFAULT 0.0,
                total_received REAL   DEFAULT 0.0,
                tips_given    INTEGER DEFAULT 0,
                tips_received INTEGER DEFAULT 0,
                created_at    INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id     INTEGER DEFAULT 0,
                to_id       INTEGER DEFAULT 0,
                amount      REAL,
                fee         REAL    DEFAULT 0.0,
                type        TEXT,
                note        TEXT    DEFAULT '',
                status      TEXT    DEFAULT 'completed',
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_tx_from  ON transactions(from_id);
            CREATE INDEX IF NOT EXISTS idx_tx_to    ON transactions(to_id);
            CREATE INDEX IF NOT EXISTS idx_tx_type  ON transactions(type);

            CREATE TABLE IF NOT EXISTS staking_scan_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS staking_deposits (
                tx_id        TEXT PRIMARY KEY,
                from_address TEXT,
                telegram_id  INTEGER DEFAULT 0,
                amount       REAL,
                height       INTEGER,
                ts           INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS staking_reward_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                height      INTEGER UNIQUE,
                reward      REAL,
                total_stake REAL,
                distributed REAL,
                ts          INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS staking_withdrawals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                amount      REAL,
                fee         REAL DEFAULT 0.0,
                dest_wallet TEXT,
                tx_id       TEXT DEFAULT '',
                status      TEXT DEFAULT 'pending',
                ts          INTEGER DEFAULT (strftime('%s','now'))
            );
        ''')

def ensure_user(telegram_id: int, username: str = '', first_name: str = ''):
    with _lock, _conn() as c:
        c.execute('''
            INSERT INTO users(telegram_id, username, first_name)
            VALUES(?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        ''', (telegram_id, username or '', first_name or ''))

def get_user(telegram_id: int) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute('SELECT * FROM users WHERE telegram_id=?', (telegram_id,)).fetchone()
        return dict(row) if row else None

def get_user_by_username(username: str) -> dict | None:
    username = username.lstrip('@')
    with _lock, _conn() as c:
        row = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        return dict(row) if row else None

def get_balance(telegram_id: int) -> float:
    u = get_user(telegram_id)
    return u['balance'] if u else 0.0

def set_wallet(telegram_id: int, wallet: str):
    with _lock, _conn() as c:
        c.execute('UPDATE users SET webd_wallet=? WHERE telegram_id=?', (wallet, telegram_id))

def get_wallet(telegram_id: int) -> str:
    u = get_user(telegram_id)
    return u['webd_wallet'] if u else ''

def do_tip(from_id: int, to_id: int, amount: float, fee: float = 0.0) -> bool:
    net = amount - fee
    with _lock, _conn() as c:
        sender = c.execute('SELECT balance FROM users WHERE telegram_id=?', (from_id,)).fetchone()
        if not sender or sender['balance'] < amount:
            return False
        c.execute('UPDATE users SET balance=balance-?, total_tipped=total_tipped+?, tips_given=tips_given+1 WHERE telegram_id=?',
                  (amount, amount, from_id))
        c.execute('UPDATE users SET balance=balance+?, total_received=total_received+?, tips_received=tips_received+1 WHERE telegram_id=?',
                  (net, net, to_id))
        c.execute('INSERT INTO transactions(from_id,to_id,amount,fee,type) VALUES(?,?,?,?,?)',
                  (from_id, to_id, amount, fee, 'tip'))
        return True

def credit_deposit(telegram_id: int, amount: float, note: str = ''):
    with _lock, _conn() as c:
        c.execute('UPDATE users SET balance=balance+? WHERE telegram_id=?', (amount, telegram_id))
        c.execute('INSERT INTO transactions(to_id,amount,type,note) VALUES(?,?,?,?)',
                  (telegram_id, amount, 'deposit', note))

def debit_withdraw(telegram_id: int, amount: float, dest_wallet: str) -> bool:
    with _lock, _conn() as c:
        u = c.execute('SELECT balance FROM users WHERE telegram_id=?', (telegram_id,)).fetchone()
        if not u or u['balance'] < amount:
            return False
        c.execute('UPDATE users SET balance=balance-? WHERE telegram_id=?', (amount, telegram_id))
        c.execute('INSERT INTO transactions(from_id,amount,type,note,status) VALUES(?,?,?,?,?)',
                  (telegram_id, amount, 'withdraw', dest_wallet, 'pending'))
        return True

def get_transactions(telegram_id: int, limit: int = 10) -> list:
    with _lock, _conn() as c:
        rows = c.execute('''
            SELECT t.*,
                   u1.username as from_username,
                   u2.username as to_username
            FROM transactions t
            LEFT JOIN users u1 ON t.from_id = u1.telegram_id
            LEFT JOIN users u2 ON t.to_id   = u2.telegram_id
            WHERE t.from_id=? OR t.to_id=?
            ORDER BY t.created_at DESC LIMIT ?
        ''', (telegram_id, telegram_id, limit)).fetchall()
        return [dict(r) for r in rows]

def get_top_tippers(limit: int = 10) -> list:
    with _lock, _conn() as c:
        rows = c.execute('''
            SELECT username, first_name, total_tipped, tips_given
            FROM users WHERE tips_given > 0
            ORDER BY total_tipped DESC LIMIT ?
        ''', (limit,)).fetchall()
        return [dict(r) for r in rows]

# ── Staking: scan state ───────────────────────────────────────────────────────

def get_scan_height() -> int:
    with _lock, _conn() as c:
        row = c.execute("SELECT value FROM staking_scan_state WHERE key='last_height'").fetchone()
        return int(row['value']) if row else 0

def set_scan_height(h: int):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO staking_scan_state(key,value) VALUES('last_height',?)", (str(h),))

def get_local_nonce() -> int | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT value FROM staking_scan_state WHERE key='local_nonce'").fetchone()
        return int(row['value']) if row else None

def set_local_nonce(n: int):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO staking_scan_state(key,value) VALUES('local_nonce',?)", (str(n),))

# ── Staking: depuneri ─────────────────────────────────────────────────────────

def deposit_exists(tx_id: str) -> bool:
    with _lock, _conn() as c:
        return c.execute('SELECT 1 FROM staking_deposits WHERE tx_id=?', (tx_id,)).fetchone() is not None

def credit_staking_deposit(tx_id: str, from_address: str, telegram_id: int, amount: float, height: int):
    with _lock, _conn() as c:
        c.execute(
            'INSERT OR IGNORE INTO staking_deposits(tx_id,from_address,telegram_id,amount,height) VALUES(?,?,?,?,?)',
            (tx_id, from_address, telegram_id, amount, height)
        )
        if telegram_id:
            c.execute('UPDATE users SET balance=balance+? WHERE telegram_id=?', (amount, telegram_id))
            c.execute('INSERT INTO transactions(to_id,amount,type,note) VALUES(?,?,?,?)',
                      (telegram_id, amount, 'deposit', f'on-chain #{height}'))

# ── Staking: rewards ──────────────────────────────────────────────────────────

def reward_event_exists(height: int) -> bool:
    with _lock, _conn() as c:
        return c.execute('SELECT 1 FROM staking_reward_events WHERE height=?', (height,)).fetchone() is not None

def add_reward_event(height: int, reward: float, total_stake: float, distributed: float):
    with _lock, _conn() as c:
        c.execute(
            'INSERT OR IGNORE INTO staking_reward_events(height,reward,total_stake,distributed) VALUES(?,?,?,?)',
            (height, reward, total_stake, distributed)
        )

def credit_reward(telegram_id: int, amount: float):
    with _lock, _conn() as c:
        c.execute('UPDATE users SET balance=balance+?, total_received=total_received+? WHERE telegram_id=?',
                  (amount, amount, telegram_id))
        c.execute('INSERT INTO transactions(to_id,amount,type,note) VALUES(?,?,?,?)',
                  (telegram_id, amount, 'reward', 'staking reward'))

def get_users_with_balance() -> list:
    with _lock, _conn() as c:
        rows = c.execute('SELECT telegram_id, balance FROM users WHERE balance > 0').fetchall()
        return [dict(r) for r in rows]

def get_wallet_map() -> dict:
    """Returneaza {webd_address: telegram_id} pentru toti userii cu wallet setat."""
    with _lock, _conn() as c:
        rows = c.execute("SELECT telegram_id, webd_wallet FROM users WHERE webd_wallet != ''").fetchall()
        return {dict(r)['webd_wallet']: dict(r)['telegram_id'] for r in rows}

def get_staking_stats() -> dict:
    with _lock, _conn() as c:
        total_staked  = c.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0]
        blocks_found  = c.execute('SELECT COUNT(*) FROM staking_reward_events WHERE distributed > 0').fetchone()[0]
        total_rewards = c.execute('SELECT COALESCE(SUM(reward),0) FROM staking_reward_events').fetchone()[0]
        total_depositors = c.execute('SELECT COUNT(*) FROM users WHERE balance > 0').fetchone()[0]
        return {
            'total_staked':    round(total_staked, 4),
            'blocks_found':    blocks_found,
            'total_rewards':   round(total_rewards, 4),
            'active_stakers':  total_depositors,
        }

# ── Staking: retrageri ────────────────────────────────────────────────────────

def add_staking_withdrawal(telegram_id: int, amount: float, fee: float, dest_wallet: str) -> int:
    with _lock, _conn() as c:
        cur = c.execute(
            'INSERT INTO staking_withdrawals(telegram_id,amount,fee,dest_wallet) VALUES(?,?,?,?)',
            (telegram_id, amount, fee, dest_wallet)
        )
        return cur.lastrowid

def update_withdrawal_tx(withdraw_id: int, tx_id: str, status: str):
    with _lock, _conn() as c:
        c.execute('UPDATE staking_withdrawals SET tx_id=?,status=? WHERE id=?',
                  (tx_id, status, withdraw_id))

# ── Bot stats ─────────────────────────────────────────────────────────────────

def get_bot_stats() -> dict:
    with _lock, _conn() as c:
        total_users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_tips  = c.execute('SELECT COUNT(*) FROM transactions WHERE type="tip"').fetchone()[0]
        total_vol   = c.execute('SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type="tip"').fetchone()[0]
        return {'total_users': total_users, 'total_tips': total_tips, 'total_volume': total_vol}
