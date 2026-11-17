import assert from 'node:assert/strict';
import {once} from 'node:events';
import {test} from 'node:test';
import {createPrintServer} from './server.mjs';

const origin = 'https://staging.myeducsync.com';
const key = 'ab'.repeat(32);

test('autorise uniquement le poste appairé et confirme seulement la soumission', async t => {
  const received = [];
  let unblock;
  let entered;
  const printing = new Promise(resolve => { entered = resolve; });
  const server = createPrintServer({origin, key, printer: 'Ticket 80', print: async pdf => {
    received.push(pdf.toString());
    const hold = new Promise(resolve => { unblock = resolve; });
    entered();
    await hold;
  }});
  server.listen(47319, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => { unblock?.(); server.closeAllConnections(); server.close(); });
  const base = 'http://127.0.0.1:47319/v1';
  const headers = {Origin: origin, Authorization: `Bearer ${key}`};
  const post = (body, extra = {}) => fetch(base + '/print', {
    method: 'POST', headers: {...headers, 'Content-Type': 'application/pdf', ...extra}, body,
  });
  assert.equal((await post('%PDF-denied', {Origin: 'https://elsewhere.example'})).status, 403);
  assert.equal((await post('%PDF-denied', {Authorization: 'Bearer invalid'})).status, 401);
  assert.equal((await post('invalid format')).status, 400);
  assert.deepEqual(received, []);
  const options = await fetch(base + '/print', {method: 'OPTIONS', headers: {Origin: origin}});
  assert.equal(options.status, 204);
  assert.equal(options.headers.get('access-control-allow-origin'), origin);
  assert.deepEqual(await (await fetch(base + '/status', {headers})).json(), {status: 'ready', printer: 'Ticket 80'});
  const first = post('%PDF-valid');
  await printing;
  assert.equal((await post('%PDF-second')).status, 409);
  unblock();
  assert.deepEqual(await (await first).json(), {status: 'submitted', printer: 'Ticket 80'});
  assert.deepEqual(received, ['%PDF-valid']);
});
