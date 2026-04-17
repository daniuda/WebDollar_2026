# WEBDOLLAR Windows Miner - Ghid Instalare si Utilizare (Beta)

Versiune aplicatie: 0.0.3
Actualizat: 2026-04-10

## 1. Ce contine pachetul beta
- Installer Windows: `dist/WebDollar Windows Miner Setup 0.0.3.exe`
- Varianta portabila: `dist/win-unpacked/WebDollar Windows Miner.exe`

## 2. Instalare

### Varianta recomandata (installer)
1. Ruleaza `WebDollar Windows Miner Setup 0.0.3.exe`.
2. Urmeaza pasii din installer.
3. Porneste aplicatia din Start Menu sau shortcut Desktop.

### Varianta portabila (fara instalare)
1. Deschide folderul `dist/win-unpacked/`.
2. Ruleaza `WebDollar Windows Miner.exe`.

## 3. Primul start (setare rapida)
1. Completeaza `Pool API URL`.
2. Completeaza `Wallet address`.
3. Apasa `Save config`.

Nota:
- Aplicatia afiseaza adresa cu separator `$` pentru lizibilitate.
- Intern, formatul este convertit automat pentru compatibilitate protocol.

## 4. Wallet (import, generare, deblocare)

Optiuni disponibile:
- `Generate wallet` pentru wallet nou.
- `Import .webd file` pentru wallet existent.

Pentru stocare criptata locala:
1. Introdu parola in `Password for local encryption`.
2. Apasa `Encrypt and save locally`.
3. Pentru deblocare ulterioara: `Password for unlock` -> `Unlock saved wallet`.

## 5. Mining (folosire de baza)
1. Apasa `Start mining`.
2. Urmareste `Mining status`, `Hashrate`, `Accepted/Rejected/Stale`.
3. Pentru oprire, apasa `Stop mining`.

## 6. Transfer WEBD (plata)
1. Completeaza adresa destinatar si suma.
2. Apasa `Trimite WEBD`.
3. Aplicatia cere confirmare explicita:
	- mesaj de tip: `Esti sigur ca vrei sa trimiti suma de ... WEBD catre adresa ...?`
	- `OK` = transferul continua
	- `Cancel` = transferul se anuleaza
4. Dupa trimitere, statusul este urmarit automat in etape:
	- `Trimisa la nod`
	- `In pending / mempool`
	- `Confirmata in block`

Observatie:
- Monitorizarea este extinsa (pana la 60 verificari, aproximativ 10 minute).
- Uneori tranzactia apare in pending/confirmed cu intarziere, in functie de nod/retea.

## 7. Mesaje uzuale si ce verifici
- Eroare auth/mining: verifica pool URL si wallet-ul incarcat/deblocat.
- Nu vin joburi noi: verifica conectivitatea si statusul pool-ului.
- Plata ramane in `Trimisa la nod`: asteapta monitorizarea completa si verifica si in explorer.

## 8. Troubleshooting rapid
1. Inchide complet aplicatia.
2. Porneste din nou o singura instanta.
3. Verifica ora sistemului (sa fie corecta).
4. Reincearca trimiterea cu aceeasi configuratie.

## 9. Recomandari pentru testare beta
1. Ruleaza fluxul complet: config -> wallet -> start/stop mining -> transfer test.
2. Cand raportezi un bug, include:
	- ora aproximativa
	- pool URL folosit
	- mesajul exact din banner
3. Daca ai log din pool/nod, include linia exacta de eroare.
