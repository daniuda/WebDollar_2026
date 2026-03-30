// PeerDiscovery.js - descoperire peers compatibilă cu rețeaua WebDollar
import { Logger } from '../../utils/logger.js';

export class PeerDiscovery {
  constructor(seedPeers = []) {
    this.seedPeers = seedPeers;
    this.discovered = new Set();
  }

  async discover() {
    // În WebDollar clasic, peers se descoperă din handshake și din seed list
    for (const peer of this.seedPeers) {
      try {
        // Poți folosi fetch sau ws pentru handshake rapid
        // Exemplu: doar log, implementare reală va încerca conexiune
        Logger.info('Seed peer:', peer);
        this.discovered.add(peer);
      } catch (e) {
        Logger.warn('Seed peer indisponibil:', peer);
      }
    }
    // TODO: adaugă descoperire din peers existenți (gossip)
    return Array.from(this.discovered);
  }
}
