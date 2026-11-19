// @vitest-environment jsdom
// Owner, 2026-11-15: « En ligne » shown next to « Hors connexion — vous pouvez continuer ». A session reopened from the
// device (first check timed out) must be checked again while the browser is online, even if the network never dropped.
import {afterEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('une session rouverte depuis l’appareil est revérifiée tant que le navigateur est en ligne', async () => {
  vi.resetModules();
  const s = await import('../src/platform/offline_session');
  s.rememberSchoolContext({token: 'tok', school: {id: 's1', name: 'École', code: 'EDS-1'}, user: {id: 'u1', email: 'a@b.c', full_name: 'A'}, permissions: []} as never);
  expect(s.getPlatformAuthState()).toBe('ONLINE_AUTHENTICATED');
  expect(s.shouldRetryCachedSession()).toBe(false);          // validée en ligne : rien à refaire

  s.setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');      // ouverture : vérification expirée → session de l'appareil
  Object.defineProperty(navigator, 'onLine', {configurable: true, get: () => true});
  expect(s.shouldRetryCachedSession()).toBe(true);             // en ligne : on revérifie

  Object.defineProperty(navigator, 'onLine', {configurable: true, get: () => false});
  expect(s.shouldRetryCachedSession()).toBe(false);            // vraiment hors ligne : on attend le réseau
  expect(s.CACHED_SESSION_RETRY_MS).toBe(20_000);
});

it('App relance la vérification périodiquement et au retour d’une réponse du serveur', () => {
  const app = readFileSync('src/App.tsx', 'utf8');
  expect(app).toContain("window.setInterval(()=>{if(shouldRetryCachedSession()||(knownContext()&&navigator.onLine!==false&&getSessionCheckState()==='interrupted'))void restore()},CACHED_SESSION_RETRY_MS)");
  expect(app).toContain("s==='ONLINE'&&(lastNet!=='ONLINE'||shouldRetryCachedSession())");
  expect(app).toContain('window.clearInterval(retry)');
});
