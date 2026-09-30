const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { McpClient } = require('./mcp-client');
const srtParser = require('../shared/srt-parser');
const cepInstaller = require('./cep-installer');
const { registerIpcHandlers } = require('./ipc-handlers');
const { pickSrtFile } = require('./srt-file-picker');

const filePicker = { pickSrtFile: () => pickSrtFile({ dialog, fs }) };

const mcpClient = new McpClient();

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, '../preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, '../renderer/index.html'));

  win.webContents.on('will-navigate', (event) => {
    event.preventDefault();
  });
}

app.whenReady().then(() => {
  registerIpcHandlers({ ipcMain, mcpClient, srtParser, cepInstaller, filePicker });
  createWindow();
  mcpClient.connect().catch((err) => {
    console.error('Не удалось подключиться к premiere-pro-mcp:', err);
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on('before-quit', async () => {
  await mcpClient.disconnect();
});
