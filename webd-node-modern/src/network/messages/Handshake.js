// Handshake.js - handshake compatibil vechi/nou pentru WebDollar
import { MessageTypes } from './MessageTypes.js';

export class Handshake {
  static buildHandshakePayload(nodeVersion = 'modern', nodeType = 'full') {
    return {
      type: MessageTypes.HANDSHAKE,
      version: nodeVersion,
      nodeType,
      time: Date.now(),
    };
  }

  static parseHandshake(msg) {
    // Acceptă handshake vechi sau nou
    if (typeof msg === 'string') {
      try {
        msg = JSON.parse(msg);
      } catch {
        return null;
      }
    }
    if (msg.type === MessageTypes.HANDSHAKE || msg.type === 'handshake') {
      return msg;
    }
    return null;
  }
}
