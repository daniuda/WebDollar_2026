// PeerManager.js - gestiune peers compatibilă cu noduri vechi și moderne
import { eventBus } from '../../utils/events.js';
import { Logger } from '../../utils/logger.js';
import { PeerDiscovery } from './PeerDiscovery.js';
import { SEED_PEERS } from './peers.config.js';

export class PeerManager {
  constructor() {
    this.peers = new Map(); // key: address, value: {ws, lastSeen, blacklist, whitelist}
    this.heartbeatInterval = 30000; // ms
    this.discovery = new PeerDiscovery(SEED_PEERS);
    setInterval(() => this.heartbeatAll(), this.heartbeatInterval);
    eventBus.on('ws:message', ({ ws, data }) => this.handleMessage(ws, data));
    this.autoDiscover();
  }

  async autoDiscover() {
    const peers = await this.discovery.discover();
    Logger.info('Peers descoperiți:', peers);
    // TODO: inițiază conexiuni către peers noi
  }

  addPeer(address, ws) {
    this.peers.set(address, { ws, lastSeen: Date.now(), blacklist: false, whitelist: false });
    Logger.info('Peer adăugat:', address);
  }

  removePeer(address) {
    this.peers.delete(address);
    Logger.info('Peer eliminat:', address);
  }

  blacklistPeer(address) {
    if (this.peers.has(address)) {
      this.peers.get(address).blacklist = true;
      Logger.warn('Peer blacklist:', address);
    }
  }

  whitelistPeer(address) {
    if (this.peers.has(address)) {
      this.peers.get(address).whitelist = true;
      Logger.info('Peer whitelist:', address);
    }
  }

  heartbeatAll() {
    for (const [address, peer] of this.peers.entries()) {
      try {
        peer.ws.send(JSON.stringify({ type: 'ping', time: Date.now() }));
      } catch (e) {
        Logger.warn('Peer nu răspunde, elimin:', address);
        this.removePeer(address);
      }
    }
  }

  handleMessage(ws, data) {
    // ping/pong, update lastSeen, reconectare dacă e nevoie
    if (data && data.type === 'pong') {
      for (const [address, peer] of this.peers.entries()) {
        if (peer.ws === ws) {
          peer.lastSeen = Date.now();
        }
      }
    }
    // alte mesaje compatibile cu noduri vechi
  }
}
