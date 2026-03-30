// MessageHandler.js - handler modular pentru mesaje compatibile vechi/nou
import { Logger } from '../../utils/logger.js';
import { eventBus } from '../../utils/events.js';
import { MessageTypes } from './MessageTypes.js';

export class MessageHandler {
  constructor() {
    eventBus.on('ws:message', ({ ws, data }) => this.handle(ws, data));
  }

  handle(ws, data) {
    // Compatibilitate: dacă e string, încearcă să parsezi JSON
    let msg = data;
    if (typeof data === 'string') {
      try {
        msg = JSON.parse(data);
      } catch {
        msg = { type: 'legacy', payload: data };
      }
    }
    // Routing după tip
    switch (msg.type) {
      case MessageTypes.PING:
      case 'ping':
        ws.send(JSON.stringify({ type: MessageTypes.PONG, time: Date.now() }));
        break;
      case MessageTypes.PONG:
      case 'pong':
        // heartbeat handled in PeerManager
        break;
      // TODO: alte tipuri de mesaje compatibile
      default:
        Logger.info('Mesaj necunoscut/legacy:', msg);
    }
  }
}
