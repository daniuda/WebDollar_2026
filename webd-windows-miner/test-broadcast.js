#!/usr/bin/env node
/**
 * Test script to verify NodeTxBroadcaster functionality
 * Simulates payment broadcast to a WebDollar node
 */

const socketIo = require('socket.io-client');

// Test config - extract from pool config string used in app
const poolConfig = 'pool/1/1/1/SpyClub/0.0001/374d24d549e73f05280b239d96d7c6b28f15aabb5d41e89818b660a9ebc3276e/https:$$node.spyclub.ro:8080';
const parts = poolConfig.split('/');
const nodeUrlPart = parts.slice(7).join('/');
const nodeUrl = nodeUrlPart.replace('$$', '//').replace(/\/$/, '');

console.log('=== NodeTxBroadcaster Test ===');
console.log('Pool config:', poolConfig);
console.log('Extracted node URL:', nodeUrl);

// Disable TLS verification like the app does
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const socket = socketIo(nodeUrl, {
  reconnection: true,
  reconnectionAttempts: 3,
  reconnectionDelay: 1000,
  timeout: 5000,
  transports: ['websocket'],
});

socket.on('connect', () => {
  console.log('[socket.io] Connected to node!');
  
  // Simulate a transaction broadcast
  const mockTxBuffer = Buffer.from('test-transaction-data', 'utf8');
  console.log('[test] Broadcasting mock transaction...');
  socket.emit('transactions/new-pending-transaction', { buffer: mockTxBuffer });
  
  console.log('[test] Emitted transactions/new-pending-transaction');
  
  setTimeout(() => {
    socket.disconnect();
    console.log('[test] Test complete');
    process.exit(0);
  }, 2000);
});

socket.on('connect_error', (err) => {
  console.error('[socket.io] Connect error:', err?.message || err);
  process.exit(1);
});

socket.on('error', (err) => {
  console.error('[socket.io] Error:', err?.message || err);
});

socket.on('disconnect', () => {
  console.log('[socket.io] Disconnected');
});

setTimeout(() => {
  console.error('[test] Connection timeout');
  process.exit(1);
}, 10000);
