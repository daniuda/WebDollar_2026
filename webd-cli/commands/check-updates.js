// Verifică dacă există update-uri pentru CLI, node și pool
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function getLocalVersion(pkgPath) {
  if (fs.existsSync(pkgPath)) {
    try {
      const pkg = JSON.parse(fs.readFileSync(pkgPath));
      return pkg.version || '0.0.0';
    } catch {
      return '0.0.0';
    }
  }
  return '0.0.0';
}

function getRemoteVersion(repo) {
  try {
    const res = execSync(`git ls-remote --tags ${repo}`).toString();
    const tags = res.match(/refs\/tags\/(v?\d+\.\d+\.\d+)/g) || [];
    if (tags.length === 0) return '0.0.0';
    const versions = tags.map(t => t.split('/').pop().replace('v','')).sort();
    return versions[versions.length-1];
  } catch {
    return '0.0.0';
  }
}

module.exports = function checkUpdates() {
  const logPath = path.join(__dirname, '../log.txt');
  const logMsg = (msg) => {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 19);
    const line = `[${now}] ${msg}`;
    console.log(line);
    fs.appendFileSync(logPath, line + '\n');
  };
  logMsg('=== Verificare update-uri CLI/node/pool ===');
  // CLI
  const cliLocal = getLocalVersion(path.join(__dirname, '../package.json'));
  const cliRemote = getRemoteVersion('https://github.com/daniuda/WebDollar_2026.git');
  logMsg(`[CLI] Local: ${cliLocal} | Remote: ${cliRemote}`);
  // Node
  const nodeLocal = getLocalVersion(path.join(__dirname, '../../webd-node/package.json'));
  const nodeRemote = getRemoteVersion('https://github.com/WebDollar/Node-WebDollar.git');
  logMsg(`[Node] Local: ${nodeLocal} | Remote: ${nodeRemote}`);
  // Pool
  const poolLocal = getLocalVersion(path.join(__dirname, '../../webd-pool/package.json'));
  const poolRemote = getRemoteVersion('https://github.com/WebDollarPool/WebDollar-Pool.git');
  logMsg(`[Pool] Local: ${poolLocal} | Remote: ${poolRemote}`);
  // Notificare dacă există update
  if (cliLocal !== cliRemote) logMsg('[CLI] Există o versiune nouă!');
  if (nodeLocal !== nodeRemote) logMsg('[Node] Există o versiune nouă!');
  if (poolLocal !== poolRemote) logMsg('[Pool] Există o versiune nouă!');
};
