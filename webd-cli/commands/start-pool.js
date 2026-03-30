// Pornește WebDollar Pool cu logare și verificare automată
const path = require('path');
const { exec } = require('child_process');

// Pornește WebDollar Pool cu port/folder custom (ex: webd start pool --port=PORT --dbfolder=CALE)
module.exports = function startPool() {
  const poolPath = path.join(__dirname, '../../webd-pool');
  const isWin = process.platform.startsWith('win');
  // Preia portul și folderul din argumente CLI dacă există
  const portArg = process.argv.find(arg => arg.startsWith('--port='));
  const port = portArg ? portArg.split('=')[1] : undefined;
  const dbfolderArg = process.argv.find(arg => arg.startsWith('--dbfolder='));
  const dbfolder = dbfolderArg ? dbfolderArg.split('=')[1] : undefined;
  let cmd = isWin ? 'npm run start' : 'npm run start';
  if (port) {
    cmd += ` -- --port=${port}`;
  }
  if (dbfolder) {
    cmd += ` -- --dbfolder=${dbfolder}`;
  }
  console.log('=== Pornire WebDollar Pool ===');
  exec(cmd, { cwd: poolPath, stdio: 'inherit' }, (err) => {
    if (err) {
      console.log('[ERROR] Pornirea pool-ului a eșuat:', err.message);
    } else {
      console.log('[STEP] Pool-ul rulează!');
    }
  });
};
