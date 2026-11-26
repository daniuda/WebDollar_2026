# WebDollar Miner — User Manual

Desktop application (graphical interface) for mining WebDollar in a pool,
without needing the full WebDollar node. Nothing else needs to be
installed on the computer — the installer brings everything it needs,
including the WebView2 component (if not already present on the system).

## Requirements

- Windows 10 or 11, 64-bit.
- A WebDollar wallet (`.webd` file). If you don't have one, ask whoever
  gave you this program for a test wallet, or use your own wallet
  dedicated to mining (not your main wallet with large funds).

## Installation

1. Run the installer file (`WebDollar Miner_0.1.0_x64_en-US.msi`).
2. Follow the installer steps (Next → Next → Install).
3. At the end, the app may launch automatically, or you can find it in
   the Start menu, under "WebDollar Miner".

## Switching language

A small **RO / EN** button in the top-right corner switches the
interface language. Your choice is remembered the next time you open
the app.

## Starting mining

On first launch you'll see a form:

| Field | What to put |
|---|---|
| **Wallet (.webd)** | The path to your wallet file. Click "Browse…" to pick it visually, or type the path directly (e.g. `C:\WEBD\my-wallet.webd`). |
| **Wallet password** | Fill in ONLY if your wallet is password-encrypted. Leave empty otherwise. |
| **Pool — URL** | Comes pre-filled with the WebDollar RunPlace pool. No need to change it unless you want a different pool. |
| **Pool — public key** | Same, comes pre-filled. |

Click **"Start mining"**. The area below shows live indicators:

- **Connected / Disconnected** — the state of the connection to the pool.
- **Height** — the current block of the network.
- **Heartbeats** — how many reports you've sent to the pool.
- **Real matches** — how many times you actually found a block (rare,
  it's normal for this to stay 0 for hours/days).
- **Reward** — your reward, in the process of accumulating.
- **Confirmed** — the reward already confirmed by the pool (what you'll
  receive at payout).

Below, in the log area, you see raw text, line by line — useful if you
want to check exactly what's happening or if an error appears. The log
lines coming from the mining process itself are currently shown as
produced (in Romanian); only the form, buttons and status indicators
switch with the RO/EN button.

**Important:** the reward grows SLOWLY, especially with small balances
— it can take hours for "Confirmed" to move visibly. This is not a sign
that the program isn't working, it's normal (it depends on the length
of the pool's reward cycle and the size of your balance).

## Stopping mining

Click **"Stop"** in the window. Mining stops, but the app stays open
(you can restart anytime, with a different wallet if you want).

## Minimizing to the system tray

- Closing the window (the X button) does **NOT** stop the app — it only
  hides the window. Mining continues in the background.
- Look for the app's icon in the system tray (bottom-right corner of the
  Windows taskbar, next to the clock).
- **Click the icon** — shows/hides the window.
- **Right-click the icon** — shows a menu with:
  - "Show / Hide" — same effect as a single click.
  - "Exit (also stops the miner)" — **this is the only way to actually
    close the app and fully stop mining.**

## Common issues

- **"Miner is already running — press Stop first."** — you pressed Start
  twice; press Stop, then Start again.
- **"Decryption failed"** (in the log area) — the wallet password is
  wrong.
- **Not connecting at all** — check your internet connection, or whether
  the wallet is already mining elsewhere at this moment (don't run two
  instances on the same address at the same time).
