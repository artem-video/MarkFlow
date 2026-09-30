const statusEl = document.getElementById('connection-status');
const sequenceEl = document.getElementById('sequence-info');
const installBtn = document.getElementById('install-cep-btn');

// Safety net: Chromium's default behavior for a drop anywhere outside the
// drop-zone is to navigate the whole window to the dropped file:// URL,
// destroying the app UI. Neutralize that at the document level.
document.addEventListener('dragover', (event) => {
  event.preventDefault();
});

document.addEventListener('drop', (event) => {
  event.preventDefault();
});

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
    sequenceEl.textContent = status.error ? `Причина: ${status.error}` : '';
  }
}

const INSTALL_BTN_DEFAULT_TEXT = installBtn.textContent;

installBtn.addEventListener('click', async () => {
  installBtn.disabled = true;
  installBtn.textContent = 'Установка…';
  try {
    const result = await window.api.installCep();
    statusEl.textContent = result.success
      ? 'Коннектор установлен, перезапустите Premiere'
      : `Ошибка установки: ${result.stderr || result.stdout}`;
  } catch (err) {
    statusEl.textContent = `Ошибка установки: ${err.message}`;
  } finally {
    installBtn.disabled = false;
    installBtn.textContent = INSTALL_BTN_DEFAULT_TEXT;
  }
});

refreshStatus();
setInterval(refreshStatus, 5000);

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

const browseBtn = document.getElementById('browse-btn');
browseBtn.addEventListener('click', async (event) => {
  event.stopPropagation();
  const text = await window.api.pickSrtFile();
  if (text == null) return;
  const parsed = await window.api.parseSrt(text);
  renderCaptions(parsed);
});
