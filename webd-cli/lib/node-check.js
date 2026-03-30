const { execSync } = require('child_process');

module.exports = function checkNodeInstalled() {
  try {
    const version = execSync('node -v', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
    return version;
  } catch {
    return null;
  }
}
