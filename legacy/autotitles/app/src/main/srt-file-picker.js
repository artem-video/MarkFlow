async function pickSrtFile({ dialog, fs }) {
  const result = await dialog.showOpenDialog({
    title: 'Выбрать .srt-файл',
    filters: [{ name: 'SubRip subtitles', extensions: ['srt'] }],
    properties: ['openFile'],
  });
  if (result.canceled || !result.filePaths[0]) {
    return null;
  }
  return fs.readFileSync(result.filePaths[0], 'utf-8');
}

module.exports = { pickSrtFile };
