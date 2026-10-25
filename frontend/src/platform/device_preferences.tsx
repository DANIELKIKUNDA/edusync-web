import React, {useEffect, useState} from 'react';
import {pushConfig, pushDevices} from '../messaging_api';
import {disablePush, enablePush, pushSupport, rememberedSubscription} from '../push_client';
import {friendlyError} from './errors';

type Props = {token: string; scope: string; platform: boolean};

/** Only the push subscription for this browser. In-app notifications and essential e-mails are unaffected. */
export function DeviceNotificationPreference({token, scope, platform}: Props) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const support = pushSupport();

  async function load() {
    const [config, devices] = await Promise.all([pushConfig(token, platform), pushDevices(token, platform)]);
    setAvailable(config.provider !== 'disabled');
    const id = rememberedSubscription(scope);
    setActive(Boolean(id && devices.items.some(device => device.id === id)));
  }
  useEffect(() => {
    let mounted = true;
    Promise.all([pushConfig(token, platform), pushDevices(token, platform)])
      .then(([config, devices]) => {
        if (!mounted) return;
        setAvailable(config.provider !== 'disabled');
        const id = rememberedSubscription(scope);
        setActive(Boolean(id && devices.items.some(device => device.id === id)));
      })
      .catch(e => { if (mounted) { setAvailable(null); setError(friendlyError(e)); } });
    return () => { mounted = false; };
  }, [token, scope, platform]);

  async function toggle() {
    setBusy(true); setError('');
    try {
      if (active) await disablePush(token, scope, platform);
      else await enablePush(token, scope, platform);
      await load();
    } catch (e) { setError(friendlyError(e)); }
    finally { setBusy(false); }
  }

  return <fieldset className="es-pref-group">
    <legend>Notifications sur cet appareil</legend>
    <p className="es-hint">Recevoir les alertes EduSync même quand l’application est fermée. Les notifications dans EduSync et les e-mails essentiels restent disponibles.</p>
    {available === null && !error && <p role="status">Vérification des notifications…</p>}
    {available === false && <p className="es-hint">Les notifications push ne sont pas configurées sur ce serveur.</p>}
    {!support.supported && <p className="es-hint">{support.reason}</p>}
    {support.permission === 'denied' && <p className="es-hint">Autorisation refusée. Réactivez les notifications dans les réglages du navigateur.</p>}
    {(available || active) && (support.supported || active) && <button type="button" className="es-btn" disabled={busy || (!active && support.permission === 'denied')}
      onClick={() => void toggle()}>{busy ? 'Mise à jour…' : active ? 'Désactiver sur cet appareil' : 'Activer sur cet appareil'}</button>}
    {active && <p className="es-hint" role="status">Notifications activées sur cet appareil.</p>}
    {error && <div className="es-alert es-alert-bad" role="alert">{error} <button type="button" className="es-btn es-btn-ghost" onClick={() => { setError(''); void load().catch(e => setError(friendlyError(e))); }}>Réessayer</button></div>}
  </fieldset>;
}
