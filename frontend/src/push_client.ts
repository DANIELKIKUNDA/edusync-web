// Push on this device (PUSH_FCM_INTEGRATION.md). Firebase Messaging is loaded on demand, only after an explicit
// "Activer les notifications" action: the browser permission prompt is never shown at page load. The registration
// token is obtained with the existing EduSync service worker (/sw.js) — no second service worker — and sent once to
// the server, which stores it encrypted. The token is never kept in localStorage or shown on screen.
import {pushConfig, pushRevoke, pushSubscribe, type PushConfig} from './messaging_api';
import {UserFacingError} from './platform/errors';

export const PUSH_ACTIVATION_MESSAGE = 'Impossible d’activer les notifications sur cet appareil. Vérifiez votre connexion ou les autorisations de notification, puis réessayez.';

const LOCAL_KEY = 'edusync.push.subscription';     // only the server-side subscription id, never the token

export type PushSupport = {supported: boolean; permission: NotificationPermission | 'unsupported'; reason?: string};

export function pushSupport(): PushSupport {
  if (!('serviceWorker' in navigator) || !('Notification' in window) || !('PushManager' in window)) {
    return {supported: false, permission: 'unsupported', reason: 'Ce navigateur ne gère pas les notifications web (sur iPhone : ajoutez d’abord EduSync à l’écran d’accueil).'};
  }
  return {supported: true, permission: Notification.permission};
}

function deviceLabel(): {label: string; platform: string; browser: string} {
  const ua = navigator.userAgent;
  const platform = /Android/i.test(ua) ? 'android' : /iPhone|iPad/i.test(ua) ? 'ios' : /Windows/i.test(ua) ? 'windows' : /Mac/i.test(ua) ? 'macos' : 'other';
  const browser = /Edg\//.test(ua) ? 'edge' : /Chrome\//.test(ua) ? 'chrome' : /Firefox\//.test(ua) ? 'firefox' : /Safari\//.test(ua) ? 'safari' : 'other';
  return {label: `${browser} · ${platform}`, platform, browser};
}

function remember(scope: string, id: string | null) {
  try { if (id) localStorage.setItem(`${LOCAL_KEY}:${scope}`, id); else localStorage.removeItem(`${LOCAL_KEY}:${scope}`); } catch { /* private mode */ }
}
export function rememberedSubscription(scope: string): string | null {
  try { return localStorage.getItem(`${LOCAL_KEY}:${scope}`); } catch { return null; }
}

async function fcmToken(cfg: PushConfig): Promise<string> {
  if (!cfg.web_config || !cfg.vapid_public_key) throw new Error('Notifications : configuration Firebase incomplète sur la plateforme');
  const [{initializeApp, getApps}, {getMessaging, getToken, isSupported}] = await Promise.all([import('@firebase/app'), import('@firebase/messaging')]);
  if (!(await isSupported())) throw new Error('Ce navigateur ne permet pas les notifications Firebase');
  const app = getApps()[0] ?? initializeApp(cfg.web_config);
  const registration = await navigator.serviceWorker.ready;           // the existing EduSync service worker
  const token = await getToken(getMessaging(app), {vapidKey: cfg.vapid_public_key, serviceWorkerRegistration: registration});
  if (!token) throw new Error('Jeton de notification indisponible');
  return token;
}

/** Explicit user action: permission prompt, token, registration on the server. `scope` = school id or "platform". */
export async function enablePush(token: string, scope: string, platform = false): Promise<{id: string; simulated: boolean}> {
  let stage = 'support';
  try {
  const support = pushSupport();
  if (!support.supported) throw new Error(support.reason);
  stage = 'configuration';
  const cfg = await pushConfig(token, platform);
  if (cfg.provider === 'disabled') throw new Error('Les notifications push ne sont pas activées sur la plateforme');
  stage = 'permission';
  const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Autorisation refusée : réactivez les notifications dans les réglages du navigateur');
  // Development only: the server refuses the fake provider in staging / production.
  stage = 'firebase-token';
  const deviceToken = cfg.provider === 'fake' ? `fcm-dev-${crypto.randomUUID()}${crypto.randomUUID()}` : await fcmToken(cfg);
  const d = deviceLabel();
  stage = 'device-registration';
  const sub = await pushSubscribe(token, {provider: 'FCM', endpoint: deviceToken, device_label: d.label, platform: d.platform, browser: d.browser}, platform);
  remember(scope, sub.id);
  return {id: sub.id, simulated: cfg.provider === 'fake'};
  } catch {
    // Never log Firebase errors: they may contain request URLs, keys or tokens.
    console.warn('[EduSync] PUSH_ACTIVATION_FAILED', {stage});
    throw new UserFacingError(PUSH_ACTIVATION_MESSAGE, 'PUSH_ACTIVATION_FAILED');
  }
}

/** Stops push on this device only (other devices of the account keep receiving). Also called at sign-out. */
export async function disablePush(token: string, scope: string, platform = false): Promise<void> {
  const id = rememberedSubscription(scope);
  // Keep the identifier until the server confirms revocation. A network error
  // must not make the UI claim that a still-active device has been removed.
  if (id) await pushRevoke(token, id, platform);
  remember(scope, null);
  try {
    const cfg = await pushConfig(token, platform);
    if (cfg.provider === 'fcm' && cfg.web_config) {
      const [{getApps}, {getMessaging, deleteToken}] = await Promise.all([import('@firebase/app'), import('@firebase/messaging')]);
      const app = getApps()[0];
      if (app) await deleteToken(getMessaging(app)).catch(() => undefined);
    }
  } catch { /* best effort: the server-side revocation already happened */ }
}
