// WebSocketServer.js - compatibil cu noduri WebDollar vechi și moderne
import { WebSocketServer as WSS } from 'ws';
import { eventBus } from '../../utils/events.js';
import { Logger } from '../../utils/logger.js';
import { PeerManager } from '../peers/index.js';
import { MessageHandler } from '../messages/MessageHandler.js';
import { Handshake } from '../messages/Handshake.js';

export class WebSocketServer {
  constructor(port = 8080) {
    this.port = port;
    this.server = null;
    this.peerManager = new PeerManager();
    this.messageHandler = new MessageHandler();
  }

  start(port = null) {
    if (port) this.port = port;
    this.server = new WSS({ port: this.port });
    this.server.on('error', (err) => {
      if (err && err.code === 'EADDRINUSE') {
        Logger.warn(`Port WS ${this.port} este deja folosit; continui fără server WS local.`);
        return;
      }
      Logger.error('Eroare server WS:', err);
    });
    this.server.on('connection', (ws, req) => this.handleConnection(ws, req));
    Logger.info(`WebDollar WebSocketServer ascultă pe portul ${this.port}`);
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
    // handshake compatibil cu noduri vechi/nou
    ws.send(JSON.stringify(Handshake.buildHandshakePayload()));
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

  broadcastTx(txBuffer) {
    if (!this.server) return 0;
    const payload = JSON.stringify({
      type: 'transactions/new-pending-transaction',
      data: { buffer: Array.from(txBuffer) },
    });
    let sent = 0;
    for (const client of this.server.clients) {
      if (client.readyState === 1 /* OPEN */) {
        try { client.send(payload); sent++; } catch (_) {}
      }
    }
    return sent;
  }
}
