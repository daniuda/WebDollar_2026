#!/usr/bin/env node
/**
 * Mock WebDollar node server for testing transaction broadcast
 * Listens on localhost:9090 and simulates the transaction protocol
 */

const http = require('http');
const socketIo = require('socket.io');

const PORT = 9090;

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Mock WebDollar Node - Socket.IO active\n');
});

const io = socketIo(server, {
  cors: { origin: '*' },
  transports: ['websocket', 'polling'],
});

io.on('connection', (socket) => {
  console.log(`[Mock Node] Client connected: ${socket.id}`);

  socket.on('transactions/new-pending-transaction', (payload) => {
    console.log('[Mock Node] Received transactions/new-pending-transaction');
    console.log('  - Payload keys:', Object.keys(payload));
    console.log('  - Buffer size:', payload.buffer ? payload.buffer.length : 'N/A');
    
    if (payload.buffer) {
      console.log('  ✓ Transaction buffer received successfully');
    } else {
      console.log('  ✗ No buffer in payload!');
    }
  });

  socket.on('disconnect', () => {
    console.log(`[Mock Node] Client disconnected: ${socket.id}`);
  });

  socket.on('error', (err) => {
    console.error(`[Mock Node] Socket error from ${socket.id}:`, err);
  });
});

server.listen(PORT, 'localhost', () => {
  console.log(`
╔════════════════════════════════════════╗
║  Mock WebDollar Node Server            ║
║  Listening on: http://localhost:${PORT}  ║
║  Socket.IO: Active                     ║
╚════════════════════════════════════════╝

To test from app:
  - Set pool config node to: http://localhost:9090
  - Or update extractNodeUrlFromPoolConfig() test
  - Send a payment
  - Should see "Received transactions/new-pending-transaction" here

Press Ctrl+C to stop
  `);
});

process.on('SIGINT', () => {
  console.log('\n\nShutting down...');
  server.close();
  process.exit(0);
});
