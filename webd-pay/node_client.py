import requests
import config

WEBD_UNITS = 10_000  # 1 WEBD = 10,000 sub-units

def get_address_balance(address: str):
    """Returns balance in WEBD (float), or None on error."""
    url = f"{config.NODE_URL}/{config.NODE_SECRET}/address/balance/{address}"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        raw = data.get('balance', 0)
        return raw / WEBD_UNITS
    except Exception:
        return None
