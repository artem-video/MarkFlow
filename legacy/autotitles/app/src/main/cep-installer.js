const { spawn } = require('node:child_process');
const { resolvePremiereMcpEntry } = require('./mcp-client');

function buildInstallCepArgs() {
  return [resolvePremiereMcpEntry(), '--install-cep'];
}

function runInstallCep({ spawnFn = spawn } = {}) {
  return new Promise((resolve) => {
    const args = buildInstallCepArgs();
    const child = spawnFn(process.execPath, args, {
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    });
    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('close', (code) => {
      resolve({ success: code === 0, stdout, stderr, exitCode: code });
    });
    child.on('error', (err) => {
      resolve({ success: false, stdout, stderr: stderr + err.message, exitCode: null });
    });
  });
}

module.exports = { buildInstallCepArgs, runInstallCep };
