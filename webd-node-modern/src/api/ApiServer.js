// ApiServer.js - API REST simplu pentru WebDollar modern
import { Logger } from '../utils/logger.js';
import { ChainStorage } from '../storage/ChainStorage.js';

export class ApiServer {
  constructor(chain) {
    this.chain = chain;
    this.server = null;
    this.workerManager = null;
    this.wsServer = null;
  }

  setWorkerManager(wm) {
    this.workerManager = wm;
  }

  setWsServer(ws) {
    this.wsServer = ws;
  }

  async start(port = 3001) {
    const express = (await import('express')).default;
    const app = express();
    app.use(express.json());

    // ── chain endpoints ──────────────────────────────────────────────────────
    app.get('/block/:height', (req, res) => {
      const block = this.chain.getBlock(Number(req.params.height));
      if (block) res.json(block);
      else res.status(404).json({ error: 'Block not found' });
    });
    app.get('/latest', (req, res) => {
      res.json(this.chain.getLatestBlock());
    });
    app.get('/height', (req, res) => {
      res.json({ height: this.chain.getHeight() });
    });

    // ── pool/worker endpoints ────────────────────────────────────────────────
    const wm = () => this.workerManager;

    const requireWM = (res) => {
      if (!wm()) { res.status(503).json({ error: 'pool nu e pornit' }); return false; }
      return true;
    };

    /** POST /worker/auth  { walletAddress, workerId?, poolKey? } */
    app.post('/worker/auth', (req, res) => {
      if (!requireWM(res)) return;
      try {
        const { walletAddress, workerId, poolKey } = req.body || {};
        const result = wm().auth(walletAddress, workerId, poolKey);
        res.json({ result: true, ...result });
      } catch (e) {
        res.status(e.status || 400).json({ result: false, message: e.message });
      }
    });

    /** GET /worker/job?token=... */
    app.get('/worker/job', (req, res) => {
      if (!requireWM(res)) return;
      const token = req.query.token;
      try {
        const job = wm().getJob(token);
        res.json({ result: true, job });
      } catch (e) {
        res.status(e.status || 400).json({ result: false, message: e.message });
      }
    });

    /** POST /worker/share  { token, jobId, nonce, hash } */
    app.post('/worker/share', (req, res) => {
      if (!requireWM(res)) return;
      const { token, ...shareData } = req.body || {};
      try {
        const validation = wm().submitShare(token, shareData);
        res.json({ result: true, ...validation });
      } catch (e) {
        res.status(e.status || 400).json({ result: false, message: e.message });
      }
    });

    /** GET /worker/stats?token=... */
    app.get('/worker/stats', (req, res) => {
      if (!requireWM(res)) return;
      const token = req.query.token;
      try {
        const stats = wm().getStats(token);
        res.json({ result: true, ...stats });
      } catch (e) {
        res.status(e.status || 400).json({ result: false, message: e.message });
      }
    });

    /** GET /pool/stats  (public) */
    app.get('/pool/stats', (req, res) => {
      if (!requireWM(res)) return;
      res.json({ result: true, ...wm().getPoolStats() });
    });

    /** POST /tx/broadcast  { hex: "..." } — broadcast tranzacție către peers */
    app.post('/tx/broadcast', (req, res) => {
      try {
        const { hex } = req.body || {};
        if (!hex || typeof hex !== 'string' || !/^[0-9a-fA-F]+$/.test(hex)) {
          return res.status(400).json({ result: false, message: 'hex invalid' });
        }
        const buf = Buffer.from(hex, 'hex');
        const peers = this.wsServer ? this.wsServer.broadcastTx(buf) : 0;
        res.json({ result: true, bytes: buf.length, peers_notified: peers });
      } catch (e) {
        res.status(500).json({ result: false, message: e.message });
      }
    });

    this.server = await new Promise((resolve, reject) => {
      const server = app.listen(port, () => {
        Logger.info('API server pornit pe portul', port);
        resolve(server);
      });

      server.on('error', (err) => {
        if (err && err.code === 'EADDRINUSE') {
          reject(new Error(`Port API ${port} este deja folosit`));
          return;
        }
        reject(err);
      });
    });
  }

  stop() {
    if (this.server) this.server.close();
  }
}
