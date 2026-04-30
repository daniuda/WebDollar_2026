// main.js - bootstrap WebDollar node modern

import { ChainStorage } from './storage/ChainStorage.js';
import { Miner } from './mining/Miner.js';
import { ApiServer } from './api/ApiServer.js';
import { WebSocketServer } from './network/sockets/WebSocketServer.js';
import { peerManager } from './network/peers/peerManagerInstance.js';
import { syncFromLegacy } from './sync/legacyRestSyncBootstrap.js';
import { loadLegacyBlocksIntoChain } from './storage/loadLegacyLevelDB.js';
import { Logger } from './utils/logger.js';
import { WorkerStorage } from './pool/WorkerStorage.js';
import { JobManager } from './pool/JobManager.js';
import { ShareValidator } from './pool/ShareValidator.js';
import { WorkerManager } from './pool/WorkerManager.js';


const chain = new ChainStorage();
const miner = new Miner(chain);
const api = new ApiServer(chain);
const wsServer = new WebSocketServer(8088);

// pool
const workerStorage  = new WorkerStorage();
const jobManager     = new JobManager(chain);
const shareValidator = new ShareValidator(jobManager);
const workerManager  = new WorkerManager(workerStorage, jobManager, shareValidator);

async function start() {
  // 1) Pornește infrastructura de bază imediat
  await api.start(3001);
  wsServer.start();

  // 2) Pornire pool - nu blochează
  workerManager.start();
  api.setWorkerManager(workerManager);
  api.setWsServer(wsServer);
  Logger.info('[Pool] Endpoint-uri /worker/* și /pool/stats active');

  // 3) Restaurare rapidă din chain.json local (sincron, instant)
  const restoredCount = chain.loadFromDisk();

  // 4) Sincronizare REST legacy - imediat, nu depinde de importul local
  await syncFromLegacy(chain, peerManager);

  // 5) Pornește minerul imediat după REST sync
  miner.start();

  // 6) Import legacy PouchDB rulează în background - nu blochează startup-ul
  //    Completează chain-ul cu blocuri istorice și salvează pe disc când gata
  loadLegacyBlocksIntoChain(chain).then(result => {
    if (result && result.imported > 0) {
      chain.saveToDisk();
    } else if (restoredCount === 0 && result && result.mode === 'pouchdb') {
      // salvăm și dacă n-am importat nimic nou (chain deja la curent)
      chain.saveToDisk();
    }
  }).catch(err => {
    Logger.warn('Import background legacy eșuat:', err.message);
  });
}

start().catch((err) => {
  Logger.error('Eroare fatală startup:', err?.message || err);
  process.exit(1);
});