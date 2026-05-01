#!/usr/bin/env python3
"""
Reconstrucție de urgență a bazei de date din blockchain.

Folosit când staking.db e pierdut/corupt și nu există backup.
Rescaneaza TOATE blocurile și reconstruieste:
  ✓ deposits     — toate depozitele primite (vizibile pe blockchain)
  ✓ withdrawals  — toate plățile trimise (vizibile pe blockchain)
  ✓ user_balances.deposited_total și withdrawn_total
  ✗ rewards_total / reward_events — calculate off-chain, NU pot fi recuperate
    (dar net_balance = deposited - withdrawn este corect și suficient pentru rambursări)

Rulare:
  python rescan.py                     # rescan complet
  python rescan.py --from 50000        # de la bloc 50000
  python rescan.py --dry-run           # simulare, fără scriere în DB
  python rescan.py --report            # generează raport JSON fără rescan
"""

import argparse, json, sys, time
from pathlib import Path

# ── setup path ─────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'config.json'
RESCAN_DB   = BASE_DIR / 'staking_rescan.db'   # DB separat, nu suprascrie cel live

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── config ─────────────────────────────────────────────────────────────────────
if not CONFIG_PATH.exists():
    print(f'[ERROR] config.json lipsă în {BASE_DIR}')
    sys.exit(1)

cfg          = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
POOL_ADDRESS = cfg['pool']['address']
NODE_URL     = cfg['pool']['node_url'].rstrip('/')

# ── HTTP helpers ───────────────────────────────────────────────────────────────
import urllib.request, ssl

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode    = ssl.CERT_NONE

def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except ssl.SSLError:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            return json.loads(r.read())

def fetch_height() -> int:
    d = _get(f'{NODE_URL}/height')
    return int(d.get('height', d) if isinstance(d, dict) else d)

def fetch_block(h: int) -> dict:
    d = _get(f'{NODE_URL}/block/{h}')
    return d if isinstance(d, dict) else {}

def parse_amount(tx: dict) -> float:
    raw = (tx.get('amount') or (tx.get('to') or {}).get('amount') or tx.get('value') or 0)
    try:
        v = float(raw)
        return v / 10_000 if v > 1_000_000 else v
    except Exception:
        return 0.0

_COINBASE = {'', 'null', 'none', '0', 'coinbase', 'genesis', 'reward'}

def is_coinbase(addr) -> bool:
    if not addr:
        return True
    a = str(addr).lower().strip()
    return a in _COINBASE or a.startswith('0x000')

# ── DB helpers ─────────────────────────────────────────────────────────────────
import sqlite3

def init_rescan_db(db_path: Path):
    with sqlite3.connect(str(db_path)) as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_address TEXT NOT NULL,
                amount_webd REAL NOT NULL,
                block_height INTEGER NOT NULL,
                tx_id TEXT UNIQUE,
                ts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                amount_webd REAL NOT NULL,
                tx_id TEXT UNIQUE,
                block_height INTEGER NOT NULL,
                ts INTEGER NOT NULL,
                status TEXT DEFAULT 'confirmed'
            );
            CREATE TABLE IF NOT EXISTS user_balances (
                address TEXT PRIMARY KEY,
                deposited_total REAL NOT NULL DEFAULT 0,
                withdrawn_total REAL NOT NULL DEFAULT 0,
                net_balance REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS rescan_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        c.commit()

def save_deposit(c, from_addr, amount, height, tx_id):
    ts = int(time.time())
    try:
        c.execute('INSERT OR IGNORE INTO deposits (from_address,amount_webd,block_height,tx_id,ts) VALUES (?,?,?,?,?)',
                  (from_addr, amount, height, tx_id, ts))
        c.execute('''INSERT INTO user_balances (address,deposited_total,net_balance) VALUES (?,?,?)
                     ON CONFLICT(address) DO UPDATE SET
                       deposited_total = deposited_total + excluded.deposited_total,
                       net_balance     = net_balance     + excluded.net_balance''',
                  (from_addr, amount, amount))
    except Exception:
        pass

def save_withdrawal(c, to_addr, amount, height, tx_id):
    ts = int(time.time())
    try:
        c.execute('INSERT OR IGNORE INTO withdrawals (address,amount_webd,block_height,tx_id,ts) VALUES (?,?,?,?,?)',
                  (to_addr, amount, height, tx_id, ts))
        c.execute('''INSERT INTO user_balances (address,withdrawn_total,net_balance) VALUES (?,?,?)
                     ON CONFLICT(address) DO UPDATE SET
                       withdrawn_total = withdrawn_total + excluded.withdrawn_total,
                       net_balance     = net_balance     - excluded.withdrawn_total''',
                  (to_addr, amount, amount))
    except Exception:
        pass

# ── Scan ───────────────────────────────────────────────────────────────────────
def scan_block(c, height: int, dry_run=False) -> tuple:
    """Returnează (deposits, withdrawals) găsite în bloc."""
    try:
        block = fetch_block(height)
    except Exception as e:
        print(f'  [!] Bloc {height} eroare: {e}', flush=True)
        return 0, 0

    deps, wds = 0, 0
    txs = block.get('transactions') or block.get('txs') or []

    for tx in txs:
        to_addr   = ((tx.get('to') or {}).get('address') or tx.get('toAddress') or '')
        from_addr = ((tx.get('from') or {}).get('address') or tx.get('fromAddress') or '')
        amount    = parse_amount(tx)
        tx_id     = tx.get('id') or tx.get('txId') or tx.get('hash') or f'b{height}-{deps+wds}'

        if not amount:
            continue

        if to_addr == POOL_ADDRESS and not is_coinbase(from_addr):
            # Depozit de la un staker
            if not dry_run:
                save_deposit(c, from_addr, amount, height, tx_id)
            deps += 1

        elif from_addr == POOL_ADDRESS and not is_coinbase(to_addr):
            # Plată trimisă de pool (retragere sau reward)
            if not dry_run:
                save_withdrawal(c, to_addr, amount, height, tx_id)
            wds += 1

    return deps, wds

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Rescan blockchain pentru reconstrucție staking DB')
    parser.add_argument('--from', dest='from_height', type=int, default=0)
    parser.add_argument('--to',   dest='to_height',   type=int, default=None)
    parser.add_argument('--dry-run',  action='store_true')
    parser.add_argument('--report',   action='store_true', help='Afisează raport din DB existent')
    parser.add_argument('--db', default=str(RESCAN_DB))
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.report:
        if not db_path.exists():
            print(f'DB {db_path} nu există. Rulează fără --report mai întâi.')
            sys.exit(1)
        print_report(db_path)
        return

    print(f'Pool address: {POOL_ADDRESS}')
    print(f'Node:         {NODE_URL}')
    print(f'DB output:    {db_path}')
    if args.dry_run:
        print('[DRY-RUN] Nicio scriere în DB.')
    print()

    try:
        current = fetch_height()
        print(f'Înălțime curentă blockchain: {current}')
    except Exception as e:
        print(f'[ERROR] Nu pot accesa nodul: {e}')
        sys.exit(1)

    start  = args.from_height
    end    = args.to_height or current

    if not args.dry_run:
        init_rescan_db(db_path)

    total_deps, total_wds = 0, 0
    t0 = time.time()

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        for h in range(start, end + 1):
            deps, wds = scan_block(conn, h, args.dry_run)
            total_deps += deps
            total_wds  += wds

            if h % 1000 == 0 or deps or wds:
                elapsed = time.time() - t0
                pct     = (h - start) / max(end - start, 1) * 100
                print(f'  Bloc {h:6d}/{end}  ({pct:.1f}%)  '
                      f'deps={total_deps} wds={total_wds}  '
                      f'{elapsed:.0f}s', flush=True)

        if not args.dry_run:
            conn.execute("INSERT OR REPLACE INTO rescan_meta VALUES ('last_scan_height',?)", (str(end),))
            conn.execute("INSERT OR REPLACE INTO rescan_meta VALUES ('scan_ts',?)", (str(int(time.time())),))
            conn.commit()

    elapsed = time.time() - t0
    print(f'\nScan complet: {end-start+1} blocuri în {elapsed:.1f}s')
    print(f'Depozite găsite:  {total_deps}')
    print(f'Plăți găsite:     {total_wds}')

    if not args.dry_run:
        print_report(db_path)

def print_report(db_path: Path):
    print('\n' + '='*60)
    print(' RAPORT BALANȚE (reconstruite din blockchain)')
    print('='*60)
    with sqlite3.connect(str(db_path)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            'SELECT address, deposited_total, withdrawn_total, net_balance'
            ' FROM user_balances ORDER BY net_balance DESC').fetchall()
        meta = {r['key']: r['value'] for r in c.execute('SELECT * FROM rescan_meta').fetchall()}

    if meta:
        print(f"Scanat până la bloc: {meta.get('last_scan_height','?')}")
        ts = int(meta.get('scan_ts', 0))
        print(f"Data scan: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(ts))}")

    print(f'\n{"Adresă":<55} {"Depus":>12} {"Retras":>12} {"Net datorat":>12}')
    print('-'*95)
    total_owed = 0.0
    for r in rows:
        net = r['net_balance']
        if net <= 0:
            continue
        total_owed += net
        addr = r['address']
        short = addr[:20] + '...' + addr[-10:] if len(addr) > 35 else addr
        print(f'{short:<55} {r["deposited_total"]:>12.4f} {r["withdrawn_total"]:>12.4f} {net:>12.4f}')

    print('-'*95)
    print(f'{"TOTAL DATORAT":>80} {total_owed:>12.4f} WEBD')
    print()

    # Export JSON
    report = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'pool_address': POOL_ADDRESS,
        'note': 'rewards_total NU e inclus (calculat off-chain). net_balance = deposited - withdrawn.',
        'total_owed_webd': round(total_owed, 4),
        'stakers': [dict(r) for r in rows if r['net_balance'] > 0],
    }
    out = BASE_DIR / 'rescan_report.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Raport JSON: {out}')

if __name__ == '__main__':
    main()
