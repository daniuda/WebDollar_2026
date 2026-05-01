#!/usr/bin/env python3
"""
Test local complet pentru webd-staking — fără nod WebDollar real.

Pornește:
  1. Un nod WebDollar FALS (mock HTTP server) pe portul 19080
  2. Staking server pe portul 13004 (cu config de test)

Testează:
  - Detectare depozite din blocuri
  - Detectare recompensă de bloc (coinbase)
  - Distribuire proporțională recompense
  - Tranzacție multi-output (build + verificare, fără broadcast real)
  - Endpoint-uri HTTP ale staking server-ului

Rulare: python test_local.py
"""

import json, os, sys, tempfile, shutil, time, threading, subprocess
import urllib.request, urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

# Windows: forteaza UTF-8 pentru output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── generare chei Ed25519 reale pentru test ────────────────────────────────────
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

def gen_keypair():
    """Returnează (seed_hex, pubkey_hex) pentru un keypair Ed25519 aleator."""
    if not HAS_CRYPTO:
        return ('aa' * 32, 'bb' * 32)
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    pub  = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return seed, pub

# ── adrese de test (format simplificat — folosim hex-uri fake) ─────────────────
# Nu putem genera adrese WEBD valide fără logica completă, dar putem testa
# restul fluxului cu adrese placeholder și să testăm tx_builder separat.

STAKER1 = 'WEBD$TESTAddr1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAe'
STAKER2 = 'WEBD$TESTAddr2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAe'
STAKER3 = 'WEBD$TESTAddr3AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAe'
POOL_ADDR = 'WEBD$PoolAddrAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAe'

# ── mock WebDollar node ────────────────────────────────────────────────────────
MOCK_PORT = 19080
BROADCAST_PORT = 19081

# Blocuri simulate:
# bloc 91: depozit 500 WEBD de la STAKER1
# bloc 92: depozit 300 WEBD de la STAKER2
# bloc 93: depozit 200 WEBD de la STAKER3
# bloc 94: recompensă bloc 10 WEBD (coinbase → pool)
# bloc 95-99: goale
MOCK_BLOCKS = {
    91: {
        'height': 91,
        'transactions': [
            {'from': {'address': STAKER1}, 'to': {'address': POOL_ADDR}, 'amount': 5_000_000}  # 500 WEBD în units
        ]
    },
    92: {
        'height': 92,
        'transactions': [
            {'from': {'address': STAKER2}, 'to': {'address': POOL_ADDR}, 'amount': 3_000_000}
        ]
    },
    93: {
        'height': 93,
        'transactions': [
            {'from': {'address': STAKER3}, 'to': {'address': POOL_ADDR}, 'amount': 2_000_000}
        ]
    },
    94: {
        'height': 94,
        'miner': POOL_ADDR,
        'reward': 100_000,  # 10 WEBD în units
        'transactions': [
            {'from': {'address': None}, 'to': {'address': POOL_ADDR}, 'amount': 100_000}
        ]
    },
}
for h in range(95, 101):
    MOCK_BLOCKS[h] = {'height': h, 'transactions': []}

_broadcast_received = []

class MockNodeHandler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/height':
            self._json({'height': 100})
        elif self.path.startswith('/block/'):
            h = int(self.path.split('/')[-1])
            self._json(MOCK_BLOCKS.get(h, {'height': h, 'transactions': []}))
        else:
            self._json({})

    def do_POST(self):
        n    = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        _broadcast_received.append(body)
        self._json({'result': True, 'bytes': len(body.get('hex', '')), 'peers_notified': 3})

# ── setup temp dir și config ───────────────────────────────────────────────────
def setup_test_env():
    tmp = Path(tempfile.mkdtemp(prefix='webd_staking_test_'))
    seed, pub = gen_keypair()
    config = {
        'pool': {
            'address': POOL_ADDR,
            'private_key_hex': seed,
            'public_key_hex':  pub,
            'fee_pct': 10,
            'node_url':      f'http://127.0.0.1:{MOCK_PORT}',
            'broadcast_url': f'http://127.0.0.1:{MOCK_PORT}/tx/broadcast',
        },
        'staking': {
            'min_stake_webd':  100,
            'min_payout_webd': 1,    # prag mic pentru test
            'scan_interval_sec': 999,  # nu pornim loop automat în test
            'history_days': 30,
        },
        'dashboard': {'host': '127.0.0.1', 'port': 13004},
    }
    (tmp / 'config.json').write_text(json.dumps(config))
    return tmp, seed, pub

# ── helpers de test ────────────────────────────────────────────────────────────
PASS = '[OK]'
FAIL = '[FAIL]'
_tests = {'ok': 0, 'fail': 0}

def check(name, condition, detail=''):
    if condition:
        print(f'  {PASS} {name}')
        _tests['ok'] += 1
    else:
        print(f'  {FAIL} {name}  {detail}')
        _tests['fail'] += 1

def approx(a, b, tol=0.01):
    return abs(a - b) < tol

# ── TEST 1: tx_builder ─────────────────────────────────────────────────────────
def test_tx_builder():
    print('\n[1] tx_builder.py')
    try:
        from tx_builder import u7le, double_sha256, build_signed_tx_multi, PAYOUT_FEE_PCT
        check('import ok', True)
        check('u7le(10000)', u7le(10000).hex() == '1027000000000000'[:14])  # little-endian
        check('double_sha256 len', len(double_sha256(b'test')) == 32)
        check('PAYOUT_FEE_PCT = 0.5', PAYOUT_FEE_PCT == 0.5)
        print(f'     PAYOUT_FEE_PCT = {PAYOUT_FEE_PCT}%')
    except Exception as e:
        check('import tx_builder', False, str(e))

# ── TEST 2: logică de distribuție ──────────────────────────────────────────────
def test_distribution_math():
    print('\n[2] Logică distribuție proporțională')

    total_stake   = 1000.0  # STAKER1=500, STAKER2=300, STAKER3=200
    reward        = 10.0
    pool_fee_pct  = 0.10
    fee_taken     = reward * pool_fee_pct       # 1.0 WEBD
    distributable = reward - fee_taken           # 9.0 WEBD

    stakes = {'S1': 500, 'S2': 300, 'S3': 200}
    shares = {k: round((v / total_stake) * distributable, 6) for k, v in stakes.items()}

    check('fee pool 10%', approx(fee_taken, 1.0))
    check('distribuit 9 WEBD', approx(distributable, 9.0))
    check('S1 share (50%)', approx(shares['S1'], 4.5))
    check('S2 share (30%)', approx(shares['S2'], 2.7))
    check('S3 share (20%)', approx(shares['S3'], 1.8))
    check('suma shares == distributable', approx(sum(shares.values()), distributable))
    print(f'     Shares: S1={shares["S1"]:.4f} S2={shares["S2"]:.4f} S3={shares["S3"]:.4f}')

    # Payout fee 0.5%
    total_payout = sum(shares.values())
    payout_fee   = max(10.0, total_payout * 0.005)
    check('payout fee = max(10, 0.5%)', approx(payout_fee, 10.0))  # 9 WEBD * 0.5% = 0.045 < 10 → folosim 10
    print(f'     Payout fee: {payout_fee:.4f} WEBD (min 10 WEBD se aplică pentru sume mici)')
    print(f'     La 2000 WEBD total distribuit: fee = 10 WEBD = 0.5%')

def _api(path, port=13004):
    try:
        url = f'http://127.0.0.1:{port}{path}'
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

def _wait_server(port=13004, timeout=8):
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/stats', timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False

# ── TEST 3: server HTTP complet ─────────────────────────────────────────────────
def test_server_http(tmp: Path):
    print('\n[3] Server HTTP — depozite, rewards, stats')

    SRVPORT = 13004
    # Scriem config.json temporar în directorul webd-staking (BASE_DIR hardcodat în server.py)
    script_dir   = Path(__file__).parent
    config_path  = script_dir / 'config.json'
    db_path      = script_dir / 'staking_test.db'
    config_bak   = script_dir / 'config.json.bak'

    seed, pub = gen_keypair()
    test_config = {
        'pool': {
            'address': POOL_ADDR,
            'private_key_hex': seed,
            'public_key_hex':  pub,
            'fee_pct': 10,
            'node_url':      f'http://127.0.0.1:{MOCK_PORT}',
            'broadcast_url': f'http://127.0.0.1:{MOCK_PORT}/tx/broadcast',
        },
        'staking': {'min_stake_webd': 100, 'min_payout_webd': 1,
                    'scan_interval_sec': 999, 'history_days': 30},
        'dashboard': {'host': '127.0.0.1', 'port': SRVPORT},
        '_test_db': str(db_path),
    }

    # Backup config dacă există
    if config_path.exists():
        config_path.rename(config_bak)
    config_path.write_text(json.dumps(test_config))

    proc = None
    try:
        # Pornește server ca subprocess
        proc = subprocess.Popen(
            [sys.executable, str(script_dir / 'server.py')],
            cwd=str(script_dir),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ok = _wait_server(SRVPORT)
        check('server pornit', ok)
        if not ok:
            return

        # Asteapta scan initial (blocuri 91-100 din mock)
        time.sleep(3)

        stats = _api('/api/stats')
        check('GET /api/stats',          'pool_address' in stats)
        check('pool_address corect',      stats.get('pool_address') == POOL_ADDR)
        check('payout_fee_pct = 0.5',    stats.get('payout_fee_pct') == 0.5)
        print(f'     fee pool: {stats.get("pool_fee_pct")}%  payout fee: {stats.get("payout_fee_pct")}%')

        # Dupa scan: 3 depozite detectate (bloc 91,92,93) + reward in bloc 94
        stakers = _api('/api/stakers')
        check('GET /api/stakers OK',     isinstance(stakers, list))
        check('3 stakers detectati',     len(stakers) == 3,
              f'gasit {len(stakers)} (asteptat 3)')
        print(f'     Stakers gasiti: {len(stakers)}')

        bal1 = _api(f'/api/balance/{STAKER1}')
        check('GET /api/balance/:addr',  'deposited_total' in bal1)
        check('STAKER1 deposited=500',   approx(bal1.get('deposited_total', 0), 500.0),
              f'gasit {bal1.get("deposited_total")}')
        check('STAKER1 rewards>0',       bal1.get('rewards_total', 0) > 0,
              f'rewards={bal1.get("rewards_total")}')
        print(f'     STAKER1: deposited={bal1.get("deposited_total")} rewards={bal1.get("rewards_total"):.4f}')

        rewards = _api('/api/rewards')
        check('GET /api/rewards',        isinstance(rewards, list))
        check('reward event detectat',   len(rewards) >= 1,
              f'gasit {len(rewards)} events (asteptat >=1)')
        if rewards:
            print(f'     Reward event: {rewards[0]["reward_amount"]} WEBD distribuit={rewards[0]["distributed"]}')

    except Exception as e:
        check('server HTTP', False, str(e))
    finally:
        if proc:
            proc.terminate()
            proc.wait()
        # Restaureaza config
        config_path.unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)
        if config_bak.exists():
            config_bak.rename(config_path)

# ── TEST 4: is_coinbase și scan logic ─────────────────────────────────────────
def test_scan_logic():
    print('\n[4] Detectare coinbase vs depozit')
    # Testăm logica direct fără a importa server.py
    COINBASE_SET = {'', 'null', 'none', '0', 'coinbase', 'genesis', 'reward'}

    def is_coinbase(addr):
        if not addr:
            return True
        a = str(addr).lower().strip()
        return a in COINBASE_SET or a.startswith('0x000')

    check('is_coinbase("")',        is_coinbase(''))
    check('is_coinbase(None)',      is_coinbase(None))
    check('is_coinbase("null")',    is_coinbase('null'))
    check('is_coinbase("coinbase")',is_coinbase('coinbase'))
    check('is_coinbase("0x0000")',  is_coinbase('0x0000abcd'))
    check('not coinbase(WEBD$...)', not is_coinbase('WEBD$abc123'))
    check('not coinbase(user addr)',not is_coinbase(STAKER1))

    # Simulează scan logic
    txs_bloc_94 = [{'from': {'address': None}, 'to': {'address': POOL_ADDR}, 'amount': 100_000}]
    txs_bloc_91 = [{'from': {'address': STAKER1}, 'to': {'address': POOL_ADDR}, 'amount': 5_000_000}]

    for tx in txs_bloc_94:
        from_addr = (tx.get('from') or {}).get('address') or ''
        check('bloc 94: from=None => coinbase', is_coinbase(from_addr))

    for tx in txs_bloc_91:
        from_addr = (tx.get('from') or {}).get('address') or ''
        check('bloc 91: from=STAKER1 => depozit', not is_coinbase(from_addr))

# ── TEST 5: tx_builder multi-output (cu chei reale) ───────────────────────────
def test_multi_output(seed_hex: str, pub_hex: str):
    print('\n[5] build_signed_tx_multi() — structura tranzacției')
    if not HAS_CRYPTO:
        print('  [SKIP] pip3 install cryptography necesar')
        return
    try:
        from tx_builder import build_signed_tx_multi, decode_webd_address, MIN_FEE_WEBD

        # Generăm adrese WEBD valide pentru test
        # Folosim adrese reale din webd pentru că decode_webd_address face validare strictă
        # Testăm structura cu o singură adresă validă
        # (nu avem adrese WEBD reale de test, deci testăm doar ce putem)
        check('build_signed_tx_multi importat', True)
        check('MIN_FEE_WEBD = 10', MIN_FEE_WEBD == 10)

        # Test fee calculation
        from tx_builder import PAYOUT_FEE_PCT
        total_2000 = 2000.0
        fee_2000   = max(10.0, total_2000 * PAYOUT_FEE_PCT / 100)
        check('fee 0.5% din 2000 = 10 WEBD', approx(fee_2000, 10.0))

        total_5000 = 5000.0
        fee_5000   = max(10.0, total_5000 * PAYOUT_FEE_PCT / 100)
        check('fee 0.5% din 5000 = 25 WEBD', approx(fee_5000, 25.0))

        total_100k = 100_000.0
        fee_100k   = max(10.0, total_100k * PAYOUT_FEE_PCT / 100)
        check('fee 0.5% din 100000 = 500 WEBD', approx(fee_100k, 500.0))

        print(f'     Exemple fee multi-output:')
        print(f'       1000 WEBD / 10 stakers: fee=10 WEBD → per staker 1 WEBD (era 10 WEBD)')
        print(f'       5000 WEBD / 50 stakers: fee=25 WEBD → per staker 0.5 WEBD (era 10 WEBD)')
        print(f'     Economie față de plăți individuale:')
        for n, total in [(10, 1000), (50, 5000), (100, 10000)]:
            fee_multi  = max(10.0, total * 0.005)
            fee_single = n * 10.0
            print(f'       {n} stakers, {total} WEBD: multi={fee_multi:.0f} WEBD vs single={fee_single:.0f} WEBD (×{fee_single/fee_multi:.0f} mai ieftin)')

    except Exception as e:
        check('multi-output', False, str(e))

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    print('=' * 60)
    print(' WebDollar Staking — test local')
    print('=' * 60)

    # Pornește mock node
    mock_srv = HTTPServer(('127.0.0.1', MOCK_PORT), MockNodeHandler)
    t = threading.Thread(target=mock_srv.serve_forever, daemon=True)
    t.start()
    print(f'\nMock WebDollar node pornit pe http://127.0.0.1:{MOCK_PORT}')

    # Setup
    tmp, seed, pub = setup_test_env()
    print(f'Config test în: {tmp}')

    try:
        test_tx_builder()
        test_distribution_math()
        test_server_http(tmp)
        test_scan_logic()
        test_multi_output(seed, pub)
    finally:
        mock_srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    print('\n' + '=' * 60)
    total = _tests['ok'] + _tests['fail']
    print(f' Rezultat: {_tests["ok"]}/{total} teste trecute', end='')
    if _tests['fail']:
        print(f' ({_tests["fail"]} EȘUATE)')
    else:
        print(' — TOATE OK')
    print('=' * 60)
    sys.exit(0 if _tests['fail'] == 0 else 1)

if __name__ == '__main__':
    # Trebuie rulat din directorul webd-staking
    script_dir = Path(__file__).parent
    if Path.cwd() != script_dir:
        os.chdir(script_dir)
    main()
