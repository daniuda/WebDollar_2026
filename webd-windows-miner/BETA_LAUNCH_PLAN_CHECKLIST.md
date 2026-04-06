# WebDollar Windows Miner - Beta Launch Plan

Date: 2026-04-06
Current baseline: Checkpoint 034

## Scope
Prepare and publish a usable beta package for Windows users with clear install and usage guidance.

## Step-by-step plan with checklist

### 1. UI cleanup for beta readability
- [x] Remove internal build marker text from visible UI.
- [x] Replace placeholder top texts with production title: WEBDOLLAR Windows Miner.
- [x] Hide temporary diagnostics row/panel related to legacy poll visibility.
- [x] Keep essential mining controls visible.

### 2. Address formatting consistency
- [x] Ensure Local config wallet input shows $ for readability.
- [x] Keep internal storage/protocol compatibility by persisting / in config.

### 3. Technical verification
- [x] Run full validation build (`npm run build`).
- [x] Confirm renderer and Electron bundles are generated.

### 4. Packaging and installation kit
- [x] Generate installer package (`npm run dist`).
- [x] Confirm NSIS installer output exists.
- [x] Confirm standalone unpacked executable exists.

### 5. Release documentation
- [x] Create beta usage guide for end users.
- [x] Create launch checklist document for release operator.
- [x] Save session discussion summary for continuity.

### 6. Source-control release flow
- [ ] Review changed files.
- [ ] Commit with beta-prep message.
- [ ] Push to GitHub remote branch.
- [ ] Optionally tag beta build.

## Artifacts generated in this cycle
- Installer: `dist/WebDollar Windows Miner Setup 0.0.3.exe`
- Standalone: `dist/win-unpacked/WebDollar Windows Miner.exe`

## Recommended release sequence
1. Smoke test installer on a clean Windows profile.
2. Run first-time flow: import/generate wallet -> save config -> start mining.
3. Publish binaries and user guide together.
4. Collect beta feedback and classify issues by severity.
5. Schedule next checkpoint update before next release.
