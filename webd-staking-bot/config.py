import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN        = os.getenv('TELEGRAM_TOKEN', '')
TWILIO_ACCOUNT_SID    = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN     = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM  = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
WEBHOOK_URL           = os.getenv('WEBHOOK_URL', '')

STAKING_API_URL       = os.getenv('STAKING_API_URL', 'http://localhost:3004')
STAKING_API_SECRET    = os.getenv('STAKING_API_SECRET', '')
EXPLORER_API_URL      = os.getenv('EXPLORER_API_URL', 'https://explorer.webdollar.io')

# ── Tip bot staking (adresa proprie, separata de pool-ul principal) ───────────
TIP_BOT_ADDRESS = os.getenv('TIP_BOT_ADDRESS', os.getenv('BOT_WEBD_ADDRESS', ''))
TIP_BOT_SEED    = os.getenv('TIP_BOT_SEED', '')    # seed hex 64 chars (32 bytes)
TIP_BOT_PUBKEY  = os.getenv('TIP_BOT_PUBKEY', '')  # pubkey hex 64 chars

# ── Nod WEBD (pentru scanare blockchain si broadcast tx) ─────────────────────
NODE_URL        = os.getenv('NODE_URL', 'http://localhost:5555')
NODE_LOCAL_URL  = os.getenv('NODE_LOCAL_URL', 'http://127.0.0.1:8081')
BROADCAST_URL   = os.getenv('BROADCAST_URL', 'http://localhost:3001/tx/broadcast')
NODE_SECRET_KEY = os.getenv('NODE_SECRET_KEY', 'SECRET_SECRET_SECRET_LONG_SECRET_123456')

# ── Bot general ───────────────────────────────────────────────────────────────
BOT_WEBD_ADDRESS  = TIP_BOT_ADDRESS   # backward compat
ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', '0'))
TIP_FEE_PCT       = float(os.getenv('TIP_FEE_PCT', '0'))
MIN_TIP           = float(os.getenv('MIN_TIP', '1'))
MIN_WITHDRAW      = float(os.getenv('MIN_WITHDRAW', '20'))  # minim retragere (acoper taxa 10 WEBD)
DB_PATH           = os.getenv('DB_PATH', 'tipbot.db')

WHATSAPP_PORT = int(os.getenv('WHATSAPP_PORT', '5005'))
