#!/usr/bin/env node
/**
 * Test broadcast to mock local node
 */

const socketIo = require('socket.io-client');

const NODE_URL = 'http://localhost:9090';

console.log('Testing broadcast to:', NODE_URL);
console.log('');

const socket = socketIo(NODE_URL, {
  reconnection: true,
  reconnectionAttempts: 3,
  timeout: 5000,
  transports: ['websocket'],
});

socket.on('connect', () => {
  console.log('✓ Connected to mock node!');
  
  // Simulate transaction broadcast
  const mockTxBuffer = Buffer.from(JSON.stringify({
    from: 'test-wallet',
    to: 'recipient-wallet',
    amount: 10,
    nonce: 1,
  }));
  
  console.log('Sending transaction...');
  socket.emit('transactions/new-pending-transaction', { buffer: mockTxBuffer });
  
  console.log('✓ Emitted transactions/new-pending-transaction');
  console.log('  Check mock server output for confirmation\n');
  
  setTimeout(() => {
    socket.disconnect();
    process.exit(0);
  }, 1000);
});

socket.on('connect_error', (err) => {
  console.error('✗ Connection failed:', err?.message || err);
  process.exit(1);
});

setTimeout(() => {
  console.error('✗ Connection timeout');
  process.exit(1);
}, 6000);
