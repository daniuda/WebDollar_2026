// Instalează și pornește WebDollar Node în Docker
const { exec } = require('child_process');

module.exports = function dockerNode() {
  const image = 'webdollar/node';
  const container = 'webdollar-node';
  const ports = '-p 80:80 -p 443:443';
  const volumes = '-v webdollar_data:/blockchainDB3';
  const cmd = `docker run -d --restart=always ${volumes} --name ${container} ${ports} ${image}`;
  console.log('=== Instalare și pornire WebDollar Node în Docker ===');
  exec(`docker pull ${image}`, (err, stdout, stderr) => {
    if (err) {
      console.log('[ERROR] Eroare la docker pull:', stderr);
      return;
    }
    console.log('[STEP] Imaginea Docker descărcată.');
    exec(cmd, (err2, stdout2, stderr2) => {
      if (err2) {
        console.log('[ERROR] Eroare la pornirea containerului:', stderr2);
      } else {
        console.log('[STEP] Containerul WebDollar Node rulează!');
      }
    });
  });
};
