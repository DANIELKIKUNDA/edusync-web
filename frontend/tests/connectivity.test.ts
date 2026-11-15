// @vitest-environment jsdom
import {expect, it, vi} from 'vitest';

it('leaves Firebase fetch options unchanged and never performs an EduSync refresh', async () => {
  const native = vi.fn(async () => new Response('{}', {status: 401}));
  vi.stubGlobal('fetch', native);
  const {resilientFetch, isEduSyncApi} = await import('../src/platform/connectivity');
  const url = 'https://firebaseinstallations.googleapis.com/v1/projects/example/installations';
  const init = {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'};
  const response = await resilientFetch(url, init);
  expect(response.status).toBe(401);
  expect(native).toHaveBeenCalledExactlyOnceWith(url, init);
  expect(isEduSyncApi('/api/v1/platform/me')).toBe(true);
  expect(isEduSyncApi('https://unrelated.example/api/v1/test')).toBe(false);
  vi.unstubAllGlobals();
});

// 2026-11-01 (owner: « pas un système qui détecte en une seconde l’absence de connexion ») — the browser's offline signal
// only starts a check; « Hors ligne » comes after several failed probes spread over the grace period, and the way back needs
// several answers in a row.
it('a one-second network drop never switches the app offline; a real loss does, after verification', async () => {
  vi.resetModules(); vi.useFakeTimers();
  let up = false;
  const health = vi.fn(async () => { if (!up) throw new TypeError('Failed to fetch'); return new Response(JSON.stringify({status: 'ok'}), {status: 200, headers: {'Content-Type': 'application/json'}}); });
  vi.stubGlobal('fetch', health);
  const c = await import('../src/platform/connectivity');
  c.installResilientFetch();
  window.dispatchEvent(new Event('offline'));
  await vi.advanceTimersByTimeAsync(1_000);
  expect(c.getConnectivity().state).not.toBe('OFFLINE');           // a drop of a second: still checking
  up = true; window.dispatchEvent(new Event('online'));
  await vi.advanceTimersByTimeAsync(100);
  expect(c.getConnectivity().state).toBe('ONLINE');                // the network came back before the verdict
  up = false; window.dispatchEvent(new Event('offline'));
  await vi.advanceTimersByTimeAsync(c.OFFLINE_GRACE_MS - 2_000);
  expect(c.getConnectivity().state).not.toBe('OFFLINE');           // still within the grace period
  await vi.advanceTimersByTimeAsync(6_000);
  expect(c.getConnectivity().state).toBe('OFFLINE');               // confirmed after several failed probes
  up = true; window.dispatchEvent(new Event('online'));
  await vi.advanceTimersByTimeAsync(100);
  // Native `online` plus one successful server health check restores the UI without waiting for a frozen old probe.
  expect(c.getConnectivity().state).toBe('ONLINE');
  vi.useRealTimers(); vi.unstubAllGlobals();
});

it('keeps display-only credentials off the network while the session is restored', async () => {
  vi.resetModules();
  const native = vi.fn(async () => new Response('{}'));
  vi.stubGlobal('fetch', native);
  try {
    const {resilientFetch} = await import('../src/platform/connectivity');
    const {OFFLINE_SCHOOL_TOKEN} = await import('../src/platform/offline_session');
    const headers = {Authorization: `Bearer ${OFFLINE_SCHOOL_TOKEN}`};
    const personnel = new URL('/api/v1/staff', window.location.origin);
    await expect(resilientFetch(personnel, {headers})).rejects.toThrow('restauration de votre session');
    await expect(resilientFetch(new Request(personnel, {method: 'POST', headers}))).rejects.toThrow('session restaurée');
    expect(native).not.toHaveBeenCalled();
    expect((await resilientFetch(personnel, {headers: {Authorization: 'Bearer active-token'}})).ok).toBe(true);
    expect(native).toHaveBeenCalledTimes(1);
  } finally {
    vi.unstubAllGlobals();
  }
});

it('accepts a slow health response and distinguishes an HTTP service outage from a disconnect', async () => {
  vi.resetModules();
  vi.useFakeTimers();
  const healthResponse = () => new Response('{"status":"ok"}', {headers: {'Content-Type': 'application/json'}});
  const native = vi.fn((_input: unknown, init: RequestInit) => new Promise<Response>((resolve, reject) => {
    const timer = setTimeout(() => resolve(healthResponse()), 8_500);
    init.signal?.addEventListener('abort', () => {clearTimeout(timer); reject(init.signal?.reason);});
  }));
  vi.stubGlobal('fetch', native);
  try {
    const c = await import('../src/platform/connectivity');
    c.installResilientFetch();
    await vi.advanceTimersByTimeAsync(13_600);
    expect(c.getConnectivity().state).toBe('ONLINE');
    expect(c.getConnectivity().lastSuccess).toBeGreaterThan(c.getConnectivity().since);
    native.mockImplementation(async () => new Response('', {status: 503}));
    await vi.advanceTimersByTimeAsync(45_000);
    expect(c.getConnectivity().state).toBe('DEGRADED');
  } finally {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  }
});
