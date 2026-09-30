const test = require('node:test');
const assert = require('node:assert/strict');
const { McpClient, formatStatus } = require('../src/main/mcp-client');

function fakeToolResult(payload) {
  // Real MCP tool results carry the parsed data on `structuredContent`
  // (verified live against premiere-pro-mcp) alongside a `content[0].text`
  // JSON-string duplicate; `_callTool` reads `structuredContent` directly.
  return {
    content: [{ type: 'text', text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
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
