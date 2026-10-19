import React, {useEffect, useRef, useState} from 'react';
import {inboxList, inboxRead, inboxReadAll, type InboxItem, type InboxScope} from '../api';
import {friendlyError} from './errors';
import {NavGlyph} from './nav_icons';
import './notification_center.css';

const SEV: Record<string, {label: string; cls: string; icon: string}> = {
  INFO: {label: 'Information', cls: 'nc-info', icon: 'info'},
  WARNING: {label: 'Avertissement', cls: 'nc-warn', icon: 'alert'},
  CRITICAL: {label: 'Critique', cls: 'nc-crit', icon: 'alert'},
};

function when(iso: string) {
  const d = new Date(iso); const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 2) return 'À l’instant';
  if (mins < 60) return `Il y a ${mins} min`;
  if (mins < 60 * 24) return `Il y a ${Math.round(mins / 60)} h`;
  return d.toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'});
}

/** Internal links only (validated server-side and in the database); never an external URL. */
function safeLink(path: string | null) { return path && /^\/[A-Za-z0-9/_?=&.-]*$/.test(path) && !path.startsWith('//') ? path : null; }

/** Also used as the recipient preview of the composer (same component as the real bell). */
export function Item({n, onRead, canRead}: {n: InboxItem; onRead: (n: InboxItem) => void; canRead: boolean}) {
  const sev = SEV[n.severity] || SEV.INFO; const link = safeLink(n.link_path);
  return <li className={`nc-item ${n.read_at ? '' : 'nc-unread'} ${sev.cls}`}>
    <span className="nc-sev" aria-hidden="true"><NavGlyph g={sev.icon} size={16}/></span>
    <div className="nc-body">
      <b>{!n.read_at && <span className="nc-dot" aria-label="Non lue"/>}{n.title}</b>
      <p>{n.body}</p>
      <small>{sev.label} · {when(n.created_at)}{n.expires_at ? ` · expire le ${new Date(n.expires_at).toLocaleDateString('fr-FR')}` : ''}</small>
      <span className="nc-acts">
        {link && <a className="es-btn es-btn-ghost" href={link} onClick={() => !n.read_at && canRead && onRead(n)}>Ouvrir</a>}
        {!n.read_at && canRead && <button className="es-btn es-btn-ghost" onClick={() => onRead(n)}>Marquer comme lue</button>}
      </span>
    </div>
  </li>;
}

export function NotificationCenterDialog({token, scope, canRead, onClose, onChanged}: {token: string; scope: InboxScope; canRead: boolean; onClose: () => void; onChanged: () => void}) {
  const [status, setStatus] = useState<'all' | 'unread' | 'read'>('all');
  const [severity, setSeverity] = useState('');
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [cursor, setCursor] = useState<{at: string; id: string} | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  async function load(more = false) {
    try { setError(''); const r = await inboxList(token, scope, {status, severity, cursor: more ? cursor : null}); setItems(prev => more && prev ? [...prev, ...r.items] : r.items); setCursor(r.next_cursor); setUnread(r.unread); }
    catch (e) { setError(friendlyError(e)); }
  }
  useEffect(() => { void load(); }, [status, severity]);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null; ref.current?.querySelector<HTMLElement>('button,select')?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey); return () => { window.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, []);
  async function read(n: InboxItem) { try { await inboxRead(token, scope, n.id); await load(); onChanged(); } catch (e) { setError(friendlyError(e)); } }
  async function readAll() { try { await inboxReadAll(token, scope); await load(); onChanged(); } catch (e) { setError(friendlyError(e)); } }
  return <div className="es-modal-backdrop" onMouseDown={e => e.currentTarget === e.target && onClose()}>
    <div className="es-modal es-modal-wide nc-center" role="dialog" aria-modal="true" aria-labelledby="nc-title" ref={ref}>
      <div className="es-modal-head"><div><h2 id="nc-title">Notifications</h2><p>{unread ? `${unread} non lue(s)` : 'Tout est lu'}</p></div>
        <button className="es-icon-btn" aria-label="Fermer" onClick={onClose}><NavGlyph g="close" size={18}/></button></div>
      <div className="nc-toolbar">
        <div className="es-tabs nc-tabs" role="tablist" aria-label="Filtrer par statut">
          {(['all', 'unread', 'read'] as const).map(s => <button key={s} role="tab" aria-selected={status === s} className={status === s ? 'es-on' : ''} onClick={() => setStatus(s)}>{s === 'all' ? 'Toutes' : s === 'unread' ? 'Non lues' : 'Lues'}</button>)}
        </div>
        <select aria-label="Filtrer par gravité" value={severity} onChange={e => setSeverity(e.target.value)}><option value="">Toutes gravités</option><option value="INFO">Information</option><option value="WARNING">Avertissement</option><option value="CRITICAL">Critique</option></select>
        {unread > 0 && canRead && <button className="es-btn" onClick={() => void readAll()}>Tout marquer comme lu</button>}
      </div>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      {items === null ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> : items.length === 0 ? <div className="es-empty">Aucune notification.</div> :
        <ul className="nc-list">{items.map(n => <Item key={n.id} n={n} onRead={read} canRead={canRead}/>)}</ul>}
      {cursor && <button className="es-btn es-btn-ghost nc-more" onClick={() => void load(true)}>Charger plus</button>}
    </div>
  </div>;
}

/** Real-time "inbox changed" signals (Server-Sent Events read with fetch so the access token travels in the
 *  Authorization header, never in the URL). Reconnects with backoff; the caller keeps a slow periodic refresh. */
function useInboxStream(token: string, scope: InboxScope, onChange: () => void) {
  const cb = useRef(onChange); cb.current = onChange;
  useEffect(() => {
    let stopped = false; let ctrl: AbortController | null = null; let delayMs = 2000;
    const url = scope === 'platform' ? '/api/v1/platform/inbox/stream' : '/api/v1/notifications/stream';
    async function connect() {
      while (!stopped) {
        ctrl = new AbortController();
        try {
          const r = await fetch(url, {headers: {Authorization: `Bearer ${token}`, Accept: 'text/event-stream'}, signal: ctrl.signal, cache: 'no-store'});
          if (!r.ok || !r.body) throw new Error(String(r.status));
          delayMs = 2000;
          const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
          for (;;) {
            const {value, done} = await reader.read(); if (done) break;
            buf += dec.decode(value, {stream: true});
            let i; while ((i = buf.indexOf('\n\n')) >= 0) { const evt = buf.slice(0, i); buf = buf.slice(i + 2); if (/^event: inbox$/m.test(evt)) cb.current(); }
          }
        } catch { if (stopped) return; }
        if (stopped) return;
        await new Promise(res => setTimeout(res, delayMs)); delayMs = Math.min(delayMs * 2, 60_000);
      }
    }
    void connect();
    return () => { stopped = true; ctrl?.abort(); };
  }, [token, scope]);
}

/** Bell with unread counter and quick panel; "Voir tout" opens the full notification center. */
export function NotificationBell({token, canDismiss, scope = 'school'}: {token: string; canDismiss: boolean; scope?: InboxScope}) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [center, setCenter] = useState(false);
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  async function load() { try { const r = await inboxList(token, scope, {status: 'all', severity: '', cursor: null, limit: 8}); setItems(r.items); setUnread(r.unread); setFailed(false); } catch { setFailed(true); } }
  useEffect(() => { void load(); const t = window.setInterval(() => void load(), 120_000); return () => window.clearInterval(t); }, [token, scope]);
  useInboxStream(token, scope, () => void load());  // real time; the 2-minute refresh is only a safety net
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); ref.current?.querySelector<HTMLElement>('button')?.focus(); } };
    window.addEventListener('mousedown', onDown); window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey); };
  }, [open]);
  async function read(n: InboxItem) { try { await inboxRead(token, scope, n.id); await load(); } catch { /* reste non lue */ } }
  return <div className="es-account nc-bell" ref={ref}>
    <button className="es-icon-btn" aria-label={unread ? `Notifications, ${unread} non lue(s)` : 'Notifications'} aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(x => !x)}>
      <NavGlyph g="bell" size={18}/>{unread > 0 && <span className="es-badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
    </button>
    {open && <div className="es-pop nc-pop" role="dialog" aria-label="Notifications récentes">
      <div className="es-pop-head"><span>Notifications</span>{unread > 0 && canDismiss ? <button className="nc-link" onClick={async () => { await inboxReadAll(token, scope); await load(); }}>Tout marquer comme lu</button> : unread > 0 ? <small>{unread} non lue(s)</small> : null}</div>
      {failed ? <div className="es-pop-empty">Notifications momentanément indisponibles.</div> : items.length === 0 ? <div className="es-pop-empty">Aucune notification.</div> :
        <ul className="nc-list nc-list-compact">{items.map(n => <Item key={n.id} n={n} onRead={read} canRead={canDismiss}/>)}</ul>}
      <button className="nc-all" onClick={() => { setOpen(false); setCenter(true); }}>Voir toutes les notifications</button>
    </div>}
    {center && <NotificationCenterDialog token={token} scope={scope} canRead={canDismiss} onClose={() => setCenter(false)} onChanged={() => void load()}/>}
  </div>;
}
