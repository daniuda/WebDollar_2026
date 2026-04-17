# Download package for website - WebDollar Windows Miner (Beta 0.0.3)

Date: 2026-04-10

This file lists what you can publish on the website for downloads.

## 1) Application install kit

1. Windows installer (recommended)
- File: `dist/WebDollar Windows Miner Setup 0.0.3.exe`
- Suggested label: "Windows Installer (x64) - standard installation"

2. Portable build (no installation)
- File: `dist/win-unpacked/WebDollar Windows Miner.exe`
- Suggested label: "Portable Windows executable (x64)"

3. Blockmap (optional for differential updates)
- File: `dist/WebDollar Windows Miner Setup 0.0.3.exe.blockmap`
- Suggested label: "Technical file for incremental updates (optional)"

## 2) Documentation for download

1. Full installation + usage guide (Romanian)
- File: `USER_GUIDE_BETA_RO.md`

2. Full installation + usage guide (English)
- File: `USER_GUIDE_BETA_EN.md`

3. Very short non-technical guide (Romanian)
- File: `USER_GUIDE_BETA_RO_SHORT.md`

4. Very short non-technical guide (English)
- File: `USER_GUIDE_BETA_SHORT_EN.md`

5. Node-WebDollar API inventory (Romanian, optional for developers)
- File: `NODE_WEBDOLLAR_API_INVENTORY_RO.md`

## 3) Suggested website structure

- Section "Application"
  - Windows Installer (.exe)
  - Portable executable (.exe)
- Section "Documentation"
  - Full guide (RO)
  - Full guide (EN)
  - Quick guide (RO)
  - Quick guide (EN)
- Section "Developer resources" (optional)
  - Node-WebDollar API inventory (RO)

## 4) Publishing note

For most users, make installer the first download button:
- `WebDollar Windows Miner Setup 0.0.3.exe`

Keep portable build as the second button for advanced users.
