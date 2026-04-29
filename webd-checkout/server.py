from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# ── Config defaults (suprascrise din args/env) ───────────────────────────────
DEFAULT_NODE_URL    = "https://webdollar.io"
DEFAULT_PORT        = 3002
DEFAULT_TIMEOUT_MS  = 600_000   # 10 minute
POLL_INTERVAL_S     = 15        # interval polling nod

# ── In-memory session store ──────────────────────────────────────────────────
# { id: { id, address, amount_webd, status, initial_balance, current_balance,
#          tx_id, created_at, expires_at, detected_at, confirmed_at,
#          _confirm_count } }
_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()

NODE_URL    = DEFAULT_NODE_URL
TIMEOUT_MS  = DEFAULT_TIMEOUT_MS
APP_DIR     = Path(__file__).resolve().parent


# ── WebDollar node helpers ───────────────────────────────────────────────────

def _fetch_json(url: str, timeout: int = 8) -> Any:
    """Fetch JSON de la un URL; incearca si cu SSL unverified ca fallback."""
    headers = {"User-Agent": "webd-checkout/1.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read().decode("utf-8"))
        raise


def fetch_balance(address: str) -> float | None:
    """Incearca mai multe endpoint-uri pentru a obtine balanta adresei."""
    base = NODE_URL.rstrip("/")
    endpoints = [
        f"{base}/address/{address}/balance",
        f"{base}/wallet/{address}",
        f"{base}/api/address/{address}",
    ]
    for url in endpoints:
        try:
            data = _fetch_json(url)
            if not isinstance(data, dict):
                continue
            raw = (data.get("balance") or data.get("amount") or
                   data.get("total") or data.get("webd"))
            if raw is not None:
                return float(raw)
        except Exception:
            pass
    return None


def fetch_recent_tx_id(address: str) -> str | None:
    """Cauta un tx catre adresa in ultimele 5 blocuri."""
    base = NODE_URL.rstrip("/")
    try:
        height_data = _fetch_json(f"{base}/height")
        height = int(height_data.get("height", 0))
        for h in range(height, max(height - 5, 0), -1):
            block = _fetch_json(f"{base}/block/{h}")
            for tx in (block.get("transactions") or block.get("txs") or []):
                to_addr = (tx.get("to") or {}).get("address") or tx.get("toAddress") or tx.get("recipient", "")
                if to_addr == address:
                    return tx.get("id") or tx.get("txId") or tx.get("hash") or f"block-{h}"
    except Exception:
        pass
    return None


# ── Session helpers ──────────────────────────────────────────────────────────

def create_session(address: str, amount_webd: float, timeout_ms: int | None = None) -> dict[str, Any]:
    sid = secrets.token_hex(12)
    now_ms = int(time.time() * 1000)
    expires = now_ms + (timeout_ms or TIMEOUT_MS)
    session: dict[str, Any] = {
        "id": sid,
        "address": address,
        "amount_webd": amount_webd,
        "status": "waiting",
        "initial_balance": None,
        "current_balance": None,
        "tx_id": None,
        "created_at": now_ms,
        "expires_at": expires,
        "detected_at": None,
        "confirmed_at": None,
        "_confirm_count": 0,
    }
    with _sessions_lock:
        _sessions[sid] = session
    # Snapshot balanță inițial
    bal = fetch_balance(address)
    if bal is not None:
        with _sessions_lock:
            session["initial_balance"] = bal
    return session


def get_session(sid: str) -> dict[str, Any] | None:
    with _sessions_lock:
        return _sessions.get(sid)


def _poll_one(session: dict[str, Any]) -> None:
    now_ms = int(time.time() * 1000)
    if session["status"] in ("confirmed", "expired"):
        return
    if now_ms > session["expires_at"]:
        session["status"] = "expired"
        return

    bal = fetch_balance(session["address"])
    if bal is not None:
        if session["initial_balance"] is None:
            session["initial_balance"] = bal
        session["current_balance"] = bal
        delta = bal - session["initial_balance"]

        if session["status"] == "waiting" and delta >= session["amount_webd"]:
            session["status"] = "detected"
            session["detected_at"] = now_ms
            tx_id = fetch_recent_tx_id(session["address"])
            if tx_id:
                session["tx_id"] = tx_id

        if session["status"] == "detected":
            session["_confirm_count"] += 1
            if session["_confirm_count"] >= 2:
                session["status"] = "confirmed"
                session["confirmed_at"] = now_ms
    else:
        # Fallback: scanare tx directa daca balanta nu e disponibila
        if session["status"] == "waiting":
            tx_id = fetch_recent_tx_id(session["address"])
            if tx_id:
                session["status"] = "detected"
                session["tx_id"] = tx_id
                session["detected_at"] = now_ms


def _poll_all_sessions() -> None:
    """Background thread: polling la interval fix pentru sesiunile active."""
    cutoff_2h = 2 * 60 * 60 * 1000
    while True:
        time.sleep(POLL_INTERVAL_S)
        now_ms = int(time.time() * 1000)
        with _sessions_lock:
            to_delete = [sid for sid, s in _sessions.items() if now_ms - s["created_at"] > cutoff_2h]
            for sid in to_delete:
                del _sessions[sid]
            active = [s for s in _sessions.values() if s["status"] not in ("confirmed", "expired")]

        for session in active:
            try:
                _poll_one(session)
            except Exception:
                pass


# ── HTTP Handler ─────────────────────────────────────────────────────────────

class CheckoutHandler(BaseHTTPRequestHandler):

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API: GET /api/session/<id>
        if path.startswith("/api/session/"):
            sid = path[len("/api/session/"):]
            session = get_session(sid)
            if not session:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Sesiune negăsită"})
                return
            remaining = max(0, session["expires_at"] - int(time.time() * 1000))
            self._json(HTTPStatus.OK, {
                "status":      session["status"],
                "txId":        session["tx_id"],
                "remaining":   remaining,
                "address":     session["address"],
                "amount":      session["amount_webd"],
                "detectedAt":  session["detected_at"],
                "confirmedAt": session["confirmed_at"],
            })
            return

        # Fișiere statice
        if path == "/" or path == "":
            path = "/index.html"
        file_path = APP_DIR / path.lstrip("/")
        self._serve_file(file_path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        # API: POST /api/session
        if parsed.path == "/api/session":
            try:
                body = self._read_json()
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            address = str(body.get("address", "")).strip()
            amount_raw = body.get("amount")
            timeout_raw = body.get("timeout")

            if not address or amount_raw is None:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "address și amount sunt obligatorii"})
                return
            try:
                amount_webd = float(amount_raw)
                if amount_webd <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "amount trebuie să fie număr pozitiv"})
                return

            timeout_ms = int(timeout_raw) if timeout_raw else None
            session = create_session(address, amount_webd, timeout_ms)

            self._json(HTTPStatus.OK, {
                "id":      session["id"],
                "qrData":  f"webd:{address}?amount={amount_webd}",
                "expires": session["expires_at"],
                "status":  session["status"],
            })
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    # ── helpers ──────────────────────────────────────────────────────────────

    def _serve_file(self, file_path: Path) -> None:
        if not file_path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        mime, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("Payload trebuie să fie obiect JSON")
        return payload

    def log_message(self, format: str, *args: Any) -> None:
        return  # silent logging


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    global NODE_URL, TIMEOUT_MS

    parser = argparse.ArgumentParser(description="webd-checkout payment server")
    parser.add_argument("--host",        default="127.0.0.1")
    parser.add_argument("--port",        type=int, default=DEFAULT_PORT)
    parser.add_argument("--node-url",    default=os.environ.get("NODE_URL", DEFAULT_NODE_URL))
    parser.add_argument("--timeout-ms",  type=int, default=int(os.environ.get("PAYMENT_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)))
    args = parser.parse_args()

    NODE_URL   = args.node_url.rstrip("/")
    TIMEOUT_MS = args.timeout_ms

    # Pornire thread polling sesiuni
    t = threading.Thread(target=_poll_all_sessions, daemon=True, name="session-poller")
    t.start()

    server = ThreadingHTTPServer((args.host, args.port), CheckoutHandler)
    print(f"webd-checkout listening on {args.host}:{args.port} | node: {NODE_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
