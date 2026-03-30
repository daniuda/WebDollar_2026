// PeerConnector.js - inițiază conexiuni către peers descoperiți
import { Logger } from '../../utils/logger.js';

export class PeerConnector {
  constructor(peerManager) {
    this.peerManager = peerManager;
  }

  async connectToPeers(peers) {
    for (const peerUrl of peers) {
      if (this.peerManager.peers.has(peerUrl)) continue; // deja conectat
      try {
        const { WebSocket } = await import('ws');
        const ws = new WebSocket(peerUrl);
        ws.on('open', () => {
          Logger.info('Conectat la peer:', peerUrl);
          this.peerManager.addPeer(peerUrl, ws);
        });
        ws.on('error', (err) => {
          Logger.warn('Eroare conectare peer:', peerUrl, err.message);
        });
      } catch (e) {
        Logger.warn('Eșec conectare peer:', peerUrl, e.message);
      }
    }
  }
}
