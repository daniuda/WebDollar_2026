import sqlite3, uuid, json
from datetime import datetime, timezone

DB_PATH = 'payments.db'

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS payments (
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
            webhook_status TEXT DEFAULT 'pending',
            webhook_attempts INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS address_pool (
            address TEXT PRIMARY KEY,
            in_use  INTEGER NOT NULL DEFAULT 0,
            payment_id TEXT
        );
        """)

def create_payment(*, amount_webd, pay_to_address, expires_at, secret,
                   merchant_id=None, webhook_url=None, redirect_url=None, metadata=None):
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    meta = json.dumps(metadata) if metadata else None
    with _conn() as c:
        c.execute("""INSERT INTO payments
            (id, merchant_id, amount_webd, pay_to_address, expires_at, secret,
             webhook_url, redirect_url, metadata, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (pid, merchant_id, amount_webd, pay_to_address, expires_at, secret,
             webhook_url, redirect_url, meta, now))
    return get_payment(pid)

def get_payment(payment_id):
    with _conn() as c:
        row = c.execute('SELECT * FROM payments WHERE id=?', (payment_id,)).fetchone()
    return dict(row) if row else None

def update_payment_paid(payment_id, paid_amount, tx_hash=''):
    with _conn() as c:
        c.execute("""UPDATE payments SET status='paid', paid_amount=?, tx_hash=?,
                     confirmations=1 WHERE id=?""", (paid_amount, tx_hash, payment_id))

def update_webhook_status(payment_id, status, attempts):
    with _conn() as c:
        c.execute('UPDATE payments SET webhook_status=?, webhook_attempts=? WHERE id=?',
                  (status, attempts, payment_id))

def get_pending_payments():
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM payments WHERE status='pending' AND expires_at > ?", (now,)
        ).fetchall()
    return [dict(r) for r in rows]

def get_payments_needing_webhook():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM payments WHERE status='paid' AND webhook_url IS NOT NULL"
            " AND webhook_status NOT IN ('sent','failed')"
        ).fetchall()
    return [dict(r) for r in rows]

def expire_old_payments():
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("UPDATE payments SET status='expired' WHERE status='pending' AND expires_at <= ?", (now,))

def seed_address_pool(addresses):
    with _conn() as c:
        c.executemany("INSERT OR IGNORE INTO address_pool (address) VALUES (?)",
                      [(a,) for a in addresses])

def get_available_address():
    with _conn() as c:
        row = c.execute("SELECT address FROM address_pool WHERE in_use=0 LIMIT 1").fetchone()
        if not row:
            return None
        addr = row['address']
        c.execute("UPDATE address_pool SET in_use=1 WHERE address=?", (addr,))
    return addr

def release_address(address):
    with _conn() as c:
        c.execute("UPDATE address_pool SET in_use=0, payment_id=NULL WHERE address=?", (address,))
