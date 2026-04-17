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

---

## Plan: Debug broadcast live + simplificare UI (Checkpoint 2026-04-09)

### Pasul 2 — Debug broadcast live pe nod real
- [x] 2a. Timeout 10s (era 5s), adauga candidati fallback pentru nod (daniuda + spyclub)
- [x] 2b. Log detaliat: HelloNode primit/neprimit, disconnect reason (io server disconnect = respins de nod), versiune
- [x] 2c. buildNodeCandidates() - lista ordonata: nod din config pool + fallback-uri hardcodate
- [x] 2d. Build + test live + salvare checkpoint (2026-04-09)

### Pasul 1 — Simplificare UI formular plata
- [x] 1a. Fee-ul calculat automat (10 WEBD fix), ref paymentFee eliminat
- [x] 1b. Formular arata doar: adresa destinatar + suma + nota "fee automat 10 WEBD" + buton Trimite
- [x] 1c. Build final curat (2026-04-09)
- [x] 1d. Indicator vizual cu 3 stari afisate permanent: Trimisa la nod -> In pending / mempool -> Confirmata in block; starea activa este evidentiata pana la confirmare.

### Checkpoint runtime (2026-04-09, dupa retest)
- [x] Confirmat ca logurile vechi proveneau dintr-o sesiune `npm run dev` pornita din `D:\Webdollar_2026`, nu din `D:\Webdollar_2026\webd-windows-miner`.
- [x] Portul 5173 era ocupat de un proces `node` stale (PID 31932), proces oprit.
- [x] Sesiunea corecta de dev este acum pornita cu `npm --prefix "D:\Webdollar_2026\webd-windows-miner" run dev`.
- [x] Detectia starii `pending` imbunatatita: fallback pe `/transactions/pending` daca `/transactions/pending/object` nu confirma, plus suport pentru campuri serializate ca `Buffer`.
- [x] Creat fisierul `NODE_WEBDOLLAR_API_INVENTORY_RO.md` cu inventarul API-urilor REST, callback si JSON-RPC din Node-WebDollar.
- [x] UX status plata imbunatatit: afisare progres polling (incercarea curenta / max), plus stare vizuala explicita "Monitorizare incheiata fara confirmare" ca sa nu mai para blocat pe "Trimisa la nod".
- [x] Corectat cauza `transaction is too old in pool`: tranzactia nu mai e semnata cu `timeLock=0`; `timeLock` se calculeaza live din `/top` (fallback `/`) inainte de semnare.
- [x] Confirmat runtime: transferul poate aparea mai tarziu; extins polling-ul la 60 verificari (~10 minute la interval de 10s).
- [x] Adaugat confirmare inainte de trimitere: prompt DA/NU cu suma si adresa destinatar; pe NU transferul este anulat.
- [x] Build salvat ca bun dupa modificarile de confirmare + monitorizare extinsa.
- [x] Executabil beta regenerat cu succes (`npm run dist`): installer NSIS + varianta `win-unpacked` (2026-04-09).
- [x] Adaugat buton de schimbare limba in UI (RO/EN) si texte principale bilingve in aplicatie.
- [x] Documentatie EN adaugata (`USER_GUIDE_BETA_EN.md`, `USER_GUIDE_BETA_SHORT_EN.md`, `DOWNLOAD_PACKAGE_FOR_SITE_EN.md`).
- [x] Regenerat kit executabil dupa modificarile de limba/documentatie (`npm run dist`, 2026-04-10).

---

## Recommended release sequence
1. Smoke test installer on a clean Windows profile.
2. Run first-time flow: import/generate wallet -> save config -> start mining.
3. Publish binaries and user guide together.
4. Collect beta feedback and classify issues by severity.
5. Schedule next checkpoint update before next release.
