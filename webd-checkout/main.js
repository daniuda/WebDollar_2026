// webd-checkout main.js
// Detectează automat dacă e în modul merchant (fără params) sau checkout activ (cu params).

const API_BASE = '';  // relativ — server.js servește și frontend-ul

(function () {
  const params  = new URLSearchParams(window.location.search);
  const address = params.get('to');
  const amount  = parseFloat(params.get('amount'));
  const redirect = params.get('redirect') || null;
  const timeout  = Number(params.get('timeout')) || 0;

  if (address && amount > 0) {
    startCheckout(address, amount, redirect, timeout);
  } else {
    showConfigForm();
  }
})();

// ── Config form (mod merchant) ───────────────────────────────────────────────

function showConfigForm() {
  document.getElementById('config-form').style.display = 'block';
  document.getElementById('checkout-view').style.display = 'none';

  document.getElementById('merchant-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const addr = document.getElementById('cfg-address').value.trim();
    const amt  = document.getElementById('cfg-amount').value;
    if (!addr || !amt) return;
    const url = `${window.location.origin}${window.location.pathname}?to=${encodeURIComponent(addr)}&amount=${amt}`;
    const box = document.getElementById('generated-link');
    const display = document.getElementById('link-display');
    display.textContent = url;
    box.style.display = 'block';
  });

  document.getElementById('copy-link-btn').addEventListener('click', () => {
    const text = document.getElementById('link-display').textContent;
    navigator.clipboard.writeText(text).then(() => {
      document.getElementById('copy-link-btn').textContent = 'Copiat!';
      setTimeout(() => { document.getElementById('copy-link-btn').textContent = 'Copiază link'; }, 2000);
    });
  });
}

// ── Checkout activ ───────────────────────────────────────────────────────────

async function startCheckout(address, amount, redirect, timeoutOverride) {
  document.getElementById('config-form').style.display = 'none';
  document.getElementById('checkout-view').style.display = 'block';

  document.getElementById('amount-display').textContent = `${amount} WEBD`;
  document.getElementById('qr-address').textContent = address;

  // Generează QR
  generateQR(address, amount);

  // Creează sesiune la backend
  let sessionId = null;
  let expiresAt = Date.now() + (timeoutOverride || 600_000);

  try {
    const body = { address, amount };
    if (timeoutOverride) body.timeout = timeoutOverride;
    const res  = await fetch(`${API_BASE}/api/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const data = await res.json();
      sessionId = data.id;
      expiresAt = data.expires;
    }
  } catch (e) {
    console.warn('Backend indisponibil, modul QR static activ:', e.message);
  }

  startCountdown(expiresAt);

  if (sessionId) {
    pollStatus(sessionId, expiresAt, redirect);
  } else {
    // Fără backend: rămâne în stare statică de așteptare
    setStatus('waiting');
  }
}

function generateQR(address, amount) {
  const qrText = `webd:${address}?amount=${amount}`;
  const qrDiv  = document.getElementById('qrcode');
  qrDiv.innerHTML = '';
  const qr = qrcode(0, 'L');
  qr.addData(qrText);
  qr.make();
  qrDiv.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2 });
}

// ── Polling ──────────────────────────────────────────────────────────────────

let _pollTimer = null;

async function pollStatus(sessionId, expiresAt, redirect) {
  if (Date.now() > expiresAt) { setStatus('expired'); return; }

  try {
    const res = await fetch(`${API_BASE}/api/session/${sessionId}`);
    if (res.ok) {
      const data = await res.json();
      setStatus(data.status, data.txId);
      if (data.status === 'confirmed') {
        if (redirect) setTimeout(() => { window.location.href = redirect; }, 3000);
        return;
      }
      if (data.status === 'expired') return;
    }
  } catch (e) {
    console.warn('Poll error:', e.message);
  }

  _pollTimer = setTimeout(() => pollStatus(sessionId, expiresAt, redirect), 10_000);
}

// ── UI helpers ───────────────────────────────────────────────────────────────

function setStatus(status, txId) {
  const box      = document.getElementById('status-box');
  const text     = document.getElementById('status-text');
  const spinner  = document.getElementById('spinner');
  const check    = document.getElementById('checkmark');
  const cross    = document.getElementById('crossmark');
  const txBox    = document.getElementById('txid-box');

  box.className = `status-box status-${status}`;
  spinner.style.display = 'none';
  check.style.display   = 'none';
  cross.style.display   = 'none';

  switch (status) {
    case 'waiting':
      spinner.style.display = 'block';
      text.textContent = 'Așteptăm plata...';
      break;
    case 'detected':
      spinner.style.display = 'block';
      text.textContent = 'Plată detectată! Se confirmă...';
      break;
    case 'confirmed':
      check.style.display = 'block';
      text.textContent = 'Plată confirmată!';
      if (txId) {
        document.getElementById('txid-value').textContent = txId;
        txBox.style.display = 'block';
      }
      break;
    case 'expired':
      cross.style.display = 'block';
      text.textContent = 'Sesiunea a expirat.';
      if (_pollTimer) clearTimeout(_pollTimer);
      break;
  }
}

let _countdownTimer = null;

function startCountdown(expiresAt) {
  const el = document.getElementById('countdown');
  function tick() {
    const ms = Math.max(0, expiresAt - Date.now());
    const min = Math.floor(ms / 60_000);
    const sec = Math.floor((ms % 60_000) / 1000);
    el.textContent = ms > 0
      ? `Timp rămas: ${min}:${sec.toString().padStart(2, '0')}`
      : 'Expirat';
    if (ms > 0) _countdownTimer = setTimeout(tick, 1000);
  }
  tick();
}
