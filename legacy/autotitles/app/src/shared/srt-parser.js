const TIMECODE_RE = /^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/;

function timecodeToSeconds(h, m, s, ms) {
  return Number(h) * 3600 + Number(m) * 60 + Number(s) + Number(ms) / 1000;
}

function parseSrt(text) {
  const entries = [];
  const errors = [];

  const normalized = text.replace(/^﻿/, '').replace(/\r\n/g, '\n');
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
