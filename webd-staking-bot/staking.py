"""
Scanner depuneri on-chain + distribuitor rewards + executor retrageri automate.
"""
import asyncio, logging, json, ssl, urllib.request, urllib.parse

from config import (
    TIP_BOT_SEED, TIP_BOT_PUBKEY, TIP_BOT_ADDRESS,
    NODE_URL, NODE_LOCAL_URL, BROADCAST_URL,
)
import db

log = logging.getLogger('webd-staking')

SCAN_INTERVAL = 30      # secunde intre scanuri
TX_FEE_WEBD   = 10.0   # fee retragere (costa din balanta userului)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode    = ssl.CERT_NONE


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=8, context=_ssl_ctx) as r:
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
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx) as r:
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


# ── Retragere automata ────────────────────────────────────────────────────────

async def execute_withdrawal(telegram_id: int, amount: float, dest_wallet: str) -> dict:
    """Semneaza si trimite tranzactia via nodul legacy sincronizat. Returneaza {ok, tx_id, error}."""
    try:
        import urllib.parse
        from_enc = urllib.parse.quote(TIP_BOT_ADDRESS, safe='')
        to_enc   = urllib.parse.quote(dest_wallet, safe='')
        url = (
            f'http://127.0.0.1:8081/SECRET_SECRET_SECRET_LONG_SECRET_123456'
            f'/wallets/create-transaction/{from_enc}/{to_enc}/{amount}/{TX_FEE_WEBD}'
        )
        result = await asyncio.to_thread(_get, url)
        if not result:
            return {'ok': False, 'error': 'Nod legacy nu raspunde'}
        if not result.get('result'):
            return {'ok': False, 'error': result.get('message') or result.get('reason') or str(result)}
        tx_id = result.get('txId') or result.get('tx_id') or ''
        log.info(f'Retragere trimisa via nod legacy: txId={tx_id} amount={amount} to={dest_wallet}')
        return {'ok': True, 'tx_id': tx_id}
    except Exception as e:
        log.exception('execute_withdrawal error')
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
