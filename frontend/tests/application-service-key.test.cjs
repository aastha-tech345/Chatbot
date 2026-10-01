const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function api(base = 'https://api.example.test') {
  const calls = [];
  const module = { exports: {} };
  const source = fs.readFileSync('lib/api/applications.ts', 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(js, { module, exports: module.exports, URL, URLSearchParams,
    window: { location: { origin: 'https://admin.example.test' } },
    require: () => ({ API_BASE_URL: base, adminRequest: async (path, init) => {
      calls.push({ path, init });
      return { id: 'example', auth_type: 'service_key', service_key_configured: true };
    } }),
  });
  return { ...module.exports, calls };
}

test('create sends secret only in body and maps safe metadata', async () => {
  const client = api();
  const result = await client.createApplication({ name: 'Example', serviceKey: 'synthetic-key', authType: 'service_key' });
  assert.equal(JSON.parse(client.calls[0].init.body).service_key, 'synthetic-key');
  assert.equal(client.calls[0].path, '/applications');
  assert.equal(result.serviceKeyConfigured, true);
  assert.equal(result.serviceKey, undefined);
});
test('blank edits omit the secret and rotations send it', async () => {
  const client = api();
  await client.updateApplication('example', { serviceKey: '' });
  assert.equal('service_key' in JSON.parse(client.calls[0].init.body), false);
  await client.updateApplication('example', { serviceKey: 'replacement' });
  assert.equal(JSON.parse(client.calls[1].init.body).service_key, 'replacement');
});
test('insecure transport rejects secret before making a request', async () => {
  const client = api('http://localhost:9000');
  await assert.rejects(client.createApplication({ serviceKey: 'synthetic-key' }), /HTTPS/);
  await assert.rejects(client.updateApplication('example', { serviceKey: 'synthetic-key' }), /HTTPS/);
  assert.equal(client.calls.length, 0);
});
