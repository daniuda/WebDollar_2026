// Detectează dacă scriptul rulează cu drepturi de administrator/root
module.exports = function isElevated() {
  if (process.platform.startsWith('win')) {
    const execSync = require('child_process').execSync;
    try {
      execSync('fsutil dirty query %systemdrive%');
      return true;
    } catch {
      return false;
    }
  } else {
    return process.getuid && process.getuid() === 0;
  }
};