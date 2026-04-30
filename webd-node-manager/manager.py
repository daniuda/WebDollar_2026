#!/usr/bin/env python3
"""
WebDollar Node Manager — monitoring, alerting, auto-restart.
Python stdlib + sqlite3. psutil optional (CPU/RAM).
"""
import json, os, sqlite3, ssl, subprocess, sys, threading, time
import smtplib, urllib.request, urllib.error
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'config.json'
DB_PATH = BASE_DIR / 'metrics.db'
DASHBOARD_HTML = BASE_DIR / 'dashboard.html'

# ── config ─────────────────────────────────────────────────────────────────────
def load_config():
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return json.load(f)

cfg = load_config()

# ── database ───────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _db_lock, _conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS metrics (
            ts INTEGER PRIMARY KEY,
            cpu_pct REAL, ram_pct REAL, ram_mb INTEGER,
            node_height INTEGER, node_status TEXT,
            pool_workers INTEGER, pool_hashrate REAL, pool_status TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER, level TEXT, message TEXT
        )''')
        c.commit()

def store_metrics(d: dict):
    keep = int(time.time()) - cfg.get('history_days', 7) * 86400
    with _db_lock, _conn() as c:
        c.execute(
            'INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?,?,?,?)',
            (d['ts'], d['cpu_pct'], d['ram_pct'], d['ram_mb'],
             d['node_height'], d['node_status'],
             d['pool_workers'], d['pool_hashrate'], d['pool_status'])
        )
        c.execute('DELETE FROM metrics WHERE ts < ?', (keep,))
        c.commit()

def store_alert(level: str, message: str):
    with _db_lock, _conn() as c:
        c.execute('INSERT INTO alerts (ts, level, message) VALUES (?,?,?)',
                  (int(time.time()), level, message))
        c.commit()

def get_history(hours: int = 24):
    cutoff = int(time.time()) - hours * 3600
    with _db_lock, _conn() as c:
        rows = c.execute(
            'SELECT ts,cpu_pct,ram_pct,ram_mb,node_height,node_status,'
            'pool_workers,pool_hashrate,pool_status '
            'FROM metrics WHERE ts > ? ORDER BY ts', (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]

def get_alerts(limit: int = 50):
    with _db_lock, _conn() as c:
        rows = c.execute(
            'SELECT ts,level,message FROM alerts ORDER BY ts DESC LIMIT ?', (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

# ── http helper ────────────────────────────────────────────────────────────────
_insecure_ctx = ssl.create_default_context()
_insecure_ctx.check_hostname = False
_insecure_ctx.verify_mode = ssl.CERT_NONE

def http_get_json(url: str, timeout: int = 5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except ssl.SSLError:
        with urllib.request.urlopen(url, timeout=timeout, context=_insecure_ctx) as r:
            return json.loads(r.read())

# ── metrics collection ─────────────────────────────────────────────────────────
def collect_system():
    if HAS_PSUTIL:
        return {
            'cpu_pct': round(psutil.cpu_percent(interval=1), 1),
            'ram_pct': round(psutil.virtual_memory().percent, 1),
            'ram_mb': psutil.virtual_memory().used // (1024 * 1024),
        }
    return {'cpu_pct': -1.0, 'ram_pct': -1.0, 'ram_mb': -1}

def collect_node():
    url = cfg['node']['api_url']
    try:
        data = http_get_json(f'{url}/height', timeout=5)
        height = data.get('height', -1) if isinstance(data, dict) else int(data)
        if height is None or height < 0:
            raise ValueError('height invalid')
        return {'node_height': int(height), 'node_status': 'up'}
    except Exception:
        return {'node_height': -1, 'node_status': 'down'}

def collect_pool():
    url = cfg['pool']['api_url']
    try:
        data = http_get_json(f'{url}/pool/stats', timeout=5)
        if not isinstance(data, dict):
            raise ValueError('raspuns invalid')
        workers = int(data.get('workers', data.get('activeWorkers', 0)) or 0)
        hashrate = float(data.get('hashrate', data.get('poolHashrate', 0.0)) or 0.0)
        return {'pool_workers': workers, 'pool_hashrate': round(hashrate, 2), 'pool_status': 'up'}
    except Exception:
        return {'pool_workers': -1, 'pool_hashrate': -1.0, 'pool_status': 'down'}

# ── alerting ───────────────────────────────────────────────────────────────────
def send_telegram(text: str):
    tg = cfg.get('alerts', {}).get('telegram', {})
    if not tg.get('enabled') or not tg.get('token'):
        return
    payload = json.dumps({
        'chat_id': str(tg['chat_id']),
        'text': text,
        'parse_mode': 'HTML',
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tg['token']}/sendMessage",
        data=payload, headers={'Content-Type': 'application/json'}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f'[ALERT] Telegram error: {e}', flush=True)

def send_email(subject: str, body: str):
    em = cfg.get('alerts', {}).get('email', {})
    if not em.get('enabled') or not em.get('username'):
        return
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = em.get('from', em['username'])
    recipients = em['to'] if isinstance(em['to'], list) else [em['to']]
    msg['To'] = ', '.join(recipients)
    try:
        with smtplib.SMTP(em['smtp_host'], em['smtp_port'], timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.login(em['username'], em['password'])
            s.sendmail(msg['From'], recipients, msg.as_string())
    except Exception as e:
        print(f'[ALERT] Email error: {e}', flush=True)

def alert(level: str, message: str):
    ts_str = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts_str}] [{level}] {message}', flush=True)
    store_alert(level, message)
    icon = {'INFO': 'ℹ️', 'WARN': '⚠️', 'ERROR': '🔴', 'CRITICAL': '🚨'}.get(level, '🔔')
    tg_text = f'{icon} <b>WebDollar Node Manager</b>\n<b>[{level}]</b> {message}'
    send_telegram(tg_text)
    send_email(f'[WebDollar Manager] {level}: {message}', message)

# ── watchdog ───────────────────────────────────────────────────────────────────
_consecutive = {'node': 0, 'pool': 0}
_prev_status = {'node': 'up', 'pool': 'up'}
_restart_times: dict = {'node': [], 'pool': []}

def watchdog_tick(service: str, status: str):
    wd = cfg.get('watchdog', {})

    if status == 'up':
        if _prev_status[service] == 'down':
            alert('INFO', f'{service} este din nou ONLINE.')
        _consecutive[service] = 0
        _prev_status[service] = 'up'
        return

    # down
    _consecutive[service] += 1
    if _prev_status[service] == 'up':
        alert('ERROR', f'{service} este DOWN! ({_consecutive[service]} eșec consecutiv)')
    _prev_status[service] = 'down'

    if not wd.get('enabled') or not wd.get('restart_on_failure'):
        return

    threshold = int(wd.get('consecutive_failures_before_restart', 3))
    if _consecutive[service] < threshold:
        return

    now = time.time()
    max_per_hour = int(wd.get('max_restarts_per_hour', 3))
    _restart_times[service] = [t for t in _restart_times[service] if now - t < 3600]

    if len(_restart_times[service]) >= max_per_hour:
        alert('CRITICAL',
              f'{service}: limită restart atinsă ({max_per_hour}/oră). Intervenție manuală necesară!')
        return

    restart_cmd = cfg.get(service, {}).get('restart_cmd', '')
    if not restart_cmd:
        alert('WARN', f'{service}: watchdog activ dar restart_cmd nu e configurat.')
        return

    try:
        subprocess.run(restart_cmd, shell=True, timeout=30, check=True)
        _restart_times[service].append(now)
        _consecutive[service] = 0
        alert('INFO', f'{service} restartat automat (cmd: {restart_cmd})')
    except Exception as e:
        alert('ERROR', f'{service}: restart eșuat — {e}')

# ── current state ──────────────────────────────────────────────────────────────
_state_lock = threading.Lock()
_current: dict = {
    'ts': 0,
    'cpu_pct': -1.0, 'ram_pct': -1.0, 'ram_mb': -1,
    'node_height': -1, 'node_status': 'unknown',
    'pool_workers': -1, 'pool_hashrate': -1.0, 'pool_status': 'unknown',
    'has_psutil': HAS_PSUTIL,
    'uptime_start': int(time.time()),
}

def update_loop():
    interval = int(cfg.get('check_interval_sec', 30))
    while True:
        try:
            sys_data = collect_system()
            node_data = collect_node()
            pool_data = collect_pool()
            snapshot = {'ts': int(time.time()), **sys_data, **node_data, **pool_data}
            store_metrics(snapshot)
            with _state_lock:
                _current.update(snapshot)
            watchdog_tick('node', node_data['node_status'])
            watchdog_tick('pool', pool_data['pool_status'])
        except Exception as e:
            print(f'[LOOP ERROR] {e}', flush=True)
        time.sleep(interval)

# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0].rstrip('/')
        params = {}
        if '?' in self.path:
            for part in self.path.split('?', 1)[1].split('&'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    params[k] = v

        if path in ('', '/'):
            if DASHBOARD_HTML.exists():
                html = DASHBOARD_HTML.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self._send_json({'error': 'dashboard.html lipsă'}, 404)

        elif path == '/api/status':
            with _state_lock:
                data = dict(_current)
            data['uptime_sec'] = int(time.time()) - data.get('uptime_start', int(time.time()))
            self._send_json(data)

        elif path == '/api/history':
            hours = int(params.get('hours', 24))
            self._send_json(get_history(hours))

        elif path == '/api/alerts':
            limit = int(params.get('limit', 50))
            self._send_json(get_alerts(limit))

        else:
            self._send_json({'error': 'not found'}, 404)

    def do_POST(self):
        path = self.path.rstrip('/')

        if path in ('/api/restart/node', '/api/restart/pool'):
            service = path.split('/')[-1]
            restart_cmd = cfg.get(service, {}).get('restart_cmd', '')
            if not restart_cmd:
                self._send_json({'error': f'restart_cmd pentru {service} nu e configurat'}, 400)
                return
            try:
                subprocess.run(restart_cmd, shell=True, timeout=30, check=True)
                alert('INFO', f'{service} restartat manual din dashboard.')
                self._send_json({'ok': True, 'cmd': restart_cmd})
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
        else:
            self._send_json({'error': 'not found'}, 404)

# ── main ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not CONFIG_PATH.exists():
        print(f'[ERROR] Config lipsă: {CONFIG_PATH}')
        print('        Copiază config.example.json în config.json și completează.')
        sys.exit(1)

    if not HAS_PSUTIL:
        print('[WARN] psutil nu este instalat — CPU%/RAM% indisponibile.')
        print('       pip3 install psutil')

    init_db()

    t = threading.Thread(target=update_loop, daemon=True)
    t.start()

    host = cfg.get('dashboard', {}).get('host', '127.0.0.1')
    port = int(cfg.get('dashboard', {}).get('port', 3003))
    print(f'[WebDollar Node Manager] Dashboard: http://{host}:{port}', flush=True)

    srv = ThreadingHTTPServer((host, port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nOprit.')
