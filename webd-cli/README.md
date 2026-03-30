
# WebDollar 2026 CLI

## Comenzi principale

- `webd install node [--snapshot=URL] [--dbfolder=CALE]` – Instalează complet și automat un nod WebDollar (clonare, npm install, snapshot blockchain, build-tools, totul automat, opțional snapshot custom și folder blockchain custom)
- `webd start node [PORT] [--dbfolder=CALE]` – Pornește nodul WebDollar cu port și folder custom
- `webd install pool [--port=PORT] [--dbfolder=CALE]` – Instalează complet și automat un pool WebDollar cu port/folder custom
- `webd start pool [--port=PORT] [--dbfolder=CALE]` – Pornește pool-ul WebDollar cu port/folder custom
- `webd docker node` – Instalează și pornește WebDollar Node în Docker
- `webd check updates` – Verifică automat dacă există update-uri pentru CLI/node/pool

## Instalare rapidă

1. Asigură-te că ai Node.js >=16 instalat
2. Deschide terminalul ca Administrator (pe Windows)
3. Rulează:
   ```
   npm install -g ./webd-cli
   webd install node --snapshot=https://webdollar.network/snapshot/blockchainDB3-latest.zip --dbfolder=D:/cale/blockchainDB3
   webd start node 8080 --dbfolder=D:/cale/blockchainDB3
   # sau pentru pool:
   webd install pool --port=8081 --dbfolder=D:/cale/pooldb
   webd start pool --port=8081 --dbfolder=D:/cale/pooldb
   # pentru Docker:
   webd docker node
   # verificare update-uri:
   webd check updates
   ```

## Detalii suplimentare
- Snapshot-ul blockchain este descărcat automat (implicit sau custom)
- Toate dependențele și pașii critici sunt automatizați
- Progresul și logarea sunt afișate clar la fiecare pas și salvate în log.txt
- Suport port/folder custom la node și pool
- Integrare Docker pentru node
- Verificare automată update-uri

## Exemple de utilizare

### Instalare și pornire nod cu snapshot custom și folder custom
```
webd install node --snapshot=https://exemplu.com/snap.zip --dbfolder=D:/blockchain
webd start node 8080 --dbfolder=D:/blockchain
```

### Instalare și pornire pool cu port/folder custom
```
webd install pool --port=8081 --dbfolder=D:/pooldb
webd start pool --port=8081 --dbfolder=D:/pooldb
```

### Pornire nod în Docker
```
webd docker node
```

### Verificare update-uri
```
webd check updates
```

## TODO
- Actualizare URL snapshot după stabilizare
