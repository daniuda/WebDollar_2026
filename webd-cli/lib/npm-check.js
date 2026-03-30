const fs = require('fs');
const path = require('path');

module.exports = function checkNodeModules(baseDir) {
  const nodeModulesPath = path.join(baseDir, 'webd-node', 'node_modules');
  return fs.existsSync(nodeModulesPath);
}
