#!/bin/bash
# Porneste ambele servicii (Telegram + WhatsApp)
cd "$(dirname "$0")"

pip3 install -r requirements.txt -q

echo "[bot] Pornire Telegram bot..."
python3 bot.py &
BOT_PID=$!

echo "[bot] Pornire WhatsApp webhook pe portul 5005..."
python3 whatsapp.py &
WA_PID=$!

echo "[bot] Telegram PID=$BOT_PID  WhatsApp PID=$WA_PID"

wait $BOT_PID $WA_PID
