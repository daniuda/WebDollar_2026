// MessageBuilder.js - utilitar pentru compunere mesaje compatibile
import { MessageTypes } from './MessageTypes.js';

export class MessageBuilder {
  static ping() {
    return JSON.stringify({ type: MessageTypes.PING, time: Date.now() });
  }

  static pong() {
    return JSON.stringify({ type: MessageTypes.PONG, time: Date.now() });
  }

  // TODO: alte tipuri de mesaje (block, tx, handshake, etc.)
}
