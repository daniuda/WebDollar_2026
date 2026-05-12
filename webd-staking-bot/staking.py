"""
Scanner depuneri on-chain + distribuitor rewards + executor retrageri automate.
"""
import asyncio, logging, json, ssl, threading, urllib.request, urllib.parse

from config import (
    TIP_BOT_SEED, TIP_BOT_PUBKEY, TIP_BOT_ADDRESS,
    NODE_URL, NODE_LOCAL_URL, BROADCAST_URL, NODE_SECRET_KEY,
)
import db

log = logging.getLogger('webd-staking')

SCAN_INTERVAL = 30      # secunde intre scanuri
TX_FEE_WEBD   = 10.0   # fee retragere (costa din balanta userului)

# ── Nonce local persistent (evita conflicte la retragerile simultane) ─────────
_local_nonce: int | None = None
_local_nonce_lock = threading.Lock()

def _get_nonce_and_timelock() -> tuple[int, int]:
    """Returneaza (nonce, time_lock) sincronizat cu nodul + local persistent."""
    global _local_nonce
    node_nonce = 0
    try:
        addr_enc = urllib.parse.quote(TIP_BOT_ADDRESS, safe='')
        nd = _get(f'{NODE_LOCAL_URL}/address/nonce/{addr_enc}')
        if nd and isinstance(nd, dict):
            node_nonce = int(nd.get('nonce', 0))
    except Exception:
        pass

    with _local_nonce_lock:
        if _local_nonce is None or node_nonce > _local_nonce:
            _local_nonce = node_nonce
        nonce = _local_nonce
        _local_nonce += 1

    time_lock = 0
    try:
        top = _get(f'{NODE_LOCAL_URL}/top')
        if top and isinstance(top, dict):
            time_lock = max(0, int(top.get('top', 0)) - 1)
    except Exception:
        pass

    return nonce, time_lock

def _release_nonce(nonce: int):
    """Elibereaza nonce rezervat daca TX a esuat inainte de broadcast."""
    global _local_nonce
    with _local_nonce_lock:
        if _local_nonce == nonce + 1:
            _local_nonce = nonce

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str) -> dict | list | None:
    try:
        ctx = ssl.create_default_context() if url.startswith('https://') else None
        kw = {'context': ctx} if ctx else {}
        with urllib.request.urlopen(url, timeout=8, **kw) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def _post(url: str, data: dict) -> dict:
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={'Content-Type': 'application/json'}
        )
        ctx = ssl.create_default_context() if url.startswith('https://') else None
        kw = {'context': ctx} if ctx else {}
        with urllib.request.urlopen(req, timeout=10, **kw) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {'error': str(e)}


# ── Blockchain helpers ────────────────────────────────────────────────────────

def _sync_fetch_height() -> int:
    for url in [NODE_URL + '/chain', NODE_URL + '/height', NODE_LOCAL_URL + '/top']:
        data = _get(url)
        if not data:
            continue
        if isinstance(data, dict):
            h = (data.get('height') or
                 data.get('top') or
                 (data.get('chain', {}) or {}).get('height'))
            if h:
                return int(h)
    return 0


def _sync_fetch_block(height: int) -> dict:
    data = _get(f'{NODE_URL}/block/{height}')
    if not isinstance(data, dict):
        return {}
    inner = data.get('data', data)
    if isinstance(inner, dict) and 'data' in inner:
        block_data = inner['data']
        return {
            'height':       height,
            'minerAddress': (block_data.get('minerAddress') or
                             block_data.get('posMinerAddress') or ''),
            'reward':       inner.get('reward', 0),
            'transactions': block_data.get('transactions') or [],
        }
    return inner if isinstance(inner, dict) else {}


def _parse_to_addr(tx: dict) -> str:
    to = tx.get('to') or {}
    if isinstance(to, list):
        to = to[0] if to else {}
    return (to.get('address') or to.get('addr') or '').strip()


def _parse_from_addr(tx: dict) -> str:
    fr = tx.get('from') or {}
    if isinstance(fr, list):
        fr = fr[0] if fr else {}
    return (fr.get('address') or fr.get('addr') or '').strip()


def _parse_amount(tx: dict) -> float:
    to = tx.get('to') or {}
    if isinstance(to, list):
        to = to[0] if to else {}
    raw = tx.get('amount') or (to.get('amount') if isinstance(to, dict) else None) or tx.get('value') or 0
    try:
        v = float(raw)
        return v / 10_000 if v > 1_000_000 else v
    except Exception:
        return 0.0


def _addr_eq(a: str, b: str) -> bool:
    return a.strip().replace('#', 'O') == b.strip().replace('#', 'O')


def _sync_get_nonce(address: str) -> int:
    addr_enc = urllib.parse.quote(address)
    data = _get(f'{NODE_LOCAL_URL}/address/nonce/{addr_enc}')
    if data and isinstance(data, dict):
        n = data.get('nonce') or data.get('count') or data.get('value')
        if n is not None:
            try:
                return int(n)
            except Exception:
                pass
    n = db.get_local_nonce()
    return n if n is not None else 0


# ── Socket.io broadcast ───────────────────────────────────────────────────────

_SIO_NODES = [
    NODE_LOCAL_URL,                   # VPS local — garantat disponibil, propaga la peers
    'http://daniuda.ddns.net:8080',   # nod minier principal (fallback)
]

def _sio_broadcast(tx_hex: str, tx_id: str = '') -> dict:
    """Broadcast TX via socket.io la primul nod disponibil."""
    try:
        import socketio as sio_lib
    except ImportError:
        return {'ok': False, 'error': 'socketio indisponibil'}
    import threading, uuid as _uuid

    tx_bytes = bytes.fromhex(tx_hex)

    for node_url in _SIO_NODES:
        result = {'done': False, 'accepted': False, 'error': None}
        ready_ev = threading.Event()

        sio = sio_lib.Client(logger=False, engineio_logger=False, reconnection=False)

        @sio.event
        def connect():
            pass

        @sio.on('HelloNode')
        def on_hello(data):
            try:
                # Send buffer as JSON {type:'Buffer', data:[...]} so Node.js
                # _processBufferArray converts it to a proper Buffer — raw bytes
                # via binary socket.io attachment are NOT reliably converted.
                sio.emit('transactions/new-pending-transaction', {
                    'buffer': {'type': 'Buffer', 'data': list(tx_bytes)}
                })
                result['done'] = True
            except Exception as exc:
                result['error'] = str(exc)
            threading.Timer(8.0, ready_ev.set).start()

        @sio.on('transactions/new-pending-transaction-id')
        def on_accepted(data):
            result['accepted'] = True
            ready_ev.set()

        @sio.event
        def connect_error(data):
            result['error'] = str(data)
            ready_ev.set()

        q = {'msg': 'HelloNode', 'version': '1.3.24', 'uuid': str(_uuid.uuid4()),
             'nodeType': '0', 'nodeConsensusType': '1', 'domain': 'browser'}
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
            log.info(f'[SIO] TX {tx_id[:16]}... trimis -> {node_url} (accepted={result["accepted"]})')
            return {'ok': True, 'node': node_url, 'accepted': result['accepted']}
        log.warning(f'[SIO] {node_url} esuat: {result["error"]}')

    return {'ok': False, 'error': 'Toate nodurile socket.io indisponibile'}


# ── Retragere automata ────────────────────────────────────────────────────────

async def execute_withdrawal(telegram_id: int, amount: float, dest_wallet: str) -> dict:
    """Construieste TX cu tx_builder, broadcast via socket.io. Fallback la nod legacy."""
    try:
        from tx_builder import build_signed_tx
    except ImportError as e:
        return {'ok': False, 'error': f'tx_builder indisponibil: {e}'}

    # Nonce local persistent + timeLock direct din /top
    try:
        nonce, time_lock = await asyncio.to_thread(_get_nonce_and_timelock)
    except Exception as e:
        return {'ok': False, 'error': f'Nu pot prelua nonce/timeLock: {e}'}
    if not time_lock:
        _release_nonce(nonce)
        log.error('[WIT] timeLock=0 — nodul local indisponibil, TX anulat')
        return {'ok': False, 'error': 'Nod indisponibil — încearcă din nou'}

    # Build TX semnat
    try:
        tx = build_signed_tx(
            from_address=TIP_BOT_ADDRESS,
            private_key_hex=TIP_BOT_SEED,
            public_key_hex=TIP_BOT_PUBKEY,
            to_address=dest_wallet,
            amount_webd=round(amount, 4),
            nonce=nonce,
            time_lock=time_lock,
        )
    except Exception as e:
        _release_nonce(nonce)
        log.exception('build_signed_tx error')
        return {'ok': False, 'error': f'Semnare TX esuata: {e}'}

    tx_id = tx['tx_id']
    log.info(f'[WIT] nonce={nonce} timeLock={time_lock} txId={tx_id[:20]} amount={amount}')

    # Broadcast via socket.io (primar)
    sio_res = await asyncio.to_thread(_sio_broadcast, tx['serialized_hex'], tx_id)
    if sio_res.get('ok'):
        log.info(f'Retragere broadcast sio: txId={tx_id} amount={amount} to={dest_wallet}')
        return {'ok': True, 'tx_id': tx_id}

    # Fallback: nod legacy HTTP broadcast
    log.warning(f'[WIT] socket.io esuat: {sio_res.get("error")}, fallback nod legacy')
    try:
        from_enc = urllib.parse.quote(TIP_BOT_ADDRESS, safe='')
        to_enc   = urllib.parse.quote(dest_wallet, safe='')
        url = (
            f'{NODE_LOCAL_URL}/{NODE_SECRET_KEY}'
            f'/wallets/create-transaction/{from_enc}/{to_enc}/{amount:.4f}/{TX_FEE_WEBD}'
        )
        result = await asyncio.to_thread(_get, url)
        if result and result.get('result'):
            fallback_id = result.get('txId') or result.get('tx_id') or tx_id
            log.info(f'Retragere via nod legacy fallback: txId={fallback_id}')
            return {'ok': True, 'tx_id': fallback_id}
        err = (result or {}).get('message') or str(result)
        return {'ok': False, 'error': f'Fallback nod legacy: {err}'}
    except Exception as e:
        log.exception('execute_withdrawal fallback error')
        return {'ok': False, 'error': str(e)}


# ── Scan loop ─────────────────────────────────────────────────────────────────

async def scan_loop(bot):
    """Loop principal: scanare depuneri + detectare rewards. Rulat in background."""
    await asyncio.sleep(15)   # startul botului
    while True:
        try:
            await _do_scan(bot)
        except Exception:
            log.exception('Eroare in scan_loop')
        await asyncio.sleep(SCAN_INTERVAL)


async def _do_scan(bot):
    if not TIP_BOT_ADDRESS:
        return

    last_h    = db.get_scan_height()
    current_h = await asyncio.to_thread(_sync_fetch_height)

    if current_h <= last_h:
        return

    from_h = last_h + 1
    to_h   = min(current_h, last_h + 200)   # maxim 200 blocuri per ciclu

    wallet_map = db.get_wallet_map()         # {webd_addr: telegram_id}

    for h in range(from_h, to_h + 1):
        block = await asyncio.to_thread(_sync_fetch_block, h)
        if not block:
            continue

        # ── Reward propriu (tip bot a minat blocul) ────────────────────
        miner = (block.get('minerAddress') or '').strip()
        if miner and _addr_eq(miner, TIP_BOT_ADDRESS) and not db.reward_event_exists(h):
            raw = block.get('reward', 0)
            try:
                reward = float(raw)
                if reward > 1_000_000:
                    reward /= 10_000
            except Exception:
                reward = 0.0
            if reward > 0:
                await _distribute_reward(bot, h, reward)

        # ── Depuneri catre adresa bot ──────────────────────────────────
        for tx in (block.get('transactions') or []):
            to_addr = _parse_to_addr(tx)
            if not to_addr or not _addr_eq(to_addr, TIP_BOT_ADDRESS):
                continue

            tx_id = (tx.get('id') or tx.get('txId') or
                     tx.get('hash') or f'block_{h}_{_parse_from_addr(tx)}')
            if db.deposit_exists(tx_id):
                continue

            from_addr = _parse_from_addr(tx)
            amount    = _parse_amount(tx)
            if amount <= 0:
                continue

            # Matching adresa sender → telegram user
            tg_id = (wallet_map.get(from_addr) or
                     wallet_map.get(from_addr.replace('#', 'O')) or
                     wallet_map.get(from_addr.replace('O', '#')))

            db.credit_staking_deposit(tx_id, from_addr, tg_id or 0, amount, h)
            log.info(f'Bloc #{h}: depunere {amount:.4f} WEBD de la {from_addr} → tg={tg_id}')

            if tg_id:
                try:
                    await bot.send_message(
                        tg_id,
                        f"✅ <b>Depunere confirmată automat!</b>\n\n"
                        f"Sumă: <b>{amount:,.4f} WEBD</b>\n"
                        f"Bloc: <b>#{h}</b>\n\n"
                        f"Balanța ta a fost creditată. Ești acum în staking! ⛏",
                        parse_mode='HTML'
                    )
                except Exception:
                    pass

    db.set_scan_height(to_h)


async def _distribute_reward(bot, height: int, reward: float):
    users = db.get_users_with_balance()
    if not users:
        db.add_reward_event(height, reward, 0, 0)
        return

    total = sum(u['balance'] for u in users)
    if total <= 0:
        db.add_reward_event(height, reward, total, 0)
        return

    distributed = 0.0
    for u in users:
        share = round(u['balance'] / total * reward, 6)
        if share <= 0:
            continue
        db.credit_reward(u['telegram_id'], share)
        distributed += share
        try:
            await bot.send_message(
                u['telegram_id'],
                f"⛏ <b>Bloc găsit! Reward primit!</b>\n\n"
                f"Bloc: <b>#{height}</b>\n"
                f"Reward tău: <b>{share:,.4f} WEBD</b>\n"
                f"<i>Cotă ta: {u['balance']:.2f} / {total:.2f} WEBD total</i>",
                parse_mode='HTML'
            )
        except Exception:
            pass

    db.add_reward_event(height, reward, total, distributed)
    log.info(f'Bloc #{height}: distribuit {distributed:.4f} WEBD la {len(users)} useri')
