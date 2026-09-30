const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getStatus: () => ipcRenderer.invoke('mcp:status'),
  installCep: () => ipcRenderer.invoke('mcp:install-cep'),
  parseSrt: (text) => ipcRenderer.invoke('srt:parse', text),
  pickSrtFile: () => ipcRenderer.invoke('srt:pick-file'),
});
