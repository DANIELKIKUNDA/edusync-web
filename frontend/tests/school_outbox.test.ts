// @vitest-environment jsdom
// Owner decision 2026-10-25: in a school, enrollment, re-enrollment and payments do not depend on the network — they are
// kept on the device with their Idempotency-Key and replayed in order when the network returns; a server refusal is
// kept « à vérifier », never dropped; no token is stored on the device.
import 'fake-indexeddb/auto';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';

const school = {school: {id: 'sch-1', code: 'EXC', name: 'École Excellence'}, user: {id: 'u-1', email: 'caisse@example.test', full_name: 'Caissière'}, permissions: ['finance.checkout.collect']};
const network = vi.fn();
let token = 'live-token';
async function setup() {
  vi.resetModules();
  const session = await import('../src/platform/offline_session');
  session.rememberSchoolContext(school as any);
  session.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');                       // no network
  const outbox = await import('../src/offline/outbox');
  outbox.configureOutbox(`sch-1:u-1:${Math.random()}`, () => token);
  const {resilientFetch} = await import('../src/platform/connectivity');
  return {session, outbox, resilientFetch};
}
beforeEach(() => { localStorage.clear(); sessionStorage.clear(); network.mockReset().mockRejectedValue(new TypeError('network')); vi.stubGlobal('fetch', network); });
afterEach(async () => { (await import('../src/platform/offline_session')).clearPlatformContext(); vi.unstubAllGlobals(); });

it('offline: a payment and an enrollment are kept on the device with their key, the caller is told « queued »', async () => {
  const {outbox, resilientFetch} = await setup();
  const pay = await resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', headers: {'Idempotency-Key': 'pay-1', Authorization: 'Bearer live-token'}, body: JSON.stringify({enrollment_id: 'e1', charge_ids: ['c1'], amount: '15000', currency: 'CDF'})});
  expect(pay.status).toBe(202); expect((await pay.json()).offline_queued).toBe(true);
  await resilientFetch('/api/v1/schooling/enrollments/family', {method: 'POST', headers: {'Idempotency-Key': 'enr-1'}, body: JSON.stringify({children: [{last_name: 'KALALA', first_name: 'Joseph'}]})});
  const rows = await outbox.listOutbox();
  expect(rows.map(r => [r.kind, r.idempotencyKey])).toEqual([['PAYMENT', 'pay-1'], ['ENROLLMENT', 'enr-1']]);
  expect(rows[1].label).toContain('KALALA');
  expect(JSON.stringify(rows)).not.toMatch(/Bearer|live-token/);                      // never a token on the device
  // the same key twice = the same operation, stored once
  await resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', headers: {'Idempotency-Key': 'pay-1'}, body: '{}'});
  expect((await outbox.listOutbox()).length).toBe(2);
  expect(network).not.toHaveBeenCalled();
});

it('back online: replayed in order with the SAME key; a server refusal is kept « à vérifier » with its reason', async () => {
  const {session, outbox, resilientFetch} = await setup();
  await resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', headers: {'Idempotency-Key': 'pay-A'}, body: JSON.stringify({amount: '15000', currency: 'CDF'})});
  await resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', headers: {'Idempotency-Key': 'pay-B'}, body: JSON.stringify({amount: '15000', currency: 'CDF'})});
  session.setPlatformAuthState('AUTHENTICATED' as any);
  const seen: string[] = [];
  network.mockReset().mockImplementation(async (_url: string, init: RequestInit) => {
    const h = new Headers(init.headers); seen.push(h.get('Idempotency-Key')!);
    expect(h.get('Authorization')).toBe('Bearer live-token');                          // token read at replay time only
    return h.get('Idempotency-Key') === 'pay-A'
      ? new Response(JSON.stringify({receipt_number: 'REC-1'}), {status: 201, headers: {'Content-Type': 'application/json'}})
      : new Response(JSON.stringify({detail: 'Déjà soldé'}), {status: 409, headers: {'Content-Type': 'application/json'}});
  });
  await outbox.syncOutbox();
  expect(seen).toEqual(['pay-A', 'pay-B']);
  const rows = await outbox.listOutbox();
  expect(rows).toHaveLength(1); expect(rows[0]).toMatchObject({idempotencyKey: 'pay-B', status: 'CONFLICT', lastError: 'Déjà soldé'});
});

it('still no network during the replay: nothing is lost and the order is kept for the next try', async () => {
  const {session, outbox, resilientFetch} = await setup();
  await resilientFetch('/api/v1/finance/cash/expenses', {method: 'POST', headers: {'Idempotency-Key': 'exp-1'}, body: JSON.stringify({amount: '1000', currency: 'CDF'})});
  session.setPlatformAuthState('AUTHENTICATED' as any);
  await outbox.syncOutbox();                                                           // fetch rejects (network)
  expect((await outbox.listOutbox()).map(r => [r.idempotencyKey, r.status])).toEqual([['exp-1', 'PENDING']]);
});

it('offline cash desk: search and balance come from the offline pack, a local payment updates it at once', async () => {
  const {outbox, resilientFetch} = await setup();
  await outbox.savePack({generatedAt: new Date().toISOString(), people: [{student_id: 's1', enrollment_id: 'e1', matricule: 'ELV-1', last_name: 'KALALA', first_name: 'Joseph', class_label: '1re A'}],
    balances: {e1: [{id: 'sep', remaining: '15000.00', paid_amount: '0.00', eligible: true, requires: []}, {id: 'oct', remaining: '15000.00', paid_amount: '0.00', eligible: false, lock_reason: 'Septembre doit être soldé d’abord', requires: ['sep']}]}});
  expect((await (await resilientFetch('/api/v1/finance/checkout/search?q=kala')).json()).items[0].matricule).toBe('ELV-1');
  await resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', headers: {'Idempotency-Key': 'pay-sep'}, body: JSON.stringify({enrollment_id: 'e1', charge_ids: ['sep'], amount: '15000', currency: 'CDF'})});
  const items = (await (await resilientFetch('/api/v1/finance/checkout/balance/00000000-0000-0000-0000-000000000000')).json()).items;
  expect(items).toEqual([]);                                                           // unknown enrollment: nothing
  const pack = await outbox.loadPack();
  expect(pack!.balances.e1.map((c: any) => [c.id, c.eligible])).toEqual([['oct', true]]);   // September paid here, October now payable
});

it('the platform stays read-only offline (only the school works without network)', async () => {
  vi.resetModules();
  const session = await import('../src/platform/offline_session');
  session.rememberPlatformContext({user: {id: 'p', email: 'o@example.test', full_name: 'O'}, roles: [], permissions: [], menu: []} as any);
  session.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
  const {resilientFetch} = await import('../src/platform/connectivity');
  await expect(resilientFetch('/api/v1/finance/checkout/collect', {method: 'POST', body: '{}'})).rejects.toMatchObject({code: 'OFFLINE_READ_ONLY'});
});
