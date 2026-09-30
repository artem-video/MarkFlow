const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { buildInstallCepArgs, runInstallCep } = require('../src/main/cep-installer');
const { resolvePremiereMcpEntry } = require('../src/main/mcp-client');

test('buildInstallCepArgs points at premiere-pro-mcp entry with --install-cep', () => {
  const args = buildInstallCepArgs();
  assert.deepEqual(args, [resolvePremiereMcpEntry(), '--install-cep']);
});

function fakeChildProcess() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  return child;
}

test('runInstallCep resolves success:true and captures stdout on exit code 0', async () => {
  const child = fakeChildProcess();
  const spawnFn = () => child;
  const resultPromise = runInstallCep({ spawnFn });
  child.stdout.emit('data', Buffer.from('CEP plugin installed\n'));
  child.emit('close', 0);
  const result = await resultPromise;
  assert.deepEqual(result, { success: true, stdout: 'CEP plugin installed\n', stderr: '', exitCode: 0 });
});

test('runInstallCep resolves success:false and captures stderr on non-zero exit code', async () => {
  const child = fakeChildProcess();
  const spawnFn = () => child;
  const resultPromise = runInstallCep({ spawnFn });
  child.stderr.emit('data', Buffer.from('permission denied\n'));
  child.emit('close', 1);
  const result = await resultPromise;
  assert.equal(result.success, false);
  assert.equal(result.stderr, 'permission denied\n');
  assert.equal(result.exitCode, 1);
});

test('runInstallCep resolves success:false when the process itself errors (e.g. spawn ENOENT)', async () => {
  const child = fakeChildProcess();
  const spawnFn = () => child;
  const resultPromise = runInstallCep({ spawnFn });
  child.emit('error', new Error('spawn ENOENT'));
  const result = await resultPromise;
  assert.equal(result.success, false);
  assert.match(result.stderr, /spawn ENOENT/);
});
