// WebSocketServer.js - compatibil cu noduri WebDollar vechi și moderne
import { WebSocketServer as WSS } from 'ws';
import { eventBus } from '../../utils/events.js';
import { Logger } from '../../utils/logger.js';
import { PeerManager } from '../peers/index.js';

export class WebDollarWebSocketServer {
  constructor({ port = 8080 } = {}) {
    this.port = port;
    this.server = new WSS({ port });
    this.peerManager = new PeerManager();
    this.server.on('connection', (ws, req) => this.handleConnection(ws, req));
    Logger.info(`WebDollar WebSocketServer ascultă pe portul ${port}`);
  }

  handleConnection(ws, req) {
    const address = req.socket.remoteAddress;
    this.peerManager.addPeer(address, ws);
    Logger.info('Peer conectat:', address);
    ws.on('message', (msg) => this.handleMessage(ws, msg));
    ws.on('close', () => {
      this.peerManager.removePeer(address);
      Logger.info('Peer deconectat');
    });
    ws.on('error', (err) => Logger.error('Eroare peer:', err));
    // handshake compatibil cu noduri vechi
    this.sendHandshake(ws);
  }

  sendHandshake(ws) {
    // handshake compatibil cu WebDollar vechi (JSON stringificat)
    const handshake = JSON.stringify({
      protocol: 'webdollar',
      version: 1,
      agent: 'webd-node-modern',
      time: Date.now()
    });
    ws.send(handshake);
  }

  handleMessage(ws, msg) {
    let data;
    try {
      data = JSON.parse(msg);
    } catch {
      data = msg; // fallback binar
    }
    eventBus.emit('ws:message', { ws, data });
  }
}
