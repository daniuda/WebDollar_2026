const fs = require('fs');
const path = require('path');

module.exports = function checkRepoExists(baseDir) {
  const repoPath = path.join(baseDir, 'webd-node');
  return fs.existsSync(repoPath) && fs.existsSync(path.join(repoPath, 'package.json'));
}
