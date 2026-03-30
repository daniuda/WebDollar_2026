// Dezarhivează snapshot-ul blockchainDB3-latest.zip în folderul blockchainDB3
const fs = require('fs');
const path = require('path');
const unzipper = require('unzipper');

module.exports = async function unzipSnapshot(log, baseDir) {
  const zipPath = path.join(baseDir, 'blockchainDB3-latest.zip');
  const destDir = path.join(baseDir, 'blockchainDB3');
  if (!fs.existsSync(zipPath)) {
    log('Arhiva snapshot nu există: ' + zipPath);
    return false;
  }
  log('Dezarhivare snapshot blockchain...');
  return new Promise((resolve) => {
    fs.createReadStream(zipPath)
      .pipe(unzipper.Extract({ path: destDir }))
      .on('close', () => {
        log('Snapshot dezarhivat cu succes în: ' + destDir);
        resolve(true);
      })
      .on('error', (err) => {
        log('Eroare la dezarhivare: ' + err.message);
        resolve(false);
      });
  });
};
