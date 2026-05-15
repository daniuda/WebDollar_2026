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

def compute_fee(amount: float) -> float:
    """Network base fee (10) + 1% service fee, total capped at 375 WEBD."""
    return min(10.0 + amount * 0.01, 375.0)

async def reply(update: Update, text: str, parse_mode=ParseMode.HTML):
    await update.message.reply_text(text, parse_mode=parse_mode, disable_web_page_preview=True)

# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    name = u.first_name or u.username or 'friend'
    await reply(update,
        f"👋 Welcome, <b>{name}</b>!\n\n"
        f"🪙 This is the <b>WebDollar Tip Bot</b>.\n"
        f"You can send WEBD to other users directly from Telegram.\n\n"
        f"Type /help for the list of commands."
    )

# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "⚙️ <b>Available Commands</b>\n\n"
        "💰 <b>Account</b>\n"
        "  /tipbalance — your balance\n"
        "  /wallet — your WEBD withdrawal wallet\n"
        "  /setwallet ADDRESS — set withdrawal wallet\n"
        "  /deposit — deposit address for WEBD\n"
        "  /withdraw AMOUNT — withdraw WEBD to your wallet\n"
        "  /transactions — last 10 transactions\n\n"
        "🎁 <b>Tips</b>\n"
        "  /tip @user AMOUNT — send WEBD to a user\n"
        "  /scoreboard — top 10 tippers\n\n"
        "📊 <b>Staking &amp; Market</b>\n"
        "  /staking — pool rewards and stats\n"
        "  /miner — miner status and blocks found\n"
        "  /price — WEBD price\n"
        "  /stats — bot statistics\n\n"
        "💳 <b>Other</b>\n"
        "  /fees — fee information\n"
        "  /topup — buy WEBD (coming soon)"
    )

# ── /tipbalance ───────────────────────────────────────────────────────────────

async def cmd_tipbalance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    user = db.get_user(u.id)
    await reply(update,
        f"💰 <b>Your Balance</b>\n\n"
        f"Available:        <code>{fmt_webd(user['balance'])}</code>\n"
        f"Total received:   <code>{fmt_webd(user['total_received'])}</code>\n"
        f"Total sent:       <code>{fmt_webd(user['total_tipped'])}</code>\n"
        f"Tips given:       <b>{user['tips_given']}</b>\n"
        f"Tips received:    <b>{user['tips_received']}</b>"
    )

# ── /wallet ───────────────────────────────────────────────────────────────────

async def cmd_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    wallet = db.get_wallet(u.id)
    if wallet:
        await reply(update,
            f"👛 <b>Your WEBD Wallet</b>\n\n"
            f"<code>{wallet}</code>\n\n"
            f"Used for withdrawals. Change with /setwallet ADDRESS"
        )
    else:
        await reply(update,
            "❌ You have not set a WEBD wallet.\n\n"
            "Use: <code>/setwallet WEBD$...</code>"
        )

# ── /setwallet ────────────────────────────────────────────────────────────────

async def cmd_setwallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    if not ctx.args:
        await reply(update, "Usage: <code>/setwallet WEBD$...</code>")
        return
    if not _rate_ok('setwallet', u.id, 5, 86400):
        await reply(update, "⏳ Too many attempts. Try again tomorrow.")
        return
    wallet = ctx.args[0].strip()
    if not _WEBD_RE.match(wallet):
        await reply(update, "❌ Invalid WEBD address. Expected format: <code>WEBD$...</code> (40 characters).")
        return
    db.set_wallet(u.id, wallet)
    await reply(update,
        f"✅ <b>Wallet set successfully!</b>\n\n"
        f"<code>{wallet}</code>"
    )

# ── /deposit ──────────────────────────────────────────────────────────────────

async def cmd_deposit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    if not TIP_BOT_ADDRESS:
        await reply(update, "⚠️ Deposits are not configured. Contact the admin.")
        return
    wallet = db.get_wallet(u.id)
    wallet_info = (
        f"\n✅ Detection wallet: <code>{short_addr(wallet)}</code>\n"
        f"<i>Deposits from this wallet are credited automatically.</i>"
        if wallet else
        f"\n⚠️ You have not set a wallet! Use <code>/setwallet WEBD$...</code>\n"
        f"<i>Without a wallet set, deposits cannot be identified automatically.</i>"
    )
    await reply(update,
        f"📥 <b>Deposit WEBD to Tip Bot</b>\n\n"
        f"Send WEBD to the bot address:\n"
        f"<code>{TIP_BOT_ADDRESS}</code>\n"
        f"{wallet_info}\n\n"
        f"✅ <b>Auto-credited</b> — the bot scans the blockchain every 30s.\n"
        f"Deposited WEBD participates in <b>staking</b> and you earn rewards proportionally."
    )

# ── /withdraw ─────────────────────────────────────────────────────────────────

async def cmd_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')

    wallet = db.get_wallet(u.id)
    if not wallet:
        await reply(update,
            "❌ You have not set a WEBD wallet.\n"
            "Use first: <code>/setwallet WEBD$...</code>"
        )
        return

    if not ctx.args:
        balance = db.get_balance(u.id)
        await reply(update,
            f"Usage: <code>/withdraw AMOUNT</code>\n\n"
            f"Available balance: <b>{fmt_webd(balance)}</b>\n"
            f"Destination wallet: <code>{short_addr(wallet)}</code>"
        )
        return

    if not _rate_ok('withdraw', u.id, 3, 3600):
        await reply(update, "⏳ Too many withdrawals. Try again in a few minutes.")
        return

    try:
        amount = float(ctx.args[0].replace(',', '.'))
        if not (0 < amount < 1_000_000) or amount != amount:
            raise ValueError
    except (ValueError, OverflowError):
        await reply(update, "❌ Invalid amount.")
        return

    fee = compute_fee(amount)
    total_debit = amount + fee

    if amount < MIN_WITHDRAW:
        await reply(update,
            f"❌ Minimum withdrawal amount: <b>{fmt_webd(MIN_WITHDRAW)}</b>\n"
            f"<i>(fee: {fmt_webd(fee)})</i>"
        )
        return

    balance = db.get_balance(u.id)
    if balance < total_debit:
        await reply(update,
            f"❌ Insufficient balance.\n"
            f"Available: <b>{fmt_webd(balance)}</b>\n"
            f"Required (amount + fee): <b>{fmt_webd(total_debit)}</b>"
        )
        return

    if not db.debit_withdraw(u.id, total_debit, wallet):
        await reply(update, "❌ Error processing withdrawal.")
        return

    withdraw_id = db.add_staking_withdrawal(u.id, amount, fee, wallet)
    net_fee = staking.TX_FEE_WEBD
    service_fee = round(fee - net_fee, 6)
    await reply(update,
        f"⏳ <b>Processing withdrawal...</b>\n\n"
        f"Amount: <b>{fmt_webd(amount)}</b>\n"
        f"Fee: <b>{fmt_webd(fee)}</b>"
        + (f" (10 network + {fmt_webd(service_fee)} service)" if service_fee > 0 else "") +
        f"\nDestination: <code>{short_addr(wallet)}</code>"
    )

    result = await staking.execute_withdrawal(u.id, amount, wallet)

    if result.get('ok'):
        tx_id = result.get('tx_id', '')
        db.update_withdrawal_tx(withdraw_id, tx_id, 'sent')
        await reply(update,
            f"✅ <b>Withdrawal sent to blockchain!</b>\n\n"
            f"Amount: <b>{fmt_webd(amount)}</b>\n"
            f"TX: <code>{tx_id[:20]}...</code>\n"
            f"Destination: <code>{short_addr(wallet)}</code>"
        )
    else:
        db.credit_deposit(u.id, total_debit, note='refund_failed_withdraw')
        db.update_withdrawal_tx(withdraw_id, '', 'failed')
        err = result.get('error', 'unknown error')
        await reply(update,
            f"❌ <b>Withdrawal failed</b>\n\n"
            f"Your balance has been refunded.\n"
            f"Error: <i>{err}</i>"
        )
        if ADMIN_TELEGRAM_ID:
            try:
                await ctx.bot.send_message(
                    ADMIN_TELEGRAM_ID,
                    f"⚠️ Withdrawal failed:\nUser {u.id}, {fmt_webd(amount)}\nError: {err}"
                )
            except Exception:
                pass

# ── /tip ──────────────────────────────────────────────────────────────────────

async def cmd_tip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')

    if not _rate_ok('tip', u.id, 20, 3600):
        await reply(update, "⏳ Too many tips. Try again later.")
        return

    if len(ctx.args) < 2:
        await reply(update, "Usage: <code>/tip @username AMOUNT</code>")
        return

    target_raw = ctx.args[0].lstrip('@')
    try:
        amount = float(ctx.args[1].replace(',', '.'))
    except ValueError:
        await reply(update, "❌ Invalid amount.")
        return

    if amount < MIN_TIP:
        await reply(update, f"❌ Minimum tip amount: <b>{fmt_webd(MIN_TIP)}</b>")
        return

    if target_raw.lower() == (u.username or '').lower():
        await reply(update, "❌ You cannot tip yourself.")
        return

    recipient = db.get_user_by_username(target_raw)
    if not recipient:
        await reply(update,
            f"❌ User @{target_raw} has not used the bot yet.\n"
            f"Ask them to type /start first."
        )
        return

    balance = db.get_balance(u.id)
    if balance < amount:
        await reply(update,
            f"❌ Insufficient balance.\n"
            f"Available: <b>{fmt_webd(balance)}</b>"
        )
        return

    fee = round(amount * TIP_FEE_PCT, 6)
    net = amount - fee

    if db.do_tip(u.id, recipient['telegram_id'], amount, fee):
        rec_name = recipient.get('first_name') or f"@{target_raw}"
        await reply(update,
            f"🎉 <b>Tip sent!</b>\n\n"
            f"Recipient: <b>{rec_name}</b> (@{target_raw})\n"
            f"Amount: <b>{fmt_webd(net)}</b>"
            + (f"\nFee: {fmt_webd(fee)}" if fee > 0 else "")
        )
        try:
            sender_name = u.first_name or f"@{u.username}"
            await ctx.bot.send_message(
                recipient['telegram_id'],
                f"🎁 You received a tip from <b>{sender_name}</b>!\n\n"
                f"Amount: <b>{fmt_webd(net)}</b>\n"
                f"New balance: <b>{fmt_webd(db.get_balance(recipient['telegram_id']))}</b>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    else:
        await reply(update, "❌ Error processing tip.")

# ── /transactions ─────────────────────────────────────────────────────────────

async def cmd_transactions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.ensure_user(u.id, u.username or '', u.first_name or '')
    txs = db.get_transactions(u.id, limit=10)

    if not txs:
        await reply(update, "📋 No transactions yet.")
        return

    lines = ["📋 <b>Last Transactions</b>\n"]
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
            lines.append(f"⬇️ Deposit: <b>{amt}</b>  <i>{ts}</i>")
        elif typ == 'withdraw':
            lines.append(f"⬆️ Withdrawal: <b>{amt}</b>  <i>{ts}</i>")

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
        f"👤 Your balance:       <b>{fmt_webd(balance)}</b>  ({pct:.2f}% of pool)\n"
        f"💰 Total in pool:      <b>{fmt_webd(total)}</b>\n"
        f"👥 Active stakers:     <b>{bot_stats['active_stakers']}</b>\n"
        f"🏆 Blocks found:       <b>{bot_stats['blocks_found']}</b>\n"
        f"🎁 Total rewards:      <b>{fmt_webd(bot_stats['total_rewards'])}</b>\n"
        f"🔗 Current block:      <b>{height}</b>\n\n"
        f"<i>Deposit WEBD with /deposit — rewards distributed automatically each block found.</i>"
    )

# ── /miner ───────────────────────────────────────────────────────────────────

async def cmd_miner(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from config import TIP_BOT_ADDRESS, NODE_LOCAL_URL
    import urllib.parse, staking as _staking

    top_data   = await asyncio.to_thread(_staking._get, f'{NODE_LOCAL_URL}/top')
    height     = top_data.get('top', '—') if isinstance(top_data, dict) else '—'
    synced     = top_data.get('is_synchronized', False) if isinstance(top_data, dict) else False
    behind     = top_data.get('secondsBehind', 0) if isinstance(top_data, dict) else 0

    addr_enc   = urllib.parse.quote(TIP_BOT_ADDRESS, safe='')
    bal_data   = await asyncio.to_thread(_staking._get, f'{NODE_LOCAL_URL}/address/balance/{addr_enc}')
    on_chain   = bal_data.get('balance', 0) if isinstance(bal_data, dict) else 0

    bot_stats  = db.get_staking_stats()
    blocks     = bot_stats.get('blocks_found', 0)
    rewards    = bot_stats.get('total_rewards', 0.0)

    sync_icon  = '🟢' if synced and behind < 120 else '🟡' if behind < 600 else '🔴'
    behind_str = f'{int(behind)}s behind' if behind else 'live'

    await reply(update,
        f"⛏ <b>Miner Status</b>\n\n"
        f"🔗 Current block:      <b>{height}</b>  {sync_icon} {behind_str}\n"
        f"💰 Miner wallet:       <b>{fmt_webd(on_chain)}</b>\n"
        f"🏆 Blocks found:       <b>{blocks}</b>\n"
        f"🎁 Total mined:        <b>{fmt_webd(rewards)}</b>\n\n"
        f"<code>{TIP_BOT_ADDRESS}</code>"
    )

# ── /price ────────────────────────────────────────────────────────────────────

async def cmd_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    price_data = api.get_price()
    if not price_data:
        await reply(update,
            "⚠️ Price data unavailable at the moment.\n\n"
            "Check manually at: https://webdollar.io"
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
        f"💹 <b>WEBD Price</b>\n\n"
        f"Price:        <b>${price}</b>\n"
        f"Volume 24h:   <b>{vol}</b>\n"
        f"Change:       {arrow} <b>{change}</b>"
    )

# ── /stats ────────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = db.get_bot_stats()
    await reply(update,
        f"🤖 <b>Bot Statistics</b>\n\n"
        f"👥 Registered users:   <b>{s['total_users']}</b>\n"
        f"🎁 Total tips:         <b>{s['total_tips']}</b>\n"
        f"💰 Total tip volume:   <b>{fmt_webd(s['total_volume'])}</b>"
    )

# ── /scoreboard ───────────────────────────────────────────────────────────────

async def cmd_scoreboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    top = db.get_top_tippers(10)
    if not top:
        await reply(update, "🏆 No tippers yet. Be the first with /tip!")
        return

    lines = ["🏆 <b>Top 10 Tippers</b>\n"]
    medals = ['🥇','🥈','🥉'] + ['🏅'] * 7
    for i, t in enumerate(top):
        name = t.get('first_name') or t.get('username') or 'Anonymous'
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
        f"💳 <b>Fees</b>\n\n"
        f"Tips:         <b>{'Free' if fee_pct == 0 else f'{fee_pct:.1f}%'}</b>\n"
        f"Deposit:      <b>Free</b>\n"
        f"Withdrawal:   <b>10 WEBD + 1% of amount</b> (max 375 WEBD total)\n"
        f"  Example: 100 WEBD → fee {fmt_webd(compute_fee(100))}\n"
        f"  Example: 1000 WEBD → fee {fmt_webd(compute_fee(1000))}\n"
        f"  Example: 40000 WEBD → fee {fmt_webd(compute_fee(40000))}\n\n"
        f"<i>Fees may be changed at the operator's discretion.</i>"
    )

# ── /topup ────────────────────────────────────────────────────────────────────

async def cmd_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "💳 <b>Buy WEBD</b>\n\n"
        "🚧 <i>This feature is under development.</i>\n\n"
        "You can currently buy WEBD on:\n"
        "• <a href='https://webdollar.io'>webdollar.io</a>\n"
        "• Listed exchanges\n\n"
        "Then use /deposit to add it to the bot."
    )

# ── /admin credit (admin only) ───────────────────────────────────────────────

async def cmd_admin_credit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id != ADMIN_TELEGRAM_ID:
        await reply(update, "❌ Access denied.")
        return
    if len(ctx.args) < 2:
        await reply(update, "Usage: /credit USER_ID AMOUNT")
        return
    try:
        uid    = int(ctx.args[0])
        amount = float(ctx.args[1])
    except ValueError:
        await reply(update, "❌ Invalid parameters.")
        return
    target = db.get_user(uid)
    if not target:
        await reply(update, f"❌ User {uid} does not exist.")
        return
    db.credit_deposit(uid, amount, note='admin_credit')
    await reply(update, f"✅ Credited {fmt_webd(amount)} → user {uid}")
    try:
        await ctx.bot.send_message(
            uid,
            f"✅ <b>{fmt_webd(amount)}</b> has been credited to your account by admin.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

# ── Main ──────────────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Porneste scan loop dupa ce botul este initializat."""
    asyncio.create_task(staking.scan_loop(app.bot))
    log.info('Scan loop started.')

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
    app.add_handler(CommandHandler('miner',        cmd_miner))
    app.add_handler(CommandHandler('price',        cmd_price))
    app.add_handler(CommandHandler('stats',        cmd_stats))
    app.add_handler(CommandHandler('scoreboard',   cmd_scoreboard))
    app.add_handler(CommandHandler('fees',         cmd_fees))
    app.add_handler(CommandHandler('topup',        cmd_topup))
    app.add_handler(CommandHandler('credit',       cmd_admin_credit))
    return app

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print('ERROR: TELEGRAM_TOKEN is not set in .env')
        exit(1)
    log.info('Telegram bot started...')
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
