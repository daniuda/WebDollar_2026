const downloadSnapshot = require('../lib/download-snapshot');


// CLI installer pentru WebDollar Node - instalare complet automată
const detectOS = require('../lib/os-detect');
const checkNodeVersion = require('../lib/node-check');
const isElevated = require('../lib/admin-check');
const installWindowsBuildTools = require('../lib/install-windows-build-tools');
const checkRepo = require('../lib/repo-check');
const checkNpm = require('../lib/npm-check');
const npmInstall = require('../lib/npm-install');
const path = require('path');

module.exports = async function installNode() {
  const log = (msg) => {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 19);
    console.log(`[${now}] ${msg}`);
  };
  log('=== Instalare automată WebDollar Node ===');
  const os = detectOS();
  log(`[STEP] Sistem de operare detectat: ${os}`);
  // Verificare Node.js >=16
  const nodeVersion = process.versions.node;
  const major = parseInt(nodeVersion.split('.')[0], 10);
  if (major < 16) {
    log(`[ERROR] Node.js >=16 este necesar. Versiune detectată: ${nodeVersion}`);
    return;
  }
  log(`[STEP] Node.js versiune compatibilă: ${nodeVersion}`);
  // Verificare drepturi admin pe Windows
  if (os === 'windows' && !isElevated()) {
    log('[ERROR] Rulează acest installer ca Administrator!');
    return;
  }
  // Instalare build-tools pe Windows
  if (os === 'windows') {
    const t0 = Date.now();
    const ok = await installWindowsBuildTools(log);
    log(`[INFO] Timp instalare build-tools: ${((Date.now()-t0)/1000).toFixed(1)}s`);
    if (!ok) return;
  }
  // Verificare existență repo webd-node
  const baseDir = path.resolve(__dirname, '../../');
  const repoExists = checkRepo(baseDir);
  if (repoExists) {
    log('[STEP] Repo webd-node există deja.');
  } else {
    log('[STEP] Repo webd-node NU există! Se clonează automat...');
    const { execSync } = require('child_process');
    const t0 = Date.now();
    try {
      execSync('git clone https://github.com/WebDollar/Node-WebDollar.git webd-node', { cwd: baseDir, stdio: 'inherit' });
      log(`[STEP] Repo webd-node clonat cu succes. (timp: ${((Date.now()-t0)/1000).toFixed(1)}s)`);
    } catch (e) {
      log('[ERROR] Clonarea repo-ului a eșuat!');
      return;
    }
  }
  // Verificare npm install
  if (checkNpm(baseDir)) {
    log('[STEP] Dependințele npm sunt deja instalate (node_modules există).');
  } else {
    log('[STEP] Dependințele npm NU sunt instalate! (urmează npm install automat cu retry)');
    const t0 = Date.now();
    const ok = await npmInstall(log, path.join(baseDir, 'webd-node'));
    log(`[INFO] Timp npm install: ${((Date.now()-t0)/1000).toFixed(1)}s`);
    if (ok) {
      log('[STEP] npm install a rulat cu succes.');
    } else {
      log('[ERROR] npm install a eșuat după mai multe încercări!');
      return;
    }
  }
  // Suport pentru --dbfolder=cale/customă
  const dbfolderArg = process.argv.find(arg => arg.startsWith('--dbfolder='));
  const dbfolder = dbfolderArg ? dbfolderArg.split('=')[1] : path.join(baseDir, 'webd-node', 'blockchainDB3');
  if (!require('fs').existsSync(dbfolder)) {
    require('fs').mkdirSync(dbfolder, { recursive: true });
  }
  // Caută argumentul --snapshot=...
  const snapshotArg = process.argv.find(arg => arg.startsWith('--snapshot='));
  const snapshotUrl = snapshotArg ? snapshotArg.split('=')[1] : undefined;
  const t0 = Date.now();
  const snapshotOk = await downloadSnapshot(log, dbfolder, snapshotUrl);
  log(`[INFO] Timp descărcare snapshot: ${((Date.now()-t0)/1000).toFixed(1)}s`);
  if (!snapshotOk) {
    log('[WARN] Nu s-a putut descărca snapshot-ul. Nodul va sincroniza normal.');
  } else {
    const unzipSnapshot = require('../lib/unzip-snapshot');
    const t1 = Date.now();
    const unzipOk = await unzipSnapshot(log, dbfolder);
    log(`[INFO] Timp dezarhivare snapshot: ${((Date.now()-t1)/1000).toFixed(1)}s`);
    if (!unzipOk) {
      log('[WARN] Snapshot-ul nu a putut fi dezarhivat.');
    } else {
      log('[STEP] Snapshot blockchain dezarhivat și gata de folosit.');
    }
  }
  log('Instalare completă! WebDollar Node este gata de folosit.');
};
