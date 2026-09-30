const test = require('node:test');
const assert = require('node:assert/strict');
const { registerIpcHandlers } = require('../src/main/ipc-handlers');

function fakeIpcMain() {
  return {
    handlers: {},
    handle(channel, fn) {
      this.handlers[channel] = fn;
    },
  };
}

test('registers mcp:status and delegates to mcpClient.getStatus', async () => {
  const ipcMain = fakeIpcMain();
  const mcpClient = { getStatus: async () => ({ connected: true }) };
  registerIpcHandlers({ ipcMain, mcpClient, srtParser: {}, cepInstaller: {}, filePicker: {} });
  const result = await ipcMain.handlers['mcp:status']();
  assert.deepEqual(result, { connected: true });
});

test('registers mcp:install-cep and delegates to cepInstaller.runInstallCep', async () => {
  const ipcMain = fakeIpcMain();
  const cepInstaller = { runInstallCep: async () => ({ success: true }) };
  registerIpcHandlers({ ipcMain, mcpClient: {}, srtParser: {}, cepInstaller, filePicker: {} });
  const result = await ipcMain.handlers['mcp:install-cep']();
  assert.deepEqual(result, { success: true });
});

test('registers srt:parse and delegates to srtParser.parseSrt with the given text', async () => {
  const ipcMain = fakeIpcMain();
  const srtParser = { parseSrt: (text) => ({ entries: [], errors: [], receivedText: text }) };
  registerIpcHandlers({ ipcMain, mcpClient: {}, srtParser, cepInstaller: {}, filePicker: {} });
  const result = await ipcMain.handlers['srt:parse']({}, 'SOME SRT TEXT');
  assert.equal(result.receivedText, 'SOME SRT TEXT');
});

test('registers srt:pick-file and delegates to filePicker.pickSrtFile', async () => {
  const ipcMain = fakeIpcMain();
  const filePicker = { pickSrtFile: async () => 'FILE TEXT' };
  registerIpcHandlers({ ipcMain, mcpClient: {}, srtParser: {}, cepInstaller: {}, filePicker });
  const result = await ipcMain.handlers['srt:pick-file']();
  assert.equal(result, 'FILE TEXT');
});
