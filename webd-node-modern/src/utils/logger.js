// logger.js - Modern logging utility
export class Logger {
  static info(...args) { console.log('[INFO]', ...args); }
  static warn(...args) { console.warn('[WARN]', ...args); }
  static error(...args) { console.error('[ERROR]', ...args); }
  static debug(...args) { if (process.env.DEBUG) console.debug('[DEBUG]', ...args); }
}
