# WEBDOLLAR Windows Miner - Ghid de utilizare (Beta)

Versiune aplicatie: 0.0.3
Actualizat: 2026-04-06

## 1. Instalare

### Varianta recomandata (installer)
1. Ruleaza: `WebDollar Windows Miner Setup 0.0.3.exe`
2. Urmeaza pasii din installer.
3. La final, deschide aplicatia din shortcut sau Start Menu.

### Varianta portabila (fara instalare)
1. Mergi in: `dist/win-unpacked/`
2. Ruleaza: `WebDollar Windows Miner.exe`

## 2. Primul start
La pornire vei vedea ecranul principal `WEBDOLLAR Windows Miner` cu zonele:
- Local config
- Wallet operations
- Local wallet vault
- Mining controls

## 3. Configurare rapida
1. In `Pool API URL`, introdu adresa pool-ului.
2. In `Wallet address`, adresa este afisata cu separator `$` pentru lizibilitate.
3. Apasa `Save config`.

Nota tehnica:
Aplicatia afiseaza adresa cu `$`, dar salveaza formatul intern compatibil protocolului legacy.

## 4. Wallet
Ai doua optiuni:
- `Generate wallet` pentru wallet nou
- `Import .webd file` pentru wallet existent

Pentru stocare criptata locala:
1. Introdu parola in `Password for local encryption`
2. Apasa `Encrypt and save locally`
3. Pentru deblocare ulterioara, foloseste `Password for unlock` + `Unlock saved wallet`

## 5. Mining
1. Apasa `Start mining`
2. Verifica `Mining status` si `Hashrate`
3. Pentru oprire, apasa `Stop mining`

## 6. Mesaje utile
- Daca apare eroare de auth, verifica pool URL si wallet-ul incarcat/deblocat.
- Daca nu sosesc joburi noi, aplicatia afiseaza warning automat.
- Daca ai un pool legacy PoS, wallet-ul trebuie sa fie importat/deblocat inainte de Start.

## 7. Ce este ascuns in beta
In acest build beta sunt ascunse elemente interne/noisy de diagnostic (inclusiv markerul intern de build si randurile temporare de tip legacy poll visibility) pentru o experienta mai curata.

## 8. Recomandari pentru testeri beta
1. Testeaza flow-ul complet: import/generare wallet -> save config -> start/stop mining.
2. Noteaza pool-ul folosit si timestamp-ul cand apare o eroare.
3. Trimite captura + mesajul exact din banner daca apare un failure.
