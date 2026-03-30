// LegacyCompat.js - utilitare pentru compatibilitate cu noduri WebDollar vechi
export class LegacyCompat {
  static parseLegacyMessage(msg) {
    // Exemplu: parsează mesaje text simple sau binare
    if (typeof msg === 'string') {
      try {
        return JSON.parse(msg);
      } catch {
        return { type: 'legacy', payload: msg };
      }
    }
    return msg;
  }

  static buildLegacyHandshake() {
    // Exemplu handshake vechi
    return JSON.stringify({ type: 'handshake', version: 'legacy', nodeType: 'full', time: Date.now() });
  }
}
