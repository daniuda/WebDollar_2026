// ApiServer.js - API REST simplu pentru WebDollar modern
import { Logger } from '../utils/logger.js';
import fs from 'fs';
import path from 'path';
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

    // Nou: block by hash
    app.get('/block-by-hash/:hash', async (req, res) => {
      try {
        const block = await this.chain.getBlockByHash(req.params.hash);
        if (block) res.json(block);
        else res.status(404).json({ error: 'Block not found' });
      } catch (e) {
        res.status(500).json({ error: e.message });
      }
    });

    app.get('/latest', (req, res) => {
      res.json(this.chain.getLatestBlock());
    });
    app.get('/height', (req, res) => {
      res.json({ height: this.chain.getHeight() });
    });

    app.get('/chain', async (req, res) => {
      try {
        const latestBlock = this.chain.getLatestBlock?.() || {};
        const chainHeight = this.chain.getHeight?.() || 0;

        // Try to get actual network height from legacy node
        let networkHeight = chainHeight;
        let syncing = false;
        try {
          const legacyResp = await (await import('axios')).default.get('http://127.0.0.1:8081/top', { timeout: 5000 });
          if (legacyResp.data?.top) {
            networkHeight = legacyResp.data.top;
            syncing = chainHeight < networkHeight;
          }
        } catch (e) {
          // Fallback to local height if legacy node unavailable
        }

        res.json({
          height: networkHeight,
          syncing,
          transactionsCount: (latestBlock.transactions || []).length,
          hash: latestBlock.hash || '',
          id: latestBlock.id || ''
        });
      } catch (e) {
        res.status(500).json({ error: e.message });
      }
    });

    app.get('/stake/total', (req, res) => {
      try {
        const chain = this.chain;
        const blocks = chain?.blocks || [];
        let totalStake = 0;

        // Calculate from all addresses in blockchain (if available)
        // For now, use a simple calculation based on block count
        // In production, this should read from proper address balance DB
        if (blocks.length > 0) {
          // Sum totalWebd from all blocks
          totalStake = blocks.reduce((sum, b) => sum + (Number(b.totalWebd) || 0), 0);
        }

        res.json({
          totalStakeWebd: totalStake || 0,
          totalStakeAtomic: (totalStake || 0) * 10000000,
          walletCount: blocks.length || 0,
          source: 'db:blockchain.sum'
        });
      } catch (e) {
        res.status(500).json({ error: e.message });
      }
    });

    app.get('/blocks', async (req, res) => {
      try {
        const limit = Math.min(parseInt(req.query.limit) || 10, 100);
        const blocks = [];

        // Try to get blocks from legacy node first (more complete data)
        try {
          const axios = await import('axios');
          const legacyResp = await axios.default.get('http://127.0.0.1:8081/top', { timeout: 5000 });
          const topHeight = legacyResp.data?.top || 0;

          if (topHeight > 0) {
            const startHeight = Math.max(0, topHeight - limit + 1);
            const legacyBlocksResp = await axios.default.get(`http://127.0.0.1:8081/blocks/between/${startHeight}/${topHeight}`, { timeout: 10000 });

            if (legacyBlocksResp.data?.blocks && Array.isArray(legacyBlocksResp.data.blocks)) {
              for (const block of legacyBlocksResp.data.blocks) {
                const txAmount = (block.data?.transactions || []).reduce((sum, tx) => {
                  if (tx?.to && Array.isArray(tx.to)) {
                    return sum + tx.to.reduce((s, t) => s + (Number(t.amount) || 0), 0);
                  }
                  return sum;
                }, 0);

                blocks.push({
                  hash: block.hash || `block-${block.height}`,
                  height: block.height || 0,
                  timestamp: (block.timeStamp || block.timestamp) * 1000,
                  minerAddress: block.data?.minerAddress || '',
                  transactions: block.data?.transactions || [],
                  totalWebd: txAmount,
                  rewardWebd: null
                });
              }
              res.json(blocks.reverse());
              return;
            }
          }
        } catch (e) {
          Logger.warn('Fallback la local blocks din legacy node failed:', e.message);
        }

        // Fallback: use local chain
        const chainBlocks = this.chain.blocks || [];
        const startIdx = Math.max(0, chainBlocks.length - limit);

        for (let i = startIdx; i < chainBlocks.length; i++) {
          const block = chainBlocks[i];
          if (block) {
            blocks.push({
              hash: block.hash || '',
              height: block.height || i,
              timestamp: block.timestamp || Date.now(),
              minerAddress: block.minerAddress || '',
              transactions: block.transactions || [],
              totalWebd: block.totalWebd || 0,
              rewardWebd: block.rewardWebd || null
            });
          }
        }
        res.json(blocks.reverse());
      } catch (e) {
        res.status(500).json({ error: e.message });
      }
    });

    app.get('/api/visit/stats', (req, res) => {
      try {
        const visitFile = '/home/ubuntu/webd-explorer-next/visit_count.json';
        if (fs.existsSync(visitFile)) {
          const data = JSON.parse(fs.readFileSync(visitFile, 'utf8'));
          const pages = Object.entries(data.pages || {}).map(([page, count]) => ({
            page,
            count: typeof count === 'number' ? count : 0
          }));
          res.json({
            total: data.total || 0,
            pages
          });
        } else {
          res.json({ total: 0, pages: [] });
        }
      } catch (e) {
        res.json({ total: 0, pages: [], error: e.message });
      }
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
