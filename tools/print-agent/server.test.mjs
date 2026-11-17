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
  const headers = {Connection: 'close', Origin: origin, Authorization: `Bearer ${key}`};
  const post = (body, extra = {}) => fetch(base + '/print', {
    method: 'POST', headers: {...headers, 'Content-Type': 'application/pdf', ...extra}, body,
  });
  assert.equal((await post('%PDF-denied', {Origin: 'https://elsewhere.example'})).status, 403);
  assert.equal((await post('%PDF-denied', {Authorization: 'Bearer invalid'})).status, 401);
  assert.equal((await post('invalid format')).status, 400);
  assert.deepEqual(received, []);
  const options = await fetch(base + '/print', {method: 'OPTIONS', headers: {Connection: 'close', Origin: origin}});
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

test('demande une validation locale avant de transmettre la clé', async t => {
  let finishApproval;
  let promptStarted;
  const started = new Promise(resolve => { promptStarted = resolve; });
  const server = createPrintServer({origin, key, printer: 'XP-80C', print: async () => {
    assert.fail('Une association ne doit jamais imprimer');
  }, approvePairing: () => new Promise(resolve => {
    finishApproval = resolve;
    promptStarted();
  })});
  server.listen(47319, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => { finishApproval?.(false); server.closeAllConnections(); server.close(); });

  const url = 'http://127.0.0.1:47319/v1/pair';
  const pair = (headers = {}) => fetch(url, {
    method: 'POST', headers: {Connection: 'close', Origin: origin, 'Content-Type': 'application/json', ...headers},
  });
  assert.equal((await pair({Origin: 'https://autre.example'})).status, 403);
  assert.equal((await pair({'Content-Type': 'text/plain'})).status, 400);
  const preflight = await fetch(url, {method: 'OPTIONS', headers: {Connection: 'close', Origin: origin}});
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get('access-control-allow-origin'), origin);
  const pending = pair();
  await started;
  assert.equal((await pair()).status, 429);
  finishApproval(true);
  const approved = await pending;
  assert.deepEqual(await approved.json(), {status: 'paired', printer: 'XP-80C', key});
  assert.equal((await pair()).status, 429);
});

test('refuser la demande ne révèle aucune clé', async t => {
  const server = createPrintServer({origin, key, printer: 'XP-80C', print: async () => {},
    approvePairing: async () => false});
  server.listen(47319, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => {server.closeAllConnections(); server.close();});
  const response = await fetch('http://127.0.0.1:47319/v1/pair', {
    method: 'POST', headers: {Connection: 'close', Origin: origin, 'Content-Type': 'application/json'},
  });
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), {status: 'pairing_denied'});
});
