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
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    });
    const client = new Client({ name: 'varlamov-titles-app', version: '0.1.0' }, { capabilities: {} });
    await client.connect(transport);
    this._client = client;
  }

  async _callTool(name) {
    const result = await this._client.callTool({ name, arguments: {} });
    return result.structuredContent || null;
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
