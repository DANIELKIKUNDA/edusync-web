// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('serialise le renouvellement et reprend une requête Chrome figée sans déconnecter', async () => {
  vi.resetModules();
  const native = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({detail: {code: 'STALE_REFRESH'}}), {
      status: 409, headers: {'X-EduSync-Session': 'STALE_REFRESH'},
    }))
    .mockResolvedValueOnce(new Response(JSON.stringify({access_token: 'access-after-wake', scope: 'SCHOOL'}), {
      status: 200, headers: {'Content-Type': 'application/json'},
    }));
  vi.stubGlobal('fetch', native);
  const lock = vi.fn(async (_name: string, callback: () => Promise<Response>) => callback());
  Object.defineProperty(navigator, 'locks', {configurable: true, value: {request: lock}});

  const {refreshAccessSession} = await import('../src/platform/connectivity');
  const response = await refreshAccessSession();

  expect(response.status).toBe(200);
  expect((await response.json()).access_token).toBe('access-after-wake');
  expect(lock).toHaveBeenCalledWith('edusync-session-refresh', expect.any(Function));
  expect(native).toHaveBeenCalledTimes(2);
  expect(native.mock.calls.every(([, init]) => (init as RequestInit).credentials === 'include')).toBe(true);
});
