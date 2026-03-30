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
  // Suport pentru --port=PORT și --dbfolder=CALE
  const portArg = process.argv.find(arg => arg.startsWith('--port='));
  const port = portArg ? portArg.split('=')[1] : undefined;
  const dbfolderArg = process.argv.find(arg => arg.startsWith('--dbfolder='));
  const dbfolder = dbfolderArg ? dbfolderArg.split('=')[1] : undefined;

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
  // Configurare rapidă port/folder custom (doar exemplu, adaptare după structura pool-ului)
  if (port) {
    log(`[STEP] Setare port custom pool: ${port} (modifică manual config dacă e nevoie)`);
    // Exemplu: scriere port în config.json dacă există
    const configPath = poolDir + '/config.json';
    if (fs.existsSync(configPath)) {
      try {
        const config = JSON.parse(fs.readFileSync(configPath));
        config.port = parseInt(port, 10);
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
        log('[STEP] Portul pool setat în config.json');
      } catch (e) {
        log('[WARN] Nu s-a putut seta portul automat în config.json');
      }
    }
  }
  if (dbfolder) {
    log(`[STEP] Setare folder custom pool: ${dbfolder} (modifică manual config dacă e nevoie)`);
    // Exemplu: scriere folder în config.json dacă există
    const configPath = poolDir + '/config.json';
    if (fs.existsSync(configPath)) {
      try {
        const config = JSON.parse(fs.readFileSync(configPath));
        config.dbfolder = dbfolder;
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
        log('[STEP] Folderul pool setat în config.json');
      } catch (e) {
        log('[WARN] Nu s-a putut seta folderul automat în config.json');
      }
    }
  }
  log('[STEP] Instalare pool completă!');
};
