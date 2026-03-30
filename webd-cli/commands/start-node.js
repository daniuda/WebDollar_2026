// Pornește WebDollar Node cu logare și verificare automată
const path = require('path');
const { exec } = require('child_process');

// Pornește WebDollar Node cu port custom (ex: webd start node 8080)
module.exports = function startNode() {
  const nodePath = path.join(__dirname, '../../webd-node');
  const isWin = process.platform.startsWith('win');
  // Preia portul din argumente CLI dacă există
  const portArg = process.argv[4];
  let cmd = isWin ? 'npm run start' : 'npm run start';
  if (portArg) {
    cmd += ` -- --port=${portArg}`;
  }
  console.log('=== Pornire WebDollar Node ===');
  exec(cmd, { cwd: nodePath, stdio: 'inherit' }, (err) => {
    if (err) {
      console.log('[ERROR] Pornirea nodului a eșuat:', err.message);
    } else {
      console.log('[STEP] Nodul rulează!');
    }
  });
};
