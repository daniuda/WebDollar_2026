# WebDollar 2026 CLI

## Comenzi principale

- `webd install node` – Instalează complet și automat un nod WebDollar (clonare, npm install, snapshot blockchain, build-tools, totul automat)
- `webd start node` – Pornește nodul WebDollar
- `webd install pool` – Instalează complet și automat un pool WebDollar
- `webd start pool` – Pornește pool-ul WebDollar

## Instalare rapidă

1. Asigură-te că ai Node.js >=16 instalat
2. Deschide terminalul ca Administrator (pe Windows)
3. Rulează:
   ```
   npm install -g ./webd-cli
   webd install node
   webd start node
   # sau pentru pool:
   webd install pool
   webd start pool
   ```

## Detalii suplimentare
- Snapshot-ul blockchain este descărcat automat de la https://webdollar.network/snapshot/blockchainDB3-latest.zip
- Toate dependențele și pașii critici sunt automatizați
- Progresul și logarea sunt afișate clar la fiecare pas

## TODO
- Opțiuni avansate de configurare (port, custom snapshot, etc)
- Integrare Docker
- Actualizare URL snapshot după stabilizare
