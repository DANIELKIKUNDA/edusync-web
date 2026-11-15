// @vitest-environment jsdom
// Owner, 2026-11-15: « Hors connexion » while online, cleared only by signing out. A background renewal that never answered
// held the shared lock forever; every later session check queued behind it. Both halves of the fix are proven here.
import {afterEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

/** Minimal Web Locks: exclusive, FIFO, honours {signal} while waiting (as the browser does). */
function fakeLocks() {
  let tail: Promise<unknown> = Promise.resolve();
  return {request: (_name: string, a: unknown, b?: () => Promise<unknown>) => {
    const opts = (typeof a === 'function' ? {} : a) as {signal?: AbortSignal};
    const cb = (typeof a === 'function' ? a : b) as () => Promise<unknown>;
    const previous = tail;
    let release!: () => void; tail = new Promise<void>(r => { release = r; });
    return new Promise((resolve, reject) => {
      opts.signal?.addEventListener('abort', () => reject(new DOMException('abandon', 'AbortError')), {once: true});
      previous.then(() => cb().then(resolve, reject).finally(release));
    });
  }};
}

it('un renouvellement qui ne répond jamais est abandonné et libère le verrou', async () => {
  vi.useFakeTimers(); vi.resetModules();
  const hang = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_r, reject) =>
    init.signal?.addEventListener('abort', () => reject(new DOMException('délai', 'AbortError')))));
  vi.stubGlobal('fetch', hang);
  Object.defineProperty(navigator, 'locks', {configurable: true, value: fakeLocks()});
  const c = await import('../src/platform/connectivity');
  const stuck = c.refreshAccessSession().catch(e => e.name);            // renouvellement de fond, sans délai fourni
  await vi.advanceTimersByTimeAsync(c.REFRESH_TIMEOUT_MS + 10);
  expect(await stuck).toBe('AbortError');                                 // il a sa propre limite de temps

  hang.mockImplementation(async () => new Response(JSON.stringify({access_token: 't'}), {status: 200}));
  const next = await c.refreshAccessSession();                            // le verrou est libre : la suivante passe
  expect(next.status).toBe(200);
});

it('une vérification qui abandonne ne reste jamais en file derrière un verrou bloqué', async () => {
  vi.resetModules();
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));   // ne répond jamais, n'écoute pas l'abandon
  Object.defineProperty(navigator, 'locks', {configurable: true, value: fakeLocks()});
  const c = await import('../src/platform/connectivity');
  void c.refreshAccessSession().catch(() => {});                          // garde le verrou
  const ctl = new AbortController();
  const check = c.refreshAccessSession(ctl.signal).catch(e => e.name);
  ctl.abort();
  expect(await check).toBe('AbortError');                                 // rendue tout de suite, pas d'attente infinie
});

it('réseau présent : le bandeau dit « Vérification de votre session… » après un délai', () => {
  const spaces = readFileSync('src/platform/spaces.tsx', 'utf8');
  const app = readFileSync('src/App.tsx', 'utf8');
  expect(spaces).toContain('Vérification de votre session…');
  expect(spaces.indexOf('if(reachable){')).toBeLessThan(spaces.indexOf('Hors connexion — vous pouvez continuer'));
  expect(app).toContain("window.addEventListener('edusync:session-retry',retryNow)");
});

it('le renouvellement de fond abandonne aussi l’attente du verrou', async () => {
  vi.useFakeTimers(); vi.resetModules();
  vi.stubGlobal('fetch', vi.fn());
  const locks = {request: (_name: string, {signal}: LockOptions) => new Promise((_resolve, reject) => {
    signal?.addEventListener('abort', () => reject(new DOMException('délai', 'AbortError')));
  })};
  Object.defineProperty(navigator, 'locks', {configurable: true, value: locks});
  const c = await import('../src/platform/connectivity');
  const pending = c.refreshAccessSession().catch(e => e.name);
  await vi.advanceTimersByTimeAsync(c.REFRESH_TIMEOUT_MS);
  expect(await pending).toBe('AbortError');
  expect(fetch).not.toHaveBeenCalled();
});

it('attend avant le bandeau et propose de réessayer seulement après une interruption', async () => {
  const {createElement} = await import('react');
  const {act, cleanup, fireEvent, render, screen} = await import('@testing-library/react/pure');
  const session = await import('../src/platform/offline_session');
  const {OfflineAdminBanner} = await import('../src/platform/spaces');
  vi.useFakeTimers();
  const retry = vi.fn();
  window.addEventListener('edusync:session-retry', retry);
  try {
    session.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');
    session.setSessionCheckState('checking');
    render(createElement(OfflineAdminBanner, {school: true}));
    expect(screen.queryByRole('status')).toBeNull();
    act(() => session.setSessionCheckState('idle'));
    act(() => vi.advanceTimersByTime(3_000));
    expect(screen.queryByRole('status')).toBeNull();
    act(() => session.setSessionCheckState('checking'));
    act(() => vi.advanceTimersByTime(3_000));
    expect(screen.getByRole('status').textContent).toContain('Vérification de votre session…');
    expect(screen.queryByRole('button', {name: 'Réessayer'})).toBeNull();
    act(() => session.setSessionCheckState('interrupted'));
    fireEvent.click(screen.getByRole('button', {name: 'Réessayer'}));
    expect(retry).toHaveBeenCalledTimes(1);
  } finally {
    cleanup();
    window.removeEventListener('edusync:session-retry', retry);
    session.setSessionCheckState('idle');
    session.setPlatformAuthState('AUTH_REQUIRED');
  }
});
