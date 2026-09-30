function registerIpcHandlers({ ipcMain, mcpClient, srtParser, cepInstaller, filePicker }) {
  ipcMain.handle('mcp:status', async () => mcpClient.getStatus());
  ipcMain.handle('mcp:install-cep', async () => cepInstaller.runInstallCep());
  ipcMain.handle('srt:parse', async (_event, text) => srtParser.parseSrt(text));
  ipcMain.handle('srt:pick-file', async () => filePicker.pickSrtFile());
}

module.exports = { registerIpcHandlers };
