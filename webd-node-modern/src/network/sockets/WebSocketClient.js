// WebSocketClient.js - compatibil cu noduri WebDollar vechi și moderne
import { WebSocket } from 'ws';
import { eventBus } from '../../utils/events.js';
import { Logger } from '../../utils/logger.js';

export class WebDollarWebSocketClient {
  constructor({ url }) {
    this.url = url;
    this.ws = new WebSocket(url);
    this.ws.on('open', () => this.handleOpen());
    this.ws.on('message', (msg) => this.handleMessage(msg));
    this.ws.on('close', () => Logger.info('Deconectat de la', url));
    this.ws.on('error', (err) => Logger.error('Eroare client:', err));
  }

  handleOpen() {
    Logger.info('Conectat la peer:', this.url);
    this.sendHandshake();
  }

  sendHandshake() {
    // handshake compatibil cu WebDollar vechi (JSON stringificat)
    const handshake = JSON.stringify({
      protocol: 'webdollar',
      version: 1,
      agent: 'webd-node-modern',
      time: Date.now()
    });
    this.ws.send(handshake);
  }

  handleMessage(msg) {
    try {
      let data;
      try {
        data = JSON.parse(msg);
      } catch {
        data = msg; // fallback binar
      }
      eventBus.emit('ws:message', { ws: this.ws, data });
    } catch (err) {
      Logger.error('Eroare la procesare mesaj:', err);
    }
  }
}
