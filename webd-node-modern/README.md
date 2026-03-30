# WebDollar Node Modern

Acest proiect reprezintă rescrierea completă a nodului WebDollar pentru Node.js modern (20+), folosind ES Modules, async/await, structură modulară și testare automată.

## Structură proiect

- `src/core/blockchain/` – logica blockchain
- `src/core/consensus/` – consens PoS/PoW
- `src/core/storage/` – stocare și indexare
- `src/network/sockets/` – conexiuni WebSocket
- `src/network/peers/` – management peers
- `src/network/messages/` – protocoale și mesaje
- `src/mining/pos/` – mining PoS
- `src/mining/pow/` – mining PoW
- `src/api/http/` – API HTTP
- `src/api/rpc/` – API RPC
- `src/utils/` – utilitare (logger, config, events)
- `tests/` – testare automată

## Module principale

- `src/network/sockets/` — WebSocketServer, WebSocketClient
- `src/network/peers/` — PeerManager, PeerDiscovery, PeerConnector
- `src/network/messages/` — MessageTypes, MessageHandler, MessageBuilder, Handshake, LegacyCompat
- `src/utils/` — logger, config, events

## Funcționalități implementate

- Peer management modern (reconnect, heartbeat, blacklist/whitelist)
- Peer discovery automat cu seed list
- Conectare automată la peers descoperiți
- Routing modular pentru mesaje compatibile (ping/pong, handshake, extensibil)
- Handshake compatibil vechi/nou
- Utilitare pentru compatibilitate cu noduri vechi

## Primii pași

1. npm install
2. Dezvoltare modulară, cu async/await și ES Modules
3. Testare automată (urmează)

## Autor
- daniuda
