const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
function client(env) {
  const calls = [];
  const storage = new Map();
  const module = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync('lib/api/client.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(js, {
    module, exports: module.exports, process: { env }, window: {},
    sessionStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    fetch: async (url, init) => { calls.push({ url, init }); return { ok: true, status: 200, json: async () => ({}) }; },
  });
  return { ...module.exports, calls };
}
test('production login uses chatbot prefix even with empty base URL', async () => {
  const api = client({ NODE_ENV: 'production', NEXT_PUBLIC_API_BASE_URL: '' });
  await api.apiRequest('/api/v1/admin/auth/login', { method: 'POST' });
  assert.equal(api.calls[0].url, '/chatbot/api/v1/admin/auth/login');
});
test('local development and explicit backend overrides work', () => {
  assert.equal(client({ NODE_ENV: 'development' }).API_BASE_URL, 'http://localhost:9000');
  assert.equal(client({ NEXT_PUBLIC_API_BASE_URL: 'https://backend.test/' }).API_BASE_URL, 'https://backend.test');
});
test('application creation sends admin JWT to chatbot backend', async () => {
  const api = client({ NODE_ENV: 'production' });
  api.setAccessToken('test-token');
  await api.adminRequest('/applications', { method: 'POST', body: '{}' });
  assert.equal(api.calls[0].url, '/chatbot/api/v1/admin/applications');
  assert.equal(api.calls[0].init.headers.Authorization, 'Bearer test-token');
});
