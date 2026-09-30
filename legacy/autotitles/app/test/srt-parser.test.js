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
  const srt = '﻿1\n00:00:00,000 --> 00:00:01,000\nТекст\n';
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
