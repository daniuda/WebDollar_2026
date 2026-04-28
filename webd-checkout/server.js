import express from 'express';
import cors from 'cors';
import fetch from 'node-fetch';
import { randomBytes } from 'crypto';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

const NODE_URL     = (process.env.NODE_URL     || 'https://webdollar.io').replace(/\/$/, '');
const PORT         = Number(process.env.PORT)         || 3002;
const TIMEOUT_MS   = Number(process.env.PAYMENT_TIMEOUT_MS) || 600_000; // 10 min
const CORS_ORIGIN  = process.env.CORS_ORIGIN  || '*';
const POLL_MS      = 15_000; // 15s between node queries

// ── In-memory session store ──────────────────────────────────────────────────
// session: { id, address, amountWebd, status, initialBalance, currentBalance,
//            txId, createdAt, expiresAt, confirmedAt, detectedAt }
const sessions = new Map();

function newId() { return randomBytes(12).toString('hex'); }

// ── WebDollar node helpers ───────────────────────────────────────────────────

async function fetchBalance(address) {
  // Try modern endpoint first, then legacy fallback
  const endpoints = [
    `${NODE_URL}/address/${address}/balance`,
    `${NODE_URL}/wallet/${address}`,
    `${NODE_URL}/api/address/${address}`,
  ];
  for (const url of endpoints) {
    try {
      const res = await fetch(url, { timeout: 8000 });
      if (!res.ok) continue;
      const data = await res.json();
      // Normalize: balance may be in .balance, .amount, .total, .webd
      const raw = data.balance ?? data.amount ?? data.total ?? data.webd ?? null;
      if (raw !== null) return Number(raw);
    } catch { /* try next */ }
  }
  return null;
}

async function fetchRecentTx(address, afterHeight) {
  // Try to find a tx to `address` in recent blocks
  try {
    const hRes = await fetch(`${NODE_URL}/height`, { timeout: 5000 });
    if (!hRes.ok) return null;
    const { height } = await hRes.json();
    // Check last 5 blocks
    const from = Math.max(1, afterHeight || height - 5);
    for (let h = height; h >= from; h--) {
      const bRes = await fetch(`${NODE_URL}/block/${h}`, { timeout: 5000 });
      if (!bRes.ok) continue;
      const block = await bRes.json();
      const txs = block.transactions || block.txs || [];
      for (const tx of txs) {
        const toAddr = tx.to?.address || tx.toAddress || tx.recipient;
        if (toAddr === address) return tx.id || tx.txId || tx.hash || `block-${h}`;
      }
    }
  } catch { /* silent */ }
  return null;
}

// ── Background poller ────────────────────────────────────────────────────────

async function pollSession(session) {
  if (session.status === 'confirmed' || session.status === 'expired') return;

  if (Date.now() > session.expiresAt) {
    session.status = 'expired';
    return;
  }

  // Balance-based detection
  const balance = await fetchBalance(session.address);
  if (balance !== null) {
    if (session.initialBalance === null) {
      session.initialBalance = balance;
    }
    session.currentBalance = balance;
    const delta = balance - session.initialBalance;

    if (session.status === 'waiting' && delta >= session.amountWebd) {
      session.status = 'detected';
      session.detectedAt = Date.now();
      // Try to find txId
      const txId = await fetchRecentTx(session.address, null);
      if (txId) session.txId = txId;
    }

    if (session.status === 'detected') {
      // Confirm after one more successful balance check (next poll cycle)
      if (session._detectedConfirmCount === undefined) {
        session._detectedConfirmCount = 0;
      }
      session._detectedConfirmCount++;
      if (session._detectedConfirmCount >= 2) {
        session.status = 'confirmed';
        session.confirmedAt = Date.now();
      }
    }
  } else {
    // Fallback: try tx scan even without balance
    if (session.status === 'waiting') {
      const txId = await fetchRecentTx(session.address, null);
      if (txId) {
        session.status = 'detected';
        session.txId = txId;
        session.detectedAt = Date.now();
      }
    }
  }
}

setInterval(async () => {
  for (const session of sessions.values()) {
    if (session.status === 'confirmed' || session.status === 'expired') continue;
    await pollSession(session);
  }
  // Clean sessions older than 2h
  const cutoff = Date.now() - 2 * 60 * 60 * 1000;
  for (const [id, s] of sessions.entries()) {
    if (s.createdAt < cutoff) sessions.delete(id);
  }
}, POLL_MS);

// ── Express app ──────────────────────────────────────────────────────────────

const app = express();
app.use(cors({ origin: CORS_ORIGIN }));
app.use(express.json());
app.use(express.static(__dirname));  // serves index.html, main.js, style.css

/** POST /api/session
 *  Body: { address: string, amount: number, timeout?: number }
 *  Returns: { id, qrData, expires, status }
 */
app.post('/api/session', async (req, res) => {
  const { address, amount, timeout } = req.body || {};
  if (!address || !amount || isNaN(Number(amount)) || Number(amount) <= 0) {
    return res.status(400).json({ error: 'address și amount sunt obligatorii' });
  }
  const amountWebd = Number(amount);
  const timeoutMs  = Number(timeout) || TIMEOUT_MS;
  const id = newId();
  const now = Date.now();
  const session = {
    id,
    address,
    amountWebd,
    status: 'waiting',
    initialBalance: null,
    currentBalance: null,
    txId: null,
    createdAt: now,
    expiresAt: now + timeoutMs,
    detectedAt: null,
    confirmedAt: null,
  };
  sessions.set(id, session);
  // Take initial balance snapshot immediately
  const bal = await fetchBalance(address);
  if (bal !== null) session.initialBalance = bal;

  res.json({
    id,
    qrData: `webd:${address}?amount=${amountWebd}`,
    expires: session.expiresAt,
    status: session.status,
  });
});

/** GET /api/session/:id
 *  Returns: { status, txId?, remaining, confirmations? }
 */
app.get('/api/session/:id', (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session) return res.status(404).json({ error: 'Sesiune negăsită' });
  const remaining = Math.max(0, session.expiresAt - Date.now());
  res.json({
    status: session.status,
    txId: session.txId || null,
    remaining,
    address: session.address,
    amount: session.amountWebd,
    detectedAt: session.detectedAt,
    confirmedAt: session.confirmedAt,
  });
});

app.listen(PORT, () => {
  console.log(`webd-checkout server pornit pe http://localhost:${PORT}`);
  console.log(`Node WebDollar: ${NODE_URL}`);
});
