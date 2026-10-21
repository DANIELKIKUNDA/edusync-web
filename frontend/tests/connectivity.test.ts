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
