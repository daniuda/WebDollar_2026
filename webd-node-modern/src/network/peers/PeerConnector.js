// PeerConnector.js - inițiază conexiuni către peers descoperiți
import { Logger } from '../../utils/logger.js';

export class PeerConnector {
  constructor(peerManager) {
    this.peerManager = peerManager;
  }

  isWebSocketUrl(peerUrl) {
    return peerUrl.startsWith('ws://') || peerUrl.startsWith('wss://');
  }

  normalizePeerUrl(peerUrl) {
    if (this.isWebSocketUrl(peerUrl)) return peerUrl;
    return peerUrl;
  }

  async connectToPeers(peers) {
    for (const peerUrl of peers) {
      if (!this.isWebSocketUrl(peerUrl)) {
        Logger.info('Peer legacy REST (fără WS):', peerUrl);
        continue;
      }

      const normalizedPeerUrl = this.normalizePeerUrl(peerUrl);
      const existing = this.peerManager.peers.get(peerUrl) || this.peerManager.peers.get(normalizedPeerUrl);
      if (existing && existing.ws) continue; // deja conectat

      try {
        const { WebSocket } = await import('ws');
        const ws = new WebSocket(normalizedPeerUrl);
        ws.on('open', () => {
          Logger.info('Conectat la peer:', normalizedPeerUrl);
          this.peerManager.addPeer(normalizedPeerUrl, ws);
        });
        ws.on('error', (err) => {
          Logger.warn('Eroare conectare peer:', normalizedPeerUrl, err.message);
        });
      } catch (e) {
        Logger.warn('Eșec conectare peer:', normalizedPeerUrl, e.message);
      }
    }
  }
}
