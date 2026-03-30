// Pornește WebDollar Pool cu logare și verificare automată
const path = require('path');
const { exec } = require('child_process');

module.exports = function startPool() {
  const poolPath = path.join(__dirname, '../../webd-pool');
  const isWin = process.platform.startsWith('win');
  const cmd = isWin ? 'npm run start' : 'npm run start'; // adaptare dacă pool-ul are script dedicat
  console.log('=== Pornire WebDollar Pool ===');
  exec(cmd, { cwd: poolPath, stdio: 'inherit' }, (err) => {
    if (err) {
      console.log('[ERROR] Pornirea pool-ului a eșuat:', err.message);
    } else {
      console.log('[STEP] Pool-ul rulează!');
    }
  });
};
