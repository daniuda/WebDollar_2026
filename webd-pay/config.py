import json
import os

_cfg = {}

def load():
    global _cfg
    path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(path) as f:
        _cfg = json.load(f)

def get(key, default=None):
    return _cfg.get(key, default)

load()

NODE_URL    = get('node_url', 'http://localhost:8080')
NODE_SECRET = get('node_secret', '')
FLASK_PORT  = get('flask_port', 3010)
TTL_MINUTES = get('session_ttl_minutes', 30)
RATE_LIMIT  = get('rate_limit_per_hour', 10)
BASE_URL    = get('base_url', 'http://localhost:3010')
WDEXP_URL   = get('wdexperience_url', '')
