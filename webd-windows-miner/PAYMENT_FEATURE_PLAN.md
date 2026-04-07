# Plan Funcționalitate Plăți — v0.1.0

**Data:** 2026-04-07  
**Bază:** tag `v0.0.3-base` (commit 82473e0, GitHub master)  
**Versiune țintă:** v0.1.0

---

## 1. Scurt rezumat

Se adaugă în aplicație posibilitatea de a trimite WEBD de la wallet-ul curent către orice adresă. Plata este posibilă **numai** dacă există un pool verificat activ (conectat sau proba-pool reușită). Plata nu se poate face fără wallet deblocat și fără confirmare utilizator.

---

## 2. Condiții prealabile (pre-conditions)

| Condiție | Verificare |
|----------|-----------|
| Pool conectat (legacyPool) sau pool API accesibil | `poolAlive: boolean` în store |
| Wallet deblocat (secret decriptat în memorie) | `currentWallet !== null` |
| Balanță minimă > valoare trimisă + fee (10 WEBD min fee) | `poolAddressReward.walletBalance > amount + fee` |
| Destinatar adresă validă WEBD | regex WIF + format `$…$` |

Butonul de trimitere rămâne dezactivat (gri, tooltip explicativ) dacă oricare condiție e neîndeplinită.

---

## 3. Arhitectura modulelor noi

```
electron/
  txBuilder.ts        ← construcție serializare tranzacție WebDollar
  txBroadcast.ts      ← trimitere HTTP/socket la pool sau full node

src/
  services/
    paymentApi.ts     ← wrapper Vue-side pentru IPC send-tx
  components/
    PaymentPanel.vue  ← formular UI trimitere plată

src/types/miner.ts    ← extend: PaymentRequest, PaymentResult
electron/main.ts      ← IPC handler: 'send-transaction'
electron/preload.ts   ← expune: desktopApi.sendTransaction()
```

---

## 4. Format tranzacție WebDollar

Bazat pe sursa Node-WebDollar (`TransactionTransformer.js`):

```
tx = {
  version: 1,
  nonce: <random 4 bytes uint32>,
  timeLock: 0,              // fără time-lock
  from: [{
    unencodedAddress: <20 bytes hex, din walletul sursă>,
    publicKey: <32 bytes Ed25519 pubkey hex>,
    amount: <amount_raw = WEBD × 10000>,
    signature: <64 bytes Ed25519, semnat pe tx_hash>
  }],
  to: [{
    unencodedAddress: <destinatar 20 bytes hex>,
    amount: <amount_raw>
  }],
  fee: <fee_raw = 10 WEBD × 10000 = 100000 units>
}
```

### Serializare pentru semnătură (txHash):
```
hash_payload = concat(
  serUint32(nonce),
  serUint32(timeLock),
  from.unencodedAddress,      // 20 bytes
  to.unencodedAddress,        // 20 bytes
  serUint64(amount_raw),      // little endian 8 bytes
  serUint64(fee_raw)
)
txHash = sha256(sha256(hash_payload))
signature = nacl.sign.detached(txHash, secretKey_32bytes)
```

> **Notă:** Se va valida exact formatul după testare contra unui nod real. Este posibil să fie nevoie de ajustări pe baza răspunsului de la pool/node (versiune protocol, succesul broadcast). Aceasta e prima iterație documentată.

---

## 5. Broadcast tranzacție

Două metode posibile (se încearcă în ordine):

### A. HTTP REST (JSON-RPC pe nodul full)
```
POST https://<node>/chain/transactions/new
Content-Type: application/json
Body: { tx: <tx serializat hex sau JSON> }
```

### B. Socket.IO emit (legacyPool socket activ)
```javascript
socket.emit('new-transaction', txPayload)
```

**Prioritate:** dacă `legacyPool` are socket conectat → se folosește socket. Altfel, se detectează automat URL-ul nodului din config de pool și se trimite HTTP.

---

## 6. UI — PaymentPanel.vue

```
┌─────────────────────────────────────────────┐
│  TRIMITE WEBD                               │
│                                             │
│  Destinatar:  [____________________________]│
│  Sumă (WEBD): [____________] maxim: XX WEBD │
│  Fee estimat: 10 WEBD (fix)                 │
│                                             │
│  [ANULEAZĂ]                [CONFIRMĂ PLATA] │
│                                             │
│  Status: ● Pool verificat | Wallet deblocat │
└─────────────────────────────────────────────┘
```

- Panel apare ca modal/drawer sau secțiune colapsabilă sub dashboard
- Câmpul destinatar validat live (format WEBD adresă)
- Suma validată live (max = balance - fee)
- Buton Confirmă → dialog de confirmare cu toate detaliile înainte de submit
- Rezultat: tx_id + link de vizualizare în explorer (dacă e online)

---

## 7. Pași de implementare (Milestone-uri)

### M1 — Infrastructură (fără UI)
1. `txBuilder.ts` — construcție payload + semnătură Ed25519
2. `txBroadcast.ts` — broadcast HTTP + socket
3. IPC handler în `main.ts` + expunere în `preload.ts`
4. `paymentApi.ts` — wrapper Vue
5. `miner.ts` — adaugă `PaymentRequest`, `PaymentResult`
6. Test manual în terminal: trimitere tx pe testnet/mainnet

### M2 — UI
1. `PaymentPanel.vue` — formular complet cu validări
2. Integrare în `App.vue` — tab sau secțiune colapsabilă
3. Pre-condition indicators (pool alive, wallet unlocked, balance ok)

### M3 — Polish & Packaging
1. Fee dinamic (inițial fix 10 WEBD, ulterior fetch de la pool)
2. Confirmare 2 pași înainte de submit
3. Afișare tx_id după trimitere + copiere în clipboard
4. Build + installer v0.1.0
5. Commit + tag `v0.1.0` + push GitHub

---

## 8. Ce NU se schimbă

- Mining flow rămâne intact
- Wallet import/export rămâne intact
- Config persisted rămâne intact
- Nu se adaugă funcție de history (tranzacții trimise) în această versiune

---

## 9. Riscuri și mitigare

| Risc | Mitigare |
|------|----------|
| Format tx diferit față de ce acceptă pool-ul | Testare live iterativă cu minimum 0.001 WEBD; fallback prin nod HTTP |
| Pool-ul nu acceptă tx prin socket | Implementare fallback HTTP automat |
| Balanță afișată incorect → trimitere greșită | Double-check balance la momentul submit, nu doar la deschidere UI |
| UI dezactivat deoarece pool nu e verificat | Afișat clar de ce nu se poate trimite + instrucțiuni |

---

## 10. Versioning & Git

```
branch: feature/payment-v0.1.0   ← creat din master (82473e0)
tag la finalizare: v0.1.0
```

Comenzi de creare branch:
```bash
git checkout -b feature/payment-v0.1.0
```

---

## Checkpoint rezumat

- **v0.0.3-base** = starea actuală, tag-uit pe GitHub, baza sigură
- **v0.1.0** = prima versiune cu plăți WEBD din aplicație
- **Keyword reluare:** `relaum_aplicatia` → continuă de la payment feature, branch `feature/payment-v0.1.0`
