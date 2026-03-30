// Instalare automată WebDollar Pool (schelet de bază)
const detectOS = require('../lib/os-detect');
const checkNodeVersion = require('../lib/node-check');
const path = require('path');

module.exports = async function installPool() {
  const log = console.log;
  log('=== Instalare automată WebDollar Pool ===');
  const os = detectOS();
  log(`[STEP] Sistem de operare detectat: ${os}`);
  const nodeVersion = process.versions.node;
  const major = parseInt(nodeVersion.split('.')[0], 10);
  if (major < 16) {
    log(`[ERROR] Node.js >=16 este necesar. Versiune detectată: ${nodeVersion}`);
    return;
  }
  log(`[STEP] Node.js versiune compatibilă: ${nodeVersion}`);
  // Clonare automată repo pool dacă lipsește
  const baseDir = path.resolve(__dirname, '../../');
  const poolDir = path.join(baseDir, 'webd-pool');
  const fs = require('fs');
  if (!fs.existsSync(poolDir)) {
    log('[STEP] Repo webd-pool NU există! Se clonează automat...');
    const { execSync } = require('child_process');
    try {
      execSync('git clone https://github.com/WebDollarPool/WebDollar-Pool.git webd-pool', { cwd: baseDir, stdio: 'inherit' });
      log('[STEP] Repo webd-pool clonat cu succes.');
    } catch (e) {
      log('[ERROR] Clonarea repo-ului pool a eșuat!');
      return;
    }
  } else {
    log('[STEP] Repo webd-pool există deja.');
  }
  // npm install automat în webd-pool
  log('[STEP] Instalare dependențe npm pentru pool...');
  try {
    const { execSync } = require('child_process');
    execSync('npm install', { cwd: poolDir, stdio: 'inherit' });
    log('[STEP] npm install pentru pool a rulat cu succes.');
  } catch (e) {
    log('[ERROR] npm install pentru pool a eșuat!');
    return;
  }
  log('[STEP] Instalare pool completă!');
};
