# Inventar API Node-WebDollar

Data: 2026-04-09
Sursa analizata: `D:\Webdollar_2026\Node-WebDollar`

Acest fisier sintetizeaza API-urile si informatiile ce pot fi extrase din Node-WebDollar din 4 zone:
- REST public
- REST privat (doar daca nodul porneste cu `WALLET_SECRET_URL`)
- callback/subscription API
- JSON-RPC

Observatie importanta:
- unele endpointuri exista in cod, dar pot fi indisponibile pe un nod public concret daca operatorul nu le expune
- rutele private exista doar daca variabila `WALLET_SECRET_URL` este definita si suficient de lunga
- metodele JSON-RPC de wallet/mining/send sunt, in general, concepute pentru acces autentificat

## 1. REST public

### `GET /`
- Ce face: intoarce sumarul nodului.
- Ce informatii poti extrage:
  - `protocol`
  - `version`
  - `poolURL` in debug
  - lungimea lantului si hash-ul ultimului bloc
  - `networkHashRate`
  - `chainWork`
  - numarul de socket clients/servers/webpeers
  - serviciile active: `serverPool`, `miningPool`, `minerPool`
  - waitlist-ul de noduri terminal
  - daca nodul este sincronizat si cu cate secunde este in urma

### `GET /blocks/between/:block_start`
### `GET /blocks/between/:block_start/:block_end`
- Ce face: intoarce un interval de blocuri.
- Ce informatii poti extrage:
  - blocuri serialize JSON
  - headere si continut de bloc pentru intervalul cerut
- Limita din cod: maxim 25 blocuri per cerere.

### `GET /blocks/at/:block`
- Ce face: intoarce un bloc dupa inaltime.
- Ce informatii poti extrage:
  - blocul serializat JSON

### `GET /address/balance/:address`
- Ce face: intoarce soldul unei adrese.
- Ce informatii poti extrage:
  - `balance` in WEBD

### `GET /address/nonce/:address`
- Ce face: intoarce nonce-ul unei adrese.
- Ce informatii poti extrage:
  - `nonce`

### `GET /server/nodes/list`
- Ce face: intoarce lista de noduri conectate.
- Ce informatii poti extrage:
  - noduri client si server
  - adresa/IP si geolocatie aproximativa

### `GET /server/nodes/blocks-propagated`
- Ce face: intoarce blocuri recente propagate/minate.
- Ce informatii poti extrage:
  - `height`
  - hash prescurtat
  - `minerAddress`

### `GET /pools/stats`
- Ce face: statistici ale pool-ului daca nodul ruleaza in mod pool.
- Ce informatii poti extrage:
  - `hashes`
  - `hashes_now`
  - `miners_online`
  - `blocks_confirmed_and_paid`
  - `blocks_unconfirmed`
  - `blocks_confirmed`
  - `blocks_being_confirmed`
  - `time_remaining`

### `GET /pools/all-miners`
- Ce face: lista tuturor minerilor cunoscuti de pool.
- Ce informatii poti extrage:
  - adresa minerului
  - `miner_index`
  - `reward_total`
  - `reward_confirmed`
  - `reward_sent`
  - ultima activitate
  - numarul de instante

### `GET /pools/miners`
- Ce face: lista instantelor de miner conectate acum.
- Ce informatii poti extrage:
  - hashrate raportat si hashrate real
  - adresa
  - reward total/confirmed/sent
  - `date_activity`
  - `miner_index`
  - `totalPOSBalance`
  - IP-ul sursa sau `offline`

### `GET /pools/pool-data`
- Ce face: date interne despre blocurile si instantele pool-ului.
- Ce informatii poti extrage:
  - `miningHeights`
  - instantele care au contribuit la bloc
  - dificultate POW/POS agregata pe instanta
  - blocul serializat, cand exista

### `GET /transactions/pending`
- Ce face: lista pending queue in forma array.
- Ce informatii poti extrage:
  - tranzactii aflate in mempool/pending

### `GET /transactions/pending/object`
- Ce face: pending queue in forma obiect.
- Ce informatii poti extrage:
  - aceleasi tranzactii pending, dar in structura obiect

### `GET /transactions/exists/:tx_id`
- Ce face: verifica daca tranzactia exista in blockchain.
- Ce informatii poti extrage:
  - `result`
  - `height` daca tranzactia a fost gasita in block

### `GET /transactions/get/:tx_id`
- Ce face: intoarce tranzactia daca este deja in blockchain.
- Ce informatii poti extrage:
  - `tx` serializat JSON
  - confirma practic includerea on-chain, nu doar broadcast-ul

### `GET /hello`
- Ce face: healthcheck simplu.
- Ce informatii poti extrage:
  - `hello: world`

### `GET /top`
- Ce face: sumar scurt al varfului lantului.
- Ce informatii poti extrage:
  - `top` (height)
  - `is_synchronized`
  - `secondsBehind`

### `GET /ping`
- Ce face: ping simplu.
- Ce informatii poti extrage:
  - `ping: pong`

## 2. REST privat prin `WALLET_SECRET_URL`

Aceste rute exista doar daca nodul este pornit cu `WALLET_SECRET_URL`.

### `GET {WALLET_SECRET_URL}/list`
- Ce face: afiseaza lista rutelor disponibile.

### `GET {WALLET_SECRET_URL}/blocks_complete/at/:block`
- Ce face: intoarce un bloc complet, mai detaliat decat varianta publica.

### `GET {WALLET_SECRET_URL}/mining/balance`
- Ce face: intoarce adresa de mining activa in nod si soldul ei.

### `GET {WALLET_SECRET_URL}/wallets/import/:address/:publicKey/:privateKey`
- Ce face: importa un wallet in nod.
- Ce efect are: wallet-ul devine disponibil in wallet manager-ul nodului.

### `GET {WALLET_SECRET_URL}/wallets/create-transaction/:from/:to/:amount/:fee`
- Ce face: nodul construieste, semneaza si propaga o tranzactie folosind wallet-ul pe care il are deja importat.
- Ce poti extrage din raspuns:
  - rezultat operatiune
  - semnatura
  - `txId`
- Observatie: aceasta ruta nu este pentru tranzactii semnate local in desktop app, ci pentru scenariul in care nodul are wallet-ul.

### `GET {WALLET_SECRET_URL}/wallets/export`
- Ce face: exporta wallet-ul activ al nodului.

### `GET {WALLET_SECRET_URL}/wallets/create-wallet`
- Ce face: creeaza un wallet nou in nod.
- Ce poti extrage:
  - adresa
  - public key
  - private key exportata

## 3. Callback / subscription API

### `GET /subscribe/address/balances`
- Ce face: subscrie clientul la schimbari de sold si nonce pentru o adresa.
- Ce poti primi ulterior:
  - `balances`
  - `nonce`

### `GET /subscribe/address/transactions`
- Ce face: subscrie clientul la tranzactii noi legate de o adresa.
- Ce poti primi ulterior:
  - tranzactii asociate adresei

## 4. JSON-RPC

Metodele gasite in cod sunt:

### Wallet / accounts
- `accounts`
  - Lista adreselor din wallet.
  - Optional poate intoarce obiecte cu `balance`, `balance_raw` si `isEncrypted`.
- `deleteAccount`
  - Sterge o adresa din wallet-ul nodului.
- `encryptAccount`
  - Marcheaza/cripteaza o adresa din wallet.
- `exportAccount`
  - Exporta o adresa din wallet.
- `importAccount`
  - Importa o adresa in wallet.
- `newAccount`
  - Creeaza o adresa noua.

### Mining
- `getMiningStatus`
  - Intoarce starea curenta a minerului local.
  - Informatii: `isMining`, `miningAddress`, `hashRate`, `nextBlockHeight`, `nextRoundIsPOS`, `nextRoundIsPOW`, `nextRoundType`.
- `setMiningAccount`
  - Seteaza adresa de mining.
- `startMining`
  - Porneste minerul.
- `stopMining`
  - Opreste minerul.

### Blockchain / network info
- `blockNumber`
  - Intoarce inaltimea curenta a lantului.
- `clientVersion`
  - Intoarce versiunea JSON-RPC/client.
- `getBalance`
  - Intoarce soldul unei adrese.
- `getBlockByHash`
  - Intoarce un bloc dupa hash.
- `getBlockByNumber`
  - Intoarce un bloc dupa inaltime.
- `getBlockCount`
  - Intoarce numarul total de blocuri.
- `getBlocksByNumbers`
  - Intoarce mai multe blocuri dupa lista de numere.
- `getBlocksByRange`
  - Intoarce blocuri pentru un interval.
- `getBlockTransactionCountByHash`
  - Numar de tranzactii dintr-un bloc dupa hash.
- `getBlockTransactionCountByNumber`
  - Numar de tranzactii dintr-un bloc dupa numar.
- `getTransactionByBlockHashAndIndex`
  - Tranzactie dupa hash bloc + index.
- `getTransactionByBlockNumberAndIndex`
  - Tranzactie dupa numar bloc + index.
- `getTransactionByHash`
  - Cauta o tranzactie dupa hash.
- `getTransactionCount`
  - Intoarce nonce / numar de tranzactii pentru o adresa, in functie de implementarea metodei.
- `netVersion`
  - Intoarce tipul de retea.
- `nodeWaitList`
  - Intoarce waitlist-ul de noduri cunoscute.
- `networkHashRate`
  - Intoarce hashrate-ul estimat al retelei.
- `peerCount`
  - Intoarce numarul de peers.
- `protocolVersion`
  - Intoarce versiunea protocolului de nod.
- `syncing`
  - Intoarce starea de sincronizare a nodului.

### Transaction send / propagation
- `sendRawTransaction`
  - Primeste o tranzactie pre-semnata, o valideaza si o propaga.
  - In cod, argumentul este un singur payload Base64 care contine JSON cu `transaction` si `signature`.
- `sendTransaction`
  - Nodul creeaza si semneaza tranzactia din wallet-ul lui.
  - Parametri principali: `from`, `to`, `value`, `fee`, optional `password`.
- `sendAdvancedTransaction`
  - Varianta mai flexibila pentru tranzactii avansate.

## 5. Ce merita folosit in aplicatia desktop miner

Pentru `webd-windows-miner`, cele mai utile zone sunt:
- `transactions/pending`
- `transactions/pending/object`
- `transactions/exists/:tx_id`
- `transactions/get/:tx_id`
- `sendRawTransaction` daca vei avea candva un endpoint JSON-RPC real disponibil pe nodul tinta
- socket event `transactions/new-pending-transaction` pentru broadcast direct catre nod

## 6. Concluzie practica

Daca vrei sa extragi informatii fara wallet pe nod, zona sigura este:
- info/top/ping
- blocks/*
- address/balance si address/nonce
- server/nodes/*
- pools/*
- transactions/pending, transactions/exists, transactions/get

Daca vrei operatii de wallet sau creare de tranzactii pe nod, ai nevoie de:
- `WALLET_SECRET_URL` pentru REST privat
  sau
- JSON-RPC configurat si, de regula, autentificat
