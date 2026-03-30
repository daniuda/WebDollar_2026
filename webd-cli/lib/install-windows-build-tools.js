// Instalează windows-build-tools dacă lipsesc (doar pe Windows)
module.exports = async function installWindowsBuildTools(log) {
  const { exec } = require('child_process');
  return new Promise((resolve) => {
    log('Instalare windows-build-tools...');
    exec('npm install --global --production windows-build-tools', (err, stdout, stderr) => {
      if (err) {
        log('Eroare la instalarea windows-build-tools: ' + stderr);
        resolve(false);
      } else {
        log('windows-build-tools instalat cu succes.');
        resolve(true);
      }
    });
  });
};