#!/usr/bin/env python3
"""
WebDollar Staking Tip Bot — Telegram
"""
import asyncio, logging, re, time as _time
from collections import defaultdict
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

# ── Rate limiting ─────────────────────────────────────────────────────────────
_rl: dict = defaultdict(lambda: defaultdict(list))

def _rate_ok(cmd: str, uid: int, max_calls: int, window_sec: int) -> bool:
    now = _time.time()
    calls = [t for t in _rl[cmd][uid] if now - t < window_sec]
    _rl[cmd][uid] = calls
    if len(calls) >= max_calls:
        return False
    _rl[cmd][uid].append(now)
    return True

# ── Address validation ────────────────────────────────────────────────────────
_WEBD_RE = re.compile(r'^WEBD[\$A-Za-z0-9+/#@=]{35,45}$')

import db, api, staking
from config import (
    TELEGRAM_TOKEN, TIP_BOT_ADDRESS, ADMIN_TELEGRAM_ID,
    TIP_FEE_PCT, MIN_TIP, MIN_WITHDRAW,
)

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)
log = logging.getLogger('webd-bot')

# ── helpers ───────────────────────────────────────────────────────────────────

def fmt_webd(amount: float) -> str:
    return f"{amount:,.2f} WEBD"

def fmt_ts(ts: int) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M UTC')

def short_addr(addr: str) -> str:
    if not addr: return '—'
    return addr[:10] + '...' + addr[-6:]

async def reply(update: Update, text: str, parse_mode=ParseMode.HTML):
    await update.message.reply_text(text, parse_mode=parse_mode, disable_web_page_preview=True)

# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    name = u.first_name or u.username or 'prieten'
    await reply(update,
        f"👋 Bun venit, <b>{name}</b>!\n\n"
        f"🪙 Acesta este botul oficial <b>WebDollar Tip Bot</b>.\n"
        f"Poți trimite WEBD altor useri direct din Telegram.\n\n"
        f"Scrie /help pentru lista de comenzi."
    )

# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "⚙️ <b>Comenzi disponibile</b>\n\n"
        "💰 <b>Cont</b>\n"
        "  /tipbalance — balanța ta\n"
        "  /wallet — wallet WEBD setat\n"
        "  /setwallet ADRESA — setează wallet de retragere\n"
        "  /deposit — adresa pentru depunere WEBD\n"
        "  /withdraw SUMA — retrage WEBD la wallet-ul setat\n"
        "  /transactions — ultimele 10 tranzacții\n\n"
        "🎁 <b>Tips</b>\n"
        "  /tip @user SUMA — trimite WEBD unui user\n"
        "  /scoreboard — top 10 tipperi\n\n"
        "📊 <b>Staking &amp; Market</b>\n"
        "  /staking — rewards și APY pool\n"
        "  /price — prețul WEBD\n"
        "  /stats — statistici bot\n\n"
        "💳 <b>Altele</b>\n"
        "  /fees — informații comisioane\n"
        "  /topup — cumpără WEBD (în curând)"
    )

# ── /tipbalance ───────────────────────────────────────────────────────────────

async def cmd_tipbalance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    user = db.get_user(u.id)
    await reply(update,
        f"💰 <b>Balanța ta</b>\n\n"
        f"Disponibil:       <code>{fmt_webd(user['balance'])}</code>\n"
        f"Total primit:     <code>{fmt_webd(user['total_received'])}</code>\n"
        f"Total trimis:     <code>{fmt_webd(user['total_tipped'])}</code>\n"
        f"Tips date:        <b>{user['tips_given']}</b>\n"
        f"Tips primite:     <b>{user['tips_received']}</b>"
    )

# ── /wallet ───────────────────────────────────────────────────────────────────

async def cmd_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    wallet = db.get_wallet(u.id)
    if wallet:
        await reply(update,
            f"👛 <b>Wallet-ul tău WEBD</b>\n\n"
            f"<code>{wallet}</code>\n\n"
            f"Folosit pentru retrageri. Schimbă cu /setwallet ADRESA"
        )
    else:
        await reply(update,
            "❌ Nu ai setat un wallet WEBD.\n\n"
            "Folosește: <code>/setwallet WEBD$...</code>"
        )

# ── /setwallet ────────────────────────────────────────────────────────────────

async def cmd_setwallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    if not ctx.args:
        await reply(update, "Folosire: <code>/setwallet WEBD$...</code>")
        return
    if not _rate_ok('setwallet', u.id, 5, 86400):
        await reply(update, "⏳ Prea multe încercări. Reîncarcă mâine.")
        return
    wallet = ctx.args[0].strip()
    if not _WEBD_RE.match(wallet):
        await reply(update, "❌ Adresă WEBD invalidă. Formatul corect: <code>WEBD$...</code> (40 caractere).")
        return
    db.set_wallet(u.id, wallet)
    await reply(update,
        f"✅ <b>Wallet setat cu succes!</b>\n\n"
        f"<code>{wallet}</code>"
    )

# ── /deposit ──────────────────────────────────────────────────────────────────

async def cmd_deposit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    if not TIP_BOT_ADDRESS:
        await reply(update, "⚠️ Depunerile nu sunt configurate momentan. Contactează adminul.")
        return
    wallet = db.get_wallet(u.id)
    wallet_info = (
        f"\n✅ Wallet detectare: <code>{short_addr(wallet)}</code>\n"
        f"<i>Depunerile de la acest wallet sunt creditate automat.</i>"
        if wallet else
        f"\n⚠️ Nu ai setat un wallet! Folosește <code>/setwallet WEBD$...</code>\n"
        f"<i>Fără wallet setat, depunerile nu pot fi identificate automat.</i>"
    )
    await reply(update,
        f"📥 <b>Depunere WEBD în Tip Bot</b>\n\n"
        f"Trimite WEBD la adresa botului:\n"
        f"<code>{TIP_BOT_ADDRESS}</code>\n"
        f"{wallet_info}\n\n"
        f"✅ <b>Creditare automată</b> — botul scanează blockchain-ul la fiecare 30s.\n"
        f"WEBD-ul depus participă la <b>staking</b> și primești rewards proporțional."
    )

# ── /withdraw ─────────────────────────────────────────────────────────────────

async def cmd_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')

    wallet = db.get_wallet(u.id)
    if not wallet:
        await reply(update,
            "❌ Nu ai setat un wallet WEBD.\n"
            "Folosește mai întâi: <code>/setwallet WEBD$...</code>"
        )
        return

    if not ctx.args:
        balance = db.get_balance(u.id)
        await reply(update,
            f"Folosire: <code>/withdraw SUMA</code>\n\n"
            f"Balanță disponibilă: <b>{fmt_webd(balance)}</b>\n"
            f"Wallet destinație: <code>{short_addr(wallet)}</code>"
        )
        return

    if not _rate_ok('withdraw', u.id, 3, 3600):
        await reply(update, "⏳ Prea multe retrageri. Încearcă din nou în câteva minute.")
        return

    try:
        amount = float(ctx.args[0].replace(',', '.'))
        if not (0 < amount < 1_000_000) or amount != amount:
            raise ValueError
    except (ValueError, OverflowError):
        await reply(update, "❌ Sumă invalidă.")
        return

    fee = staking.TX_FEE_WEBD
    total_debit = amount + fee

    if amount < MIN_WITHDRAW:
        await reply(update,
            f"❌ Suma minimă pentru retragere: <b>{fmt_webd(MIN_WITHDRAW)}</b>\n"
            f"<i>(taxa rețea: {fmt_webd(fee)})</i>"
        )
        return

    balance = db.get_balance(u.id)
    if balance < total_debit:
        await reply(update,
            f"❌ Balanță insuficientă.\n"
            f"Disponibil: <b>{fmt_webd(balance)}</b>\n"
            f"Necesar (sumă + taxă): <b>{fmt_webd(total_debit)}</b>"
        )
        return

    # Debit imediat din DB pentru a preveni double-spend
    if not db.debit_withdraw(u.id, total_debit, wallet):
        await reply(update, "❌ Eroare la procesarea retragerii.")
        return

    withdraw_id = db.add_staking_withdrawal(u.id, amount, fee, wallet)
    await reply(update,
        f"⏳ <b>Procesare retragere...</b>\n\n"
        f"Sumă: <b>{fmt_webd(amount)}</b>\n"
        f"Taxă rețea: <b>{fmt_webd(fee)}</b>\n"
        f"Destinație: <code>{short_addr(wallet)}</code>"
    )

    result = await staking.execute_withdrawal(u.id, amount, wallet)

    if result.get('ok'):
        tx_id = result.get('tx_id', '')
        db.update_withdrawal_tx(withdraw_id, tx_id, 'sent')
        await reply(update,
            f"✅ <b>Retragere trimisă pe blockchain!</b>\n\n"
            f"Sumă: <b>{fmt_webd(amount)}</b>\n"
            f"TX: <code>{tx_id[:20]}...</code>\n"
            f"Destinație: <code>{short_addr(wallet)}</code>"
        )
    else:
        # Refund dacă tx a eșuat
        db.credit_deposit(u.id, total_debit, note='refund_failed_withdraw')
        db.update_withdrawal_tx(withdraw_id, '', 'failed')
        err = result.get('error', 'eroare necunoscută')
        await reply(update,
            f"❌ <b>Retragere eșuată</b>\n\n"
            f"Balanța a fost restituită.\n"
            f"Eroare: <i>{err}</i>"
        )
        if ADMIN_TELEGRAM_ID:
            try:
                await ctx.bot.send_message(
                    ADMIN_TELEGRAM_ID,
                    f"⚠️ Retragere eșuată:\nUser {u.id}, {fmt_webd(amount)}\nEroare: {err}"
                )
            except Exception:
                pass

# ── /tip ──────────────────────────────────────────────────────────────────────

async def cmd_tip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')

    if not _rate_ok('tip', u.id, 20, 3600):
        await reply(update, "⏳ Prea multe tips. Încearcă din nou mai târziu.")
        return

    if len(ctx.args) < 2:
        await reply(update, "Folosire: <code>/tip @username SUMA</code>")
        return

    target_raw = ctx.args[0].lstrip('@')
    try:
        amount = float(ctx.args[1].replace(',', '.'))
    except ValueError:
        await reply(update, "❌ Suma invalidă.")
        return

    if amount < MIN_TIP:
        await reply(update, f"❌ Suma minimă pentru tip: <b>{fmt_webd(MIN_TIP)}</b>")
        return

    if target_raw.lower() == (u.username or '').lower():
        await reply(update, "❌ Nu îți poți da tip ție însuți.")
        return

    recipient = db.get_user_by_username(target_raw)
    if not recipient:
        await reply(update,
            f"❌ Userul @{target_raw} nu a folosit botul încă.\n"
            f"Roagă-l să scrie /start mai întâi."
        )
        return

    balance = db.get_balance(u.id)
    if balance < amount:
        await reply(update,
            f"❌ Balanță insuficientă.\n"
            f"Disponibil: <b>{fmt_webd(balance)}</b>"
        )
        return

    fee = round(amount * TIP_FEE_PCT, 6)
    net = amount - fee

    if db.do_tip(u.id, recipient['telegram_id'], amount, fee):
        rec_name = recipient.get('first_name') or f"@{target_raw}"
        await reply(update,
            f"🎉 <b>Tip trimis!</b>\n\n"
            f"Destinatar: <b>{rec_name}</b> (@{target_raw})\n"
            f"Sumă: <b>{fmt_webd(net)}</b>"
            + (f"\nComision: {fmt_webd(fee)}" if fee > 0 else "")
        )
        # notifică destinatarul
        try:
            sender_name = u.first_name or f"@{u.username}"
            await ctx.bot.send_message(
                recipient['telegram_id'],
                f"🎁 Ai primit un tip de la <b>{sender_name}</b>!\n\n"
                f"Sumă: <b>{fmt_webd(net)}</b>\n"
                f"Balanță nouă: <b>{fmt_webd(db.get_balance(recipient['telegram_id']))}</b>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    else:
        await reply(update, "❌ Eroare la procesarea tipului.")

# ── /transactions ─────────────────────────────────────────────────────────────

async def cmd_transactions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    txs = db.get_transactions(u.id, limit=10)

    if not txs:
        await reply(update, "📋 Nu ai tranzacții încă.")
        return

    lines = ["📋 <b>Ultimele tranzacții</b>\n"]
    for tx in txs:
        ts    = fmt_ts(tx['created_at'])
        amt   = fmt_webd(tx['amount'])
        typ   = tx['type']
        if typ == 'tip':
            if tx['from_id'] == u.id:
                to_u = tx.get('to_username') or str(tx['to_id'])
                lines.append(f"📤 Tip → @{to_u}: <b>{amt}</b>  <i>{ts}</i>")
            else:
                fr_u = tx.get('from_username') or str(tx['from_id'])
                lines.append(f"📥 Tip ← @{fr_u}: <b>{amt}</b>  <i>{ts}</i>")
        elif typ == 'deposit':
            lines.append(f"⬇️ Depunere: <b>{amt}</b>  <i>{ts}</i>")
        elif typ == 'withdraw':
            lines.append(f"⬆️ Retragere: <b>{amt}</b>  <i>{ts}</i>")

    await reply(update, "\n".join(lines))

# ── /staking ──────────────────────────────────────────────────────────────────

async def cmd_staking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')

    bot_stats = db.get_staking_stats()
    user      = db.get_user(u.id)
    balance   = user['balance'] if user else 0.0
    total     = bot_stats['total_staked']

    pct = round(balance / total * 100, 2) if total > 0 else 0.0

    node = api.get_node_status()
    height = node.get('height', '—') if node else '—'

    await reply(update,
        f"⛏ <b>Tip Bot Staking</b>\n\n"
        f"👤 Balanța ta:         <b>{fmt_webd(balance)}</b>  ({pct:.2f}% din pool)\n"
        f"💰 Total în pool:      <b>{fmt_webd(total)}</b>\n"
        f"👥 Stakeri activi:     <b>{bot_stats['active_stakers']}</b>\n"
        f"🏆 Blocuri găsite:     <b>{bot_stats['blocks_found']}</b>\n"
        f"🎁 Total rewards:      <b>{fmt_webd(bot_stats['total_rewards'])}</b>\n"
        f"🔗 Bloc curent:        <b>{height}</b>\n\n"
        f"<i>Depune WEBD cu /deposit — rewards distribuite automat la fiecare bloc găsit.</i>"
    )

# ── /price ────────────────────────────────────────────────────────────────────

async def cmd_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    price_data = api.get_price()
    if not price_data:
        await reply(update,
            "⚠️ Date de preț indisponibile momentan.\n\n"
            "Verifică manual pe: https://webdollar.io"
        )
        return

    price  = price_data.get('price') or price_data.get('usd') or price_data.get('last', '—')
    vol    = price_data.get('volume') or price_data.get('vol_24h', '—')
    change = price_data.get('change_24h') or price_data.get('percent_change_24h', '—')

    arrow = ''
    if isinstance(change, (int, float)):
        arrow = '🟢' if change >= 0 else '🔴'
        change = f"{change:+.2f}%"

    await reply(update,
        f"💹 <b>Prețul WEBD</b>\n\n"
        f"Preț:         <b>${price}</b>\n"
        f"Volum 24h:    <b>{vol}</b>\n"
        f"Schimbare:    {arrow} <b>{change}</b>"
    )

# ── /stats ────────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = db.get_bot_stats()
    await reply(update,
        f"🤖 <b>Statistici Bot</b>\n\n"
        f"👥 Utilizatori înregistrați: <b>{s['total_users']}</b>\n"
        f"🎁 Total tips procesate:     <b>{s['total_tips']}</b>\n"
        f"💰 Volum total tips:         <b>{fmt_webd(s['total_volume'])}</b>"
    )

# ── /scoreboard ───────────────────────────────────────────────────────────────

async def cmd_scoreboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = db.get_top_tippers(10)
    if not top:
        await reply(update, "🏆 Nu există tipperi încă. Fii primul cu /tip!")
        return

    lines = ["🏆 <b>Top 10 Tipperi</b>\n"]
    medals = ['🥇','🥈','🥉'] + ['🏅'] * 7
    for i, t in enumerate(top):
        name = t.get('first_name') or t.get('username') or 'Anonim'
        if t.get('username'):
            name = f"@{t['username']}"
        lines.append(
            f"{medals[i]} <b>{name}</b>  —  {fmt_webd(t['total_tipped'])}  ({t['tips_given']} tips)"
        )
    await reply(update, "\n".join(lines))

# ── /fees ─────────────────────────────────────────────────────────────────────

async def cmd_fees(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fee_pct = TIP_FEE_PCT * 100
    await reply(update,
        f"💳 <b>Comisioane</b>\n\n"
        f"Tips:         <b>{'Gratuit' if fee_pct == 0 else f'{fee_pct:.1f}%'}</b>\n"
        f"Depunere:     <b>Gratuit</b>\n"
        f"Retragere:    <b>Gratuit</b> (taxe rețea WebDollar aplicate)\n\n"
        f"<i>Comisioanele pot fi modificate la discreția operatorului.</i>"
    )

# ── /topup ────────────────────────────────────────────────────────────────────

async def cmd_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "💳 <b>Cumpără WEBD</b>\n\n"
        "🚧 <i>Această funcție este în curs de dezvoltare.</i>\n\n"
        "Momentan poți achiziționa WEBD de pe:\n"
        "• <a href='https://webdollar.io'>webdollar.io</a>\n"
        "• Exchange-uri listate\n\n"
        "Apoi folosește /deposit pentru a depune în bot."
    )

# ── /admin credit (admin only) ───────────────────────────────────────────────

async def cmd_admin_credit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id != ADMIN_TELEGRAM_ID:
        await reply(update, "❌ Acces interzis.")
        return
    # /credit USER_ID SUMA
    if len(ctx.args) < 2:
        await reply(update, "Folosire: /credit USER_ID SUMA")
        return
    try:
        uid    = int(ctx.args[0])
        amount = float(ctx.args[1])
    except ValueError:
        await reply(update, "❌ Parametri invalizi.")
        return
    target = db.get_user(uid)
    if not target:
        await reply(update, f"❌ Userul {uid} nu există.")
        return
    db.credit_deposit(uid, amount, note='admin_credit')
    await reply(update, f"✅ Creditat {fmt_webd(amount)} → user {uid}")
    try:
        await ctx.bot.send_message(
            uid,
            f"✅ <b>{fmt_webd(amount)}</b> a fost creditat în contul tău de admin.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

# ── Main ──────────────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Porneste scan loop dupa ce botul este initializat."""
    asyncio.create_task(staking.scan_loop(app.bot))
    log.info('Scan loop pornit.')

def build_app() -> Application:
    db.init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler('start',        cmd_start))
    app.add_handler(CommandHandler('help',         cmd_help))
    app.add_handler(CommandHandler('tipbalance',   cmd_tipbalance))
    app.add_handler(CommandHandler('balance',      cmd_tipbalance))
    app.add_handler(CommandHandler('wallet',       cmd_wallet))
    app.add_handler(CommandHandler('setwallet',    cmd_setwallet))
    app.add_handler(CommandHandler('deposit',      cmd_deposit))
    app.add_handler(CommandHandler('withdraw',     cmd_withdraw))
    app.add_handler(CommandHandler('tip',          cmd_tip))
    app.add_handler(CommandHandler('transactions', cmd_transactions))
    app.add_handler(CommandHandler('staking',      cmd_staking))
    app.add_handler(CommandHandler('price',        cmd_price))
    app.add_handler(CommandHandler('stats',        cmd_stats))
    app.add_handler(CommandHandler('scoreboard',   cmd_scoreboard))
    app.add_handler(CommandHandler('fees',         cmd_fees))
    app.add_handler(CommandHandler('topup',        cmd_topup))
    app.add_handler(CommandHandler('credit',       cmd_admin_credit))
    return app

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print('EROARE: TELEGRAM_TOKEN nu este setat în .env')
        exit(1)
    log.info('Bot Telegram pornit...')
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
