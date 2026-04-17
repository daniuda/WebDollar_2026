# WEBDOLLAR Windows Miner - Installation and Usage Guide (Beta)

Application version: 0.0.3
Updated: 2026-04-10

## 1. What is included in this beta package
- Windows installer: `dist/WebDollar Windows Miner Setup 0.0.3.exe`
- Portable build: `dist/win-unpacked/WebDollar Windows Miner.exe`

## 2. Installation

### Recommended option (installer)
1. Run `WebDollar Windows Miner Setup 0.0.3.exe`.
2. Follow the installer steps.
3. Launch the app from Start Menu or Desktop shortcut.

### Portable option (no installation)
1. Open `dist/win-unpacked/`.
2. Run `WebDollar Windows Miner.exe`.

## 3. First start (quick setup)
1. Fill in `Pool API URL`.
2. Fill in `Wallet address`.
3. Click `Save config`.

Notes:
- The app displays wallet address with `$` for readability.
- Internally, it converts automatically to protocol-compatible format.

## 4. Wallet (import, generate, unlock)

Available options:
- `Generate wallet` for a new wallet.
- `Import .webd file` for an existing wallet.

For local encrypted storage:
1. Enter password in `Password for local encryption`.
2. Click `Encrypt and save locally`.
3. To unlock later: `Password for unlock` -> `Unlock saved wallet`.

## 5. Mining (basic usage)
1. Click `Start mining`.
2. Watch `Mining status`, `Hashrate`, `Accepted/Rejected/Stale`.
3. Click `Stop mining` to stop.

## 6. Send WEBD (payment)
1. Fill recipient address and amount.
2. Click `Send WEBD`.
3. Confirm in dialog:
   - `OK` = continue transfer
   - `Cancel` = abort transfer
4. After sending, app tracks status stages:
   - `Sent to node`
   - `In pending / mempool`
   - `Confirmed in block`

Notes:
- Monitoring window is extended (up to 60 checks, around 10 minutes).
- Depending on node/network conditions, pending/confirmed can appear with delay.

## 7. Language switch
- Use the language button in header (`Romana` / `English`) to switch UI language.

## 8. Common checks
- Auth/mining error: verify pool URL and wallet is loaded/unlocked.
- No new jobs: check network connectivity and pool health.
- Payment stays at `Sent to node`: wait for full monitoring window and verify in explorer link shown by app.

## 9. Quick troubleshooting
1. Fully close the app.
2. Start only one app instance.
3. Verify system clock is correct.
4. Retry with same config.

## 10. Beta testing recommendations
1. Test full flow: config -> wallet -> start/stop mining -> payment test.
2. When reporting issues, include:
   - approximate time
   - pool URL
   - exact banner message
3. If you have pool/node logs, include exact error line.
