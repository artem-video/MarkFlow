const test = require('node:test');
const assert = require('node:assert/strict');
const { pickSrtFile } = require('../src/main/srt-file-picker');

test('pickSrtFile returns the file content when a file is chosen', async () => {
  const dialog = {
    showOpenDialog: async () => ({ canceled: false, filePaths: ['/some/path/captions.srt'] }),
  };
  const fs = {
    readFileSync: (filePath, encoding) => {
      assert.equal(filePath, '/some/path/captions.srt');
      assert.equal(encoding, 'utf-8');
      return '1\n00:00:00,000 --> 00:00:01,000\nПривет\n';
    },
  };
  const text = await pickSrtFile({ dialog, fs });
  assert.equal(text, '1\n00:00:00,000 --> 00:00:01,000\nПривет\n');
});

test('pickSrtFile returns null when the dialog is cancelled', async () => {
  const dialog = {
    showOpenDialog: async () => ({ canceled: true, filePaths: [] }),
  };
  const fs = { readFileSync: () => { throw new Error('should not be called'); } };
  const text = await pickSrtFile({ dialog, fs });
  assert.equal(text, null);
});

test('pickSrtFile filters the dialog to .srt files', async () => {
  let capturedOptions;
  const dialog = {
    showOpenDialog: async (options) => {
      capturedOptions = options;
      return { canceled: true, filePaths: [] };
    },
  };
  const fs = { readFileSync: () => { throw new Error('should not be called'); } };
  await pickSrtFile({ dialog, fs });
  assert.deepEqual(capturedOptions.filters, [{ name: 'SubRip subtitles', extensions: ['srt'] }]);
  assert.deepEqual(capturedOptions.properties, ['openFile']);
});
