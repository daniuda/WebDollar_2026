// Pornește WebDollar Node cu logare și verificare automată
const path = require('path');
const { exec } = require('child_process');

module.exports = function startNode() {
  const nodePath = path.join(__dirname, '../../webd-node');
  const entry = path.join(nodePath, 'start.sh');
  const isWin = process.platform.startsWith('win');
  const cmd = isWin ? 'npm run start' : `bash ${entry}`;
  console.log('=== Pornire WebDollar Node ===');
  exec(cmd, { cwd: nodePath, stdio: 'inherit' }, (err) => {
    if (err) {
      console.log('[ERROR] Pornirea nodului a eșuat:', err.message);
    } else {
      console.log('[STEP] Nodul rulează!');
    }
  });
};
