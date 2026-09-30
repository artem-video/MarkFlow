# Мост к Premiere + каркас приложения — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Electron-приложение, которое подтверждённо (не мок-данными) подключается к запущенному Premiere через `premiere-pro-mcp`, показывает активную секвенцию, и после drag-and-drop .srt-файла показывает распарсенный список реплик.

**Architecture:** Electron main-процесс спавнит `premiere-pro-mcp` (npm-пакет, MIT) как MCP-сервер по stdio и говорит с ним как MCP-клиент (`@modelcontextprotocol/sdk`) — без LLM в рантайме. Renderer — чистый UI без Node-доступа (contextIsolation, preload с `contextBridge`). Парсинг .srt — чистая функция без внешних зависимостей.

**Tech Stack:** Node.js (CommonJS), Electron, `premiere-pro-mcp` (spawned локально из `node_modules`), `@modelcontextprotocol/sdk` (клиентская часть), встроенный тестраннер `node --test` (без Jest/Vitest — YAGNI).

**Spec:** [2026-08-20-мост-к-premiere-design.md](2026-08-20-мост-к-premiere-design.md)

## Global Constraints

- Код живёт в `C:\Users\Artem\Videos\VARLAMOV\Daily Shorts\Варламов Шортс Титры\app\` (подпапка внутри Daily Shorts, решение пользователя). Эта подпапка — отдельный git-репозиторий (git init выполнен 2026-08-20), не связанный с остальной «Daily Shorts» — крупные видеофайлы в него не попадают. Шаги «commit» из этого плана выполняются как обычно, локально, без push куда-либо.
- MOGRT — не используется нигде в этом плане.
- Кроссплатформенность (Windows + Mac) — не использовать пути или API, специфичные только для одной ОС, во всём коде из этого плана.
- Renderer не имеет прямого доступа к Node/Electron API — только через `window.api`, выставленный preload-скриптом (`contextIsolation: true`, `nodeIntegration: false`).
- Упаковка/дистрибуция приложения (electron-builder и т.п.) — вне скоупа этого плана.

---

## Task 1: Каркас Electron-проекта

**Files:**
- Create: `app/package.json`
- Create: `app/src/main/index.js`
- Create: `app/src/preload.js`
- Create: `app/src/renderer/index.html`

**Interfaces:**
- Produces: рабочее Electron-приложение, запускаемое `npm start` из `app/`, открывающее окно с заглушкой. Дальнейшие задачи наполняют `main/index.js`, `preload.js` и `renderer/index.html` реальной логикой.

- [ ] **Step 1: Создать структуру папок и package.json**

Создать папку `app/` и внутри неё:

```json
{
  "name": "varlamov-titles-app",
  "version": "0.1.0",
  "private": true,
  "main": "src/main/index.js",
  "scripts": {
    "start": "electron .",
    "test": "node --test test/"
  }
}
```

- [ ] **Step 2: Установить зависимости**

Run (из `app/`):
```bash
npm install --save electron premiere-pro-mcp @modelcontextprotocol/sdk
```

Expected: `node_modules/` содержит `electron`, `premiere-pro-mcp`, `@modelcontextprotocol/sdk`, `package-lock.json` создан.

- [ ] **Step 3: Заглушка main-процесса**

`app/src/main/index.js`:
```js
const { app, BrowserWindow } = require('electron');
const path = require('node:path');

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
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
```

- [ ] **Step 4: Заглушка preload и renderer**

`app/src/preload.js`:
```js
// Наполняется в Task 5.
```

`app/src/renderer/index.html`:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Варламов Шортс Титры — Мост к Premiere</title>
</head>
<body>
  <h1>Каркас готов</h1>
</body>
</html>
```

- [ ] **Step 5: Ручная проверка**

Run: `npm start` (из `app/`)
Expected: открывается окно Electron с заголовком «Каркас готов». Закрыть окно, вернуться в терминал без ошибок в консоли.

---

## Task 2: Парсер .srt

**Files:**
- Create: `app/src/shared/srt-parser.js`
- Test: `app/test/srt-parser.test.js`

**Interfaces:**
- Produces: `parseSrt(text: string) -> { entries: Array<{index: number, startSeconds: number, endSeconds: number, text: string}>, errors: Array<{blockNumber: number, raw: string, message: string}> }`
- Consumes: ничего (чистая функция).

- [ ] **Step 1: Написать падающие тесты**

`app/test/srt-parser.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { parseSrt } = require('../src/shared/srt-parser');

test('parses a single simple entry', () => {
  const srt = '1\n00:00:00,000 --> 00:00:02,500\nПривет мир\n';
  const result = parseSrt(srt);
  assert.equal(result.entries.length, 1);
  assert.deepEqual(result.entries[0], {
    index: 1,
    startSeconds: 0,
    endSeconds: 2.5,
    text: 'Привет мир',
  });
  assert.equal(result.errors.length, 0);
});

test('parses multi-line text within one entry', () => {
  const srt = '1\n00:00:01,000 --> 00:00:03,000\nСтрока один\nСтрока два\n';
  const result = parseSrt(srt);
  assert.equal(result.entries[0].text, 'Строка один\nСтрока два');
});

test('parses multiple entries separated by blank lines', () => {
  const srt = '1\n00:00:00,000 --> 00:00:01,000\nПервая\n\n2\n00:00:01,000 --> 00:00:02,000\nВторая\n';
  const result = parseSrt(srt);
  assert.equal(result.entries.length, 2);
  assert.equal(result.entries[1].text, 'Вторая');
  assert.equal(result.entries[1].startSeconds, 1);
});

test('handles CRLF line endings', () => {
  const srt = '1\r\n00:00:00,000 --> 00:00:01,000\r\nТекст\r\n';
  const result = parseSrt(srt);
  assert.equal(result.entries.length, 1);
  assert.equal(result.entries[0].text, 'Текст');
});

test('strips UTF-8 BOM at the start of the file', () => {
  const srt = '\uFEFF1\n00:00:00,000 --> 00:00:01,000\nТекст\n';
  const result = parseSrt(srt);
  assert.equal(result.entries.length, 1);
  assert.equal(result.entries[0].index, 1);
});

test('skips a malformed block and reports an error, continuing to parse the rest', () => {
  const srt = '1\nНЕ ТАЙМКОД\nТекст первого\n\n2\n00:00:05,000 --> 00:00:06,000\nВторой блок валиден\n';
  const result = parseSrt(srt);
  assert.equal(result.entries.length, 1);
  assert.equal(result.entries[0].text, 'Второй блок валиден');
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].blockNumber, 1);
});

test('returns empty entries and no errors for an empty string', () => {
  const result = parseSrt('');
  assert.deepEqual(result.entries, []);
  assert.deepEqual(result.errors, []);
});
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `node --test test/srt-parser.test.js` (из `app/`)
Expected: FAIL — `Cannot find module '../src/shared/srt-parser'`.

- [ ] **Step 3: Реализовать парсер**

`app/src/shared/srt-parser.js`:
```js
const TIMECODE_RE = /^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/;

function timecodeToSeconds(h, m, s, ms) {
  return Number(h) * 3600 + Number(m) * 60 + Number(s) + Number(ms) / 1000;
}

function parseSrt(text) {
  const entries = [];
  const errors = [];

  const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  const blocks = normalized.split(/\n\s*\n/).map((b) => b.trim()).filter((b) => b.length > 0);

  blocks.forEach((block, i) => {
    const blockNumber = i + 1;
    const lines = block.split('\n');
    if (lines.length < 2) {
      errors.push({ blockNumber, raw: block, message: 'блок короче двух строк' });
      return;
    }

    const indexLine = lines[0].trim();
    const index = Number.parseInt(indexLine, 10);
    if (Number.isNaN(index)) {
      errors.push({ blockNumber, raw: block, message: `первая строка не число: "${indexLine}"` });
      return;
    }

    const timecodeMatch = lines[1].match(TIMECODE_RE);
    if (!timecodeMatch) {
      errors.push({ blockNumber, raw: block, message: `вторая строка не тайм-код: "${lines[1]}"` });
      return;
    }

    const [, h1, m1, s1, ms1, h2, m2, s2, ms2] = timecodeMatch;
    const textLines = lines.slice(2);
    entries.push({
      index,
      startSeconds: timecodeToSeconds(h1, m1, s1, ms1),
      endSeconds: timecodeToSeconds(h2, m2, s2, ms2),
      text: textLines.join('\n'),
    });
  });

  return { entries, errors };
}

module.exports = { parseSrt, timecodeToSeconds };
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `node --test test/srt-parser.test.js`
Expected: PASS, 7/7 tests green.

---

## Task 3: MCP-клиент к premiere-pro-mcp

**Files:**
- Create: `app/src/main/mcp-client.js`
- Test: `app/test/mcp-client.test.js`

**Interfaces:**
- Consumes: `premiere-pro-mcp` (npm-пакет, установлен в Task 1), `@modelcontextprotocol/sdk` (`Client`, `StdioClientTransport`).
- Produces:
  - `class McpClient` с методами `connect(): Promise<void>`, `getStatus(): Promise<{connected: boolean, sequenceName: string|null, sequenceDurationSeconds: number|null, error: string|null}>`, `disconnect(): Promise<void>`.
  - `formatStatus(pingResult, activeSequenceResult): {connected, sequenceName, sequenceDurationSeconds}` — чистая функция, экспортируется отдельно для тестов.
  - `resolvePremiereMcpEntry(): string` — путь к `dist/index.js` внутри установленного пакета `premiere-pro-mcp`.

Реальные формы ответов инструментов (проверено вживую через `premiere-pro-mcp` на Premiere 26.0.0, «16.08 ЧП» проект):
```json
// ping
{"ok":true,"tool":"ping","data":{"connected":true,"premiereVersion":"26.0.0","projectName":"16.08 ЧП- Copy.prproj","activeSequence":"ЧП 338 2"}}
// get_active_sequence
{"ok":true,"tool":"get_active_sequence","data":{"name":"16_08_CHP_narezka - (9x16)","id":"...","end":79.44, "...": "остальные поля не нужны для статуса"}}
```
MCP `callTool` возвращает `{ content: [{ type: "text", text: "<эта JSON-строка>" }] }` — нужно `JSON.parse(result.content[0].text)`.

- [ ] **Step 1: Написать падающие тесты**

`app/test/mcp-client.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { McpClient, formatStatus } = require('../src/main/mcp-client');

function fakeToolResult(payload) {
  return { content: [{ type: 'text', text: JSON.stringify(payload) }] };
}

test('formatStatus: not connected returns all nulls', () => {
  const result = formatStatus({ data: { connected: false } }, null);
  assert.deepEqual(result, { connected: false, sequenceName: null, sequenceDurationSeconds: null });
});

test('formatStatus: connected with full active-sequence data', () => {
  const ping = { data: { connected: true, activeSequence: 'ЧП 338 2' } };
  const activeSeq = { data: { name: '16_08_CHP_narezka - (9x16)', end: 79.44 } };
  const result = formatStatus(ping, activeSeq);
  assert.deepEqual(result, {
    connected: true,
    sequenceName: '16_08_CHP_narezka - (9x16)',
    sequenceDurationSeconds: 79.44,
  });
});

test('formatStatus: connected but no active-sequence data falls back to ping name', () => {
  const ping = { data: { connected: true, activeSequence: 'ЧП 338 2' } };
  const result = formatStatus(ping, null);
  assert.deepEqual(result, {
    connected: true,
    sequenceName: 'ЧП 338 2',
    sequenceDurationSeconds: null,
  });
});

test('McpClient.getStatus: reports connected true with sequence info on success', async () => {
  const fakeClient = {
    callTool: async ({ name }) => {
      if (name === 'ping') {
        return fakeToolResult({ data: { connected: true, activeSequence: 'ЧП 338 2' } });
      }
      if (name === 'get_active_sequence') {
        return fakeToolResult({ data: { name: '16_08_CHP_narezka - (9x16)', end: 79.44 } });
      }
      throw new Error(`unexpected tool: ${name}`);
    },
  };
  const client = new McpClient({ client: fakeClient });
  const status = await client.getStatus();
  assert.deepEqual(status, {
    connected: true,
    sequenceName: '16_08_CHP_narezka - (9x16)',
    sequenceDurationSeconds: 79.44,
    error: null,
  });
});

test('McpClient.getStatus: reports connected false when ping says not connected', async () => {
  const fakeClient = {
    callTool: async () => fakeToolResult({ data: { connected: false } }),
  };
  const client = new McpClient({ client: fakeClient });
  const status = await client.getStatus();
  assert.equal(status.connected, false);
  assert.equal(status.error, null);
});

test('McpClient.getStatus: reports connected false with error message when ping call throws (e.g. timeout)', async () => {
  const fakeClient = {
    callTool: async () => {
      throw new Error('Command timed out after 5000ms');
    },
  };
  const client = new McpClient({ client: fakeClient });
  const status = await client.getStatus();
  assert.equal(status.connected, false);
  assert.equal(status.error, 'Command timed out after 5000ms');
});
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `node --test test/mcp-client.test.js`
Expected: FAIL — `Cannot find module '../src/main/mcp-client'`.

- [ ] **Step 3: Реализовать McpClient**

`app/src/main/mcp-client.js`:
```js
function resolvePremiereMcpEntry() {
  return require.resolve('premiere-pro-mcp/dist/index.js');
}

function formatStatus(pingResult, activeSequenceResult) {
  const pingData = pingResult && pingResult.data;
  if (!pingData || !pingData.connected) {
    return { connected: false, sequenceName: null, sequenceDurationSeconds: null };
  }
  const seq = activeSequenceResult && activeSequenceResult.data;
  return {
    connected: true,
    sequenceName: seq ? seq.name : pingData.activeSequence || null,
    sequenceDurationSeconds: seq ? seq.end : null,
  };
}

class McpClient {
  constructor({ client } = {}) {
    this._client = client || null;
  }

  async connect() {
    if (this._client) return;
    const { Client } = await import('@modelcontextprotocol/sdk/client/index.js');
    const { StdioClientTransport } = await import('@modelcontextprotocol/sdk/client/stdio.js');
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [resolvePremiereMcpEntry()],
    });
    const client = new Client({ name: 'varlamov-titles-app', version: '0.1.0' }, { capabilities: {} });
    await client.connect(transport);
    this._client = client;
  }

  async _callTool(name) {
    const result = await this._client.callTool({ name, arguments: {} });
    const text = result.content && result.content[0] && result.content[0].text;
    return text ? JSON.parse(text) : null;
  }

  async getStatus() {
    let pingResult;
    try {
      pingResult = await this._callTool('ping');
    } catch (err) {
      return { connected: false, sequenceName: null, sequenceDurationSeconds: null, error: err.message };
    }
    const pingData = pingResult && pingResult.data;
    if (!pingData || !pingData.connected) {
      return { ...formatStatus(pingResult, null), error: null };
    }
    let activeSequenceResult = null;
    try {
      activeSequenceResult = await this._callTool('get_active_sequence');
    } catch {
      activeSequenceResult = null;
    }
    return { ...formatStatus(pingResult, activeSequenceResult), error: null };
  }

  async disconnect() {
    if (this._client && typeof this._client.close === 'function') {
      await this._client.close();
    }
    this._client = null;
  }
}

module.exports = { McpClient, formatStatus, resolvePremiereMcpEntry };
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `node --test test/mcp-client.test.js`
Expected: PASS, 6/6 tests green.

---

## Task 4: Установка CEP-коннектора

**Files:**
- Create: `app/src/main/cep-installer.js`
- Test: `app/test/cep-installer.test.js`

**Interfaces:**
- Consumes: `resolvePremiereMcpEntry()` из Task 3 (`app/src/main/mcp-client.js`).
- Produces: `buildInstallCepArgs(): string[]`, `runInstallCep({ spawnFn? }): Promise<{success: boolean, stdout: string, stderr: string, exitCode: number|null}>`.

- [ ] **Step 1: Написать падающие тесты**

`app/test/cep-installer.test.js`:
```js
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
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `node --test test/cep-installer.test.js`
Expected: FAIL — `Cannot find module '../src/main/cep-installer'`.

- [ ] **Step 3: Реализовать cep-installer**

`app/src/main/cep-installer.js`:
```js
const { spawn } = require('node:child_process');
const { resolvePremiereMcpEntry } = require('./mcp-client');

function buildInstallCepArgs() {
  return [resolvePremiereMcpEntry(), '--install-cep'];
}

function runInstallCep({ spawnFn = spawn } = {}) {
  return new Promise((resolve) => {
    const args = buildInstallCepArgs();
    const child = spawnFn(process.execPath, args);
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
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `node --test test/cep-installer.test.js`
Expected: PASS, 4/4 tests green.

---

## Task 5: IPC-обвязка и preload

**Files:**
- Create: `app/src/main/ipc-handlers.js`
- Modify: `app/src/preload.js`
- Modify: `app/src/main/index.js`
- Test: `app/test/ipc-handlers.test.js`

**Interfaces:**
- Consumes: `McpClient` (Task 3), `{ parseSrt }` (Task 2), `{ runInstallCep }` (Task 4).
- Produces: `registerIpcHandlers({ ipcMain, mcpClient, srtParser, cepInstaller })` регистрирует три канала: `mcp:status`, `mcp:install-cep`, `srt:parse`. `window.api` в renderer получает `getStatus()`, `installCep()`, `parseSrt(text)`.

- [ ] **Step 1: Написать падающие тесты**

`app/test/ipc-handlers.test.js`:
```js
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
  registerIpcHandlers({ ipcMain, mcpClient, srtParser: {}, cepInstaller: {} });
  const result = await ipcMain.handlers['mcp:status']();
  assert.deepEqual(result, { connected: true });
});

test('registers mcp:install-cep and delegates to cepInstaller.runInstallCep', async () => {
  const ipcMain = fakeIpcMain();
  const cepInstaller = { runInstallCep: async () => ({ success: true }) };
  registerIpcHandlers({ ipcMain, mcpClient: {}, srtParser: {}, cepInstaller });
  const result = await ipcMain.handlers['mcp:install-cep']();
  assert.deepEqual(result, { success: true });
});

test('registers srt:parse and delegates to srtParser.parseSrt with the given text', async () => {
  const ipcMain = fakeIpcMain();
  const srtParser = { parseSrt: (text) => ({ entries: [], errors: [], receivedText: text }) };
  registerIpcHandlers({ ipcMain, mcpClient: {}, srtParser, cepInstaller: {} });
  const result = await ipcMain.handlers['srt:parse']({}, 'SOME SRT TEXT');
  assert.equal(result.receivedText, 'SOME SRT TEXT');
});
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `node --test test/ipc-handlers.test.js`
Expected: FAIL — `Cannot find module '../src/main/ipc-handlers'`.

- [ ] **Step 3: Реализовать ipc-handlers**

`app/src/main/ipc-handlers.js`:
```js
function registerIpcHandlers({ ipcMain, mcpClient, srtParser, cepInstaller }) {
  ipcMain.handle('mcp:status', async () => mcpClient.getStatus());
  ipcMain.handle('mcp:install-cep', async () => cepInstaller.runInstallCep());
  ipcMain.handle('srt:parse', async (_event, text) => srtParser.parseSrt(text));
}

module.exports = { registerIpcHandlers };
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `node --test test/ipc-handlers.test.js`
Expected: PASS, 3/3 tests green.

- [ ] **Step 5: Наполнить preload.js**

`app/src/preload.js`:
```js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getStatus: () => ipcRenderer.invoke('mcp:status'),
  installCep: () => ipcRenderer.invoke('mcp:install-cep'),
  parseSrt: (text) => ipcRenderer.invoke('srt:parse', text),
});
```

- [ ] **Step 6: Подключить всё в main/index.js**

`app/src/main/index.js` (полностью заменяет заглушку из Task 1):
```js
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const { McpClient } = require('./mcp-client');
const srtParser = require('../shared/srt-parser');
const cepInstaller = require('./cep-installer');
const { registerIpcHandlers } = require('./ipc-handlers');

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
}

app.whenReady().then(async () => {
  registerIpcHandlers({ ipcMain, mcpClient, srtParser, cepInstaller });
  try {
    await mcpClient.connect();
  } catch (err) {
    console.error('Не удалось подключиться к premiere-pro-mcp:', err);
  }
  createWindow();
});

app.on('window-all-closed', async () => {
  await mcpClient.disconnect();
  if (process.platform !== 'darwin') app.quit();
});
```

- [ ] **Step 7: Ручная проверка**

Run: `npm start` (из `app/`)
Expected: окно открывается без ошибок в DevTools console (Ctrl+Shift+I / Cmd+Option+I), даже если Premiere не запущен (соединение просто не установится, `mcpClient.connect()` может упасть в лог — это ожидаемо на этом шаге, UI ещё не тронут).

---

## Task 6: UI статуса подключения и активной секвенции

**Files:**
- Modify: `app/src/renderer/index.html`
- Create: `app/src/renderer/renderer.js`
- Create: `app/src/renderer/styles.css`

**Interfaces:**
- Consumes: `window.api.getStatus()` из Task 5 (`{connected, sequenceName, sequenceDurationSeconds, error}`).

Ручное UI-тестирование вместо unit-тестов — это чистая DOM-логика, а автоматизировать её означало бы тянуть e2e-фреймворк (Playwright/Spectron) ради MVP, что не оправдано на этом этапе (см. спеку: только юнит-тесты парсера + ручной smoke-тест).

- [ ] **Step 1: Обновить index.html**

`app/src/renderer/index.html`:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Варламов Шортс Титры — Мост к Premiere</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <h1>Мост к Premiere</h1>
  <section id="status-panel">
    <p id="connection-status">Проверка подключения…</p>
    <p id="sequence-info"></p>
    <button id="install-cep-btn" hidden>Установить коннектор</button>
  </section>
  <section id="drop-zone">Перетащите сюда .srt-файл</section>
  <ul id="captions-list"></ul>
  <script src="renderer.js"></script>
</body>
</html>
```

- [ ] **Step 2: Написать renderer.js (статус + активная секвенция)**

`app/src/renderer/renderer.js`:
```js
const statusEl = document.getElementById('connection-status');
const sequenceEl = document.getElementById('sequence-info');
const installBtn = document.getElementById('install-cep-btn');

async function refreshStatus() {
  const status = await window.api.getStatus();
  if (status.connected) {
    statusEl.textContent = 'Подключено к Premiere';
    installBtn.hidden = true;
    sequenceEl.textContent = status.sequenceName
      ? `Активная секвенция: ${status.sequenceName}${
          status.sequenceDurationSeconds != null
            ? ` (${Math.round(status.sequenceDurationSeconds)} сек)`
            : ''
        }`
      : '';
  } else {
    statusEl.textContent = 'Нет подключения — откройте Premiere или установите коннектор';
    installBtn.hidden = false;
    sequenceEl.textContent = '';
  }
}

installBtn.addEventListener('click', async () => {
  installBtn.disabled = true;
  installBtn.textContent = 'Установка…';
  const result = await window.api.installCep();
  installBtn.disabled = false;
  installBtn.textContent = 'Установить коннектор';
  statusEl.textContent = result.success
    ? 'Коннектор установлен, перезапустите Premiere'
    : `Ошибка установки: ${result.stderr || result.stdout}`;
});

refreshStatus();
setInterval(refreshStatus, 5000);
```

- [ ] **Step 3: Минимальные стили**

`app/src/renderer/styles.css`:
```css
body { font-family: sans-serif; padding: 16px; }
#drop-zone {
  margin-top: 16px;
  padding: 40px;
  border: 2px dashed #999;
  text-align: center;
  color: #666;
}
#drop-zone.drag-over { border-color: #2b8; color: #2b8; }
.warning { color: #b60; }
```

- [ ] **Step 4: Ручная проверка**

Run: `npm start`, при закрытом Premiere.
Expected: статус «Нет подключения…», видна кнопка «Установить коннектор».

Run: `npm start`, при открытом Premiere с установленным CEP-коннектором.
Expected: статус «Подключено к Premiere», строка с именем и длительностью активной секвенции, кнопка скрыта.

---

## Task 7: Drag-and-drop .srt и список реплик

**Files:**
- Modify: `app/src/renderer/renderer.js`

**Interfaces:**
- Consumes: `window.api.parseSrt(text)` из Task 5, возвращает `{entries, errors}` (форма из Task 2).

- [ ] **Step 1: Добавить обработку drag-and-drop и рендер списка**

Дописать в конец `app/src/renderer/renderer.js`:
```js
const dropZone = document.getElementById('drop-zone');
const listEl = document.getElementById('captions-list');

function renderCaptions(parsed) {
  listEl.innerHTML = '';
  for (const entry of parsed.entries) {
    const li = document.createElement('li');
    li.textContent = `${entry.startSeconds.toFixed(2)}–${entry.endSeconds.toFixed(2)}: ${entry.text}`;
    listEl.appendChild(li);
  }
  if (parsed.errors.length > 0) {
    const warn = document.createElement('li');
    warn.textContent = `Пропущено блоков с ошибками: ${parsed.errors.length}`;
    warn.className = 'warning';
    listEl.appendChild(warn);
  }
}

dropZone.addEventListener('dragover', (event) => {
  event.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', async (event) => {
  event.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const text = await file.text();
  const parsed = await window.api.parseSrt(text);
  renderCaptions(parsed);
});
```

- [ ] **Step 2: Ручная проверка**

Подготовить тестовый файл `app/test/fixtures/sample.srt`:
```
1
00:00:00,000 --> 00:00:02,000
Тестовая реплика один

2
00:00:02,000 --> 00:00:04,500
Тестовая реплика два
```

Run: `npm start`, перетащить `sample.srt` в зону дропа.
Expected: под зоной появляется список из двух пунктов с текстом и таймингами, совпадающими с файлом. Строки об ошибках нет.

---

## Известное отклонение от спеки

Спека требует «обрыв соединения → статус «отключено» + попытка переподключения». В этом плане переподключение реализовано неявно: `refreshStatus()` в Task 6 опрашивает `getStatus()` каждые 5 секунд, и каждый вызов — это свежий `ping`, так что как только Premiere/CEP-коннектор снова доступны, статус сам восстановится без отдельной кнопки «переподключиться». Это покрывает основной случай (монтажёр закрыл/открыл Premiere). Не покрыт более редкий случай — если сам процесс `premiere-pro-mcp` (Node) упадёт: `McpClient` не респавнит его автоматически в рамках этого плана. Если это станет реальной проблемой на Task 8, стоит завести отдельную небольшую задачу на респавн процесса, а не блокировать этим текущую подсистему.

## Task 8: Сквозная проверка на реальном Premiere (manual smoke test)

Не про код — финальная приёмка подсистемы целиком, как определено в Definition of done спеки.

- [ ] **Step 1**: Открыть реальный проект в Premiere (например «16.08 ЧП»), активная секвенция — любая с несколькими клипами.
- [ ] **Step 2**: Убедиться, что CEP-коннектор `premiere-pro-mcp` установлен (если нет — использовать кнопку «Установить коннектор» из Task 6, перезапустить Premiere, проверить `premiere-pro-mcp --doctor` вручную при проблемах).
- [ ] **Step 3**: Запустить приложение (`npm start` из `app/`). Убедиться, что статус «Подключено к Premiere» и имя/длительность активной секвенции совпадают с реальным проектом.
- [ ] **Step 4**: В Premiere сделать Export → Captions/Subtitles на любой секвенции с Captions-дорожкой, получить .srt.
- [ ] **Step 5**: Перетащить полученный .srt в приложение. Сверить построчно распарсенный список с содержимым .srt-файла (текст, начало, конец).
- [ ] **Step 6**: Закрыть Premiere, убедиться что статус в приложении меняется на «Нет подключения…» в течение ~5 секунд (интервал опроса из Task 6).

Если все 6 шагов проходят — Definition of done подсистемы «Мост к Premiere + каркас приложения» выполнено, план закрыт.
