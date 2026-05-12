import urllib.request, urllib.error, json, ssl
from config import STAKING_API_URL, STAKING_API_SECRET, EXPLORER_API_URL

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode    = ssl.CERT_NONE

def _get(url: str, secret: str = '') -> dict | list | None:
    try:
        req = urllib.request.Request(url)
        if secret:
            req.add_header('X-Secret', secret)
        with urllib.request.urlopen(req, timeout=8, context=_ctx) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

# ── Staking API ───────────────────────────────────────────────────────────────

def get_staking_stats() -> dict | None:
    return _get(f'{STAKING_API_URL}/api/stats')

def get_node_status() -> dict | None:
    return _get(f'{STAKING_API_URL}/api/node-status')

def get_stakers() -> list | None:
    return _get(f'{STAKING_API_URL}/api/stakers')

def get_staking_balance(address: str) -> dict | None:
    return _get(f'{STAKING_API_URL}/api/balance/{urllib.parse.quote(address)}')

def get_staking_deposits(address: str) -> list | None:
    return _get(f'{STAKING_API_URL}/api/deposits/{urllib.parse.quote(address)}')

def get_rewards() -> list | None:
    return _get(f'{STAKING_API_URL}/api/rewards')

# ── Explorer / Price API ──────────────────────────────────────────────────────

def get_price() -> dict | None:
    # Incearca endpoint cunoscut explorer WebDollar
    for path in ['/api/price', '/api/v1/price', '/price']:
        data = _get(f'{EXPLORER_API_URL}{path}')
        if data:
            return data
    return None

def get_blockchain_height() -> int:
    data = _get(f'{STAKING_API_URL}/api/node-status')
    if data and isinstance(data, dict):
        return int(data.get('height', 0) or 0)
    return 0

import urllib.parse
