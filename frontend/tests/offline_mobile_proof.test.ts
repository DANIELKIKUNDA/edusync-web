// @vitest-environment jsdom
// Offline proof on a phone (2026-10-31): defects found against the real server, kept fixed here.
import 'fake-indexeddb/auto';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';

const school = {school: {id: 'sch-1', code: 'EXC', name: 'École Excellence'}, user: {id: 'u-1', email: 'caisse@example.test', full_name: 'Caissière'}, permissions: ['finance.checkout.collect']};
const E = '11111111-1111-1111-1111-111111111111';
async function setup() {
  vi.resetModules();
  const session = await import('../src/platform/offline_session');
  session.rememberSchoolContext(school as any); session.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
  const outbox = await import('../src/offline/outbox');
  outbox.configureOutbox(`sch-1:u-1:${Math.random()}`, () => 'token');
  const {resilientFetch} = await import('../src/platform/connectivity');
  return {outbox, resilientFetch};
}
beforeEach(() => { localStorage.clear(); vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network'))); });
afterEach(async () => { (await import('../src/platform/offline_session')).clearPlatformContext(); vi.unstubAllGlobals(); });

it('« Action conseillée » offline: the oldest payable charge of the device copy, as the server orders it', async () => {
  const {outbox, resilientFetch} = await setup();
  await outbox.savePack({generatedAt: 'now', people: [], balances: {[E]: [
    {id: 'c-locked', label: 'Octobre', currency: 'CDF', remaining: '15000.00', eligible: false},
    {id: 'c-first', label: 'Frais de l’État — 1re tranche', currency: 'CDF', remaining: '12000.00', eligible: true},
    {id: 'c-next', label: 'Septembre', currency: 'CDF', remaining: '15000.00', eligible: true}]}});
  const r = await (await resilientFetch(`/api/v1/finance/checkout/recommended/${E}`)).json();
  expect(r).toMatchObject({ready: true, label: 'Frais de l’État — 1re tranche', total: '12000.00', allocations: [{charge_id: 'c-first', amount: '12000.00'}]});
  const none = await (await resilientFetch('/api/v1/finance/checkout/recommended/22222222-2222-2222-2222-222222222222')).json();
  expect(none.ready).toBe(false);
});

it('the pending payment reads FC on the device, never the internal code CDF', async () => {
  const {outbox, resilientFetch} = await setup();
  await resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', headers: {'Idempotency-Key': 'k-1', 'Content-Type': 'application/json'},
    body: JSON.stringify({enrollment_id: E, charge_ids: ['c-first'], amount: '1000', currency: 'CDF'})});
  const [row] = await outbox.listOutbox();
  expect(row.label).toBe('Encaissement · 1000 FC');
});

// 2026-10-31 (owner: « au niveau école tout le monde peut travailler offline »)
it('every role: a staff record edit is kept with its version (If-Match) and replayed with it', async () => {
  const {outbox, resilientFetch} = await setup();
  const S = '33333333-3333-3333-3333-333333333333';
  const r = await resilientFetch(`/api/v1/personnel/${S}`, {method: 'PUT', headers: {'Idempotency-Key': 'k-staff', 'If-Match': '7', 'Content-Type': 'application/json'}, body: JSON.stringify({employee_no: 'A1', last_name: 'KABEYA', category: 'AUTRE'})});
  expect(r.status).toBe(202);
  const [row] = await outbox.listOutbox();
  expect(row).toMatchObject({label: 'Fiche agent', ifMatch: '7', idempotencyKey: 'k-staff'});
  const sent: any[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_u: string, init: RequestInit) => { sent.push(Object.fromEntries(new Headers(init.headers).entries())); return new Response('{}', {status: 200}); }));
  Object.defineProperty(navigator, 'onLine', {configurable: true, get: () => true});
  await outbox.syncOutbox();
  expect(sent[0]).toMatchObject({'if-match': '7', 'idempotency-key': 'k-staff', 'x-edusync-replay': 'outbox'});
  expect(await outbox.listOutbox()).toHaveLength(0);
});

it('an operation without Idempotency-Key is never kept (it could not be replayed safely)', async () => {
  const {outbox, resilientFetch} = await setup();
  await expect(resilientFetch('/api/v1/stewardship/stock/movements', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})).rejects.toThrow(/demande le réseau/);
  expect(await outbox.listOutbox()).toHaveLength(0);
});

it('accounts and access stay online, with a message that says so', async () => {
  const {outbox, resilientFetch} = await setup();
  await expect(resilientFetch('/api/v1/access/members', {method: 'POST', headers: {'Idempotency-Key': 'k-m', 'Content-Type': 'application/json'}, body: '{}'})).rejects.toThrow(/comptes et accès/);
  expect(await outbox.listOutbox()).toHaveLength(0);
});
