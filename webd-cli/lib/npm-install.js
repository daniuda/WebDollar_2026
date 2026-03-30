const { execSync } = require('child_process');
const path = require('path');

module.exports = function npmInstall(baseDir) {
  const cwd = path.join(baseDir, 'webd-node');
  try {
    execSync('npm install', { cwd, stdio: 'inherit' });
    return true;
  } catch (e) {
    return false;
  }
}
