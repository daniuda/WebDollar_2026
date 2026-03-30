// Descarcă automat snapshot-ul blockchain și îl plasează în blockchainDB3
const https = require('https');
const fs = require('fs');
const path = require('path');

module.exports = async function downloadSnapshot(log, destFolder, customUrl) {
  const snapshotUrl = customUrl || 'https://webdollar.network/snapshot/blockchainDB3-latest.zip';
  const destZip = path.join(destFolder, 'blockchainDB3-latest.zip');
  log('Descărcare snapshot blockchain de la: ' + snapshotUrl);
  return new Promise((resolve) => {
    const file = fs.createWriteStream(destZip);
    https.get(snapshotUrl, (response) => {
      if (response.statusCode !== 200) {
        log('Eroare la descărcare snapshot: ' + response.statusCode);
        resolve(false);
        return;
      }
      response.pipe(file);
      file.on('finish', () => {
        file.close(() => {
          log('Snapshot descărcat cu succes: ' + destZip);
          resolve(true);
        });
      });
    }).on('error', (err) => {
      fs.unlink(destZip, () => {});
      log('Eroare la descărcare snapshot: ' + err.message);
      resolve(false);
    });
  });
}
