import React, {useEffect, useState} from 'react';
import {systemHealth, type SystemHealth} from '../api';
import {friendlyError} from './errors';
import {NavGlyph} from './nav_icons';
import './health.css';

const STATE: Record<string, {label: string; cls: string; icon: string}> = {
  OK: {label: 'Opérationnel', cls: 'hl-ok', icon: 'checkCircle'},
  DEGRADED: {label: 'Dégradé', cls: 'hl-warn', icon: 'alert'},
  DOWN: {label: 'Hors service', cls: 'hl-bad', icon: 'alert'},
  NOT_CONFIGURED: {label: 'Non configuré', cls: 'hl-off', icon: 'info'},
};
const ICON: Record<string, string> = {api: 'cockpit', database: 'database', redis: 'layers', worker_outbox: 'sync', worker_communications: 'message', storage: 'folder', errors: 'alert', backup: 'cloudUp'};
const OVERALL: Record<string, string> = {OK: 'Tous les services fonctionnent normalement', DEGRADED: 'Service dégradé : certaines fonctions peuvent être lentes ou différées', DOWN: 'Incident : au moins un service est hors service'};

/** Real measurements only (latency, heartbeats, counters); a component that is not configured says so. */
export function HealthPanel({token}: {token: string}) {
  const [data, setData] = useState<SystemHealth | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() { try { setBusy(true); setError(''); setData(await systemHealth(token)); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); } }
  useEffect(() => { void load(); const t = window.setInterval(() => void load(), 30_000); return () => window.clearInterval(t); }, [token]);
  const overall = data ? STATE[data.overall] : null;
  return <div className="hl">
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {data && overall && <div className={`hl-banner ${overall.cls}`} role="status">
      <NavGlyph g={overall.icon} size={22}/>
      <div><b>{OVERALL[data.overall] || overall.label}</b><small>Mesuré {new Date(data.checked_at).toLocaleTimeString('fr-FR')} · actualisation automatique toutes les 30 s</small></div>
      <button className="es-btn" onClick={() => void load()} disabled={busy}>{busy ? 'Mesure…' : 'Mesurer maintenant'}</button>
    </div>}
    {!data && !error && <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
    {data && <ul className="hl-grid">{data.components.map(c => { const st = STATE[c.state] || STATE.DOWN; return <li key={c.key} className={st.cls}>
      <span className="hl-ico" aria-hidden="true"><NavGlyph g={ICON[c.key] || 'pulse'} size={20}/></span>
      <div><b>{c.label}</b><small>{c.detail}</small></div>
      <em className="hl-pill"><i aria-hidden="true"/>{st.label}</em>
    </li>; })}</ul>}
    {data?.figures && Object.keys(data.figures).length > 0 && <p className="hl-foot">{data.figures.schools_active ?? '—'} école(s) active(s) · {data.figures.sessions_open ?? '—'} session(s) ouverte(s)</p>}
  </div>;
}
