// @vitest-environment jsdom
// Owner, 2026-11-15: « TikTok et YouTube marchent avec la même connexion, EduSync dit hors connexion ». Slow network
// (a TLS handshake alone took 8 s): the app opens at once on the device, and the SERVER comes first whenever it answers.
import 'fake-indexeddb/auto';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';

const school = {school: {id: 'sch-1', code: 'EXC', name: 'École'}, user: {id: 'u-1', email: 'a@b.c', full_name: 'A'}, permissions: []};
const network = vi.fn();
beforeEach(() => { localStorage.clear(); network.mockReset(); vi.stubGlobal('fetch', network);
  Object.defineProperty(navigator, 'onLine', {configurable: true, get: () => true}); });
afterEach(async () => { (await import('../src/platform/offline_session')).clearPlatformContext(); vi.unstubAllGlobals(); });

async function cachedSession() {
  vi.resetModules();
  const s = await import('../src/platform/offline_session');
  s.rememberSchoolContext(school as never);
  const url = new URL('/api/v1/schooling/students', location.origin);
  await s.rememberPlatformRead(url, new Response(JSON.stringify({items: ['copie de l’appareil']}), {headers: {'Content-Type': 'application/json'}}));
  s.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');            // vérification de session pas encore aboutie
  const c = await import('../src/platform/connectivity');
  return {s, c};
}

it('réseau présent (même lent) : le serveur d’abord, pas « non disponible hors connexion »', async () => {
  const {c} = await cachedSession();
  network.mockResolvedValue(new Response(JSON.stringify({items: ['donnée du serveur']}), {status: 200, headers: {'Content-Type': 'application/json'}}));
  const r = await c.resilientFetch('/api/v1/schooling/families');           // jamais consultée : avant, refusée sans réseau
  expect(network).toHaveBeenCalled();
  expect(await r.json()).toEqual({items: ['donnée du serveur']});
});

it('le serveur ne répond pas : la copie de l’appareil prend le relais', async () => {
  const {c} = await cachedSession();
  network.mockRejectedValue(new TypeError('network'));
  const r = await c.resilientFetch('/api/v1/schooling/students');
  expect(await r.json()).toEqual({items: ['copie de l’appareil']});
});

it('session encore en reprise (refus 401) : la lecture vient de l’appareil, pas une erreur', async () => {
  const {c} = await cachedSession();
  network.mockResolvedValue(new Response('{"detail":"Session à renouveler"}', {status: 401}));
  Object.defineProperty(navigator, 'locks', {configurable: true, value: undefined});
  const r = await c.resilientFetch('/api/v1/schooling/students');
  expect(await r.json()).toEqual({items: ['copie de l’appareil']});
});

it('vraie coupure (mode avion) : l’appareil seul, sans attendre le réseau', async () => {
  const {c} = await cachedSession();
  Object.defineProperty(navigator, 'onLine', {configurable: true, get: () => false});
  const r = await c.resilientFetch('/api/v1/schooling/students');
  expect(network).not.toHaveBeenCalled();
  expect(await r.json()).toEqual({items: ['copie de l’appareil']});
});

it('démarrage immédiat sur la session de l’appareil, vérification en arrière-plan (30 s pour un réseau lent)', async () => {
  const app = readFileSync('src/App.tsx', 'utf8');
  expect(app).toContain('if(first){first=false;if(knownContext()){applyCachedContext();if(alive)setRestoring(false)}}');
  expect(app).toContain('window.setTimeout(()=>ctl.abort(),SESSION_CHECK_MS)');
  const {SESSION_CHECK_MS} = await import('../src/platform/offline_session');
  const {REFRESH_TIMEOUT_MS} = await import('../src/platform/connectivity');
  expect(SESSION_CHECK_MS).toBe(30_000); expect(REFRESH_TIMEOUT_MS).toBe(30_000);
});
