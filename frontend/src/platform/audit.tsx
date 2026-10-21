import {PageTrail} from './navigation';
import React, {useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {downloadAuditCsv, fetchAudit, fetchAuditEvent, type AuditCategory, type AuditDetail, type AuditItem, type AuditQuery} from './audit_api';
import {friendlyError, UserFacingError} from './errors';
import {auditActionLabel, resultLabel} from './labels';
import {NavGlyph} from './nav_icons';
import {fetchSchools} from './schools_api';
import './schools.css';
import './audit.css';

/* Journal d'audit (Plateforme EduSync), lot 2026-10. Read only: the audit trail is append-only on the server (no edit,
   no delete, no correction anywhere). Server-side search (debounced) and filters (applied at once, kept in the URL and
   restored after a detail), keyset pagination, newest first (or oldest). Repetitive events that are identical (same
   action, actor, scope, resource, result) and close in time are grouped visually only; every occurrence stays listed
   and openable. The detail shows only what the event really holds; sensitive values arrive masked from the server. */

export type AuditLinks = {canSchools: boolean; canTeam: boolean; canAccess: boolean; canNotify: boolean;
  onOpenSchool: (id: string) => void; onOpenMember: (id: string) => void; onOpenUser: (id: string) => void; onOpenCampaign: (id: string) => void};

const LIMIT = 50;
const EMPTY: AuditQuery = {q: '', category: '', action: '', school: '', schoolName: '', actor: '', result: '', from: '', to: '', sort: 'newest'};
const CHIPS: [AuditCategory, string][] = [['', 'Tous'], ['FAILURES', 'Échecs'], ['SECURITY', 'Sécurité'], ['PLATFORM', 'Plateforme'], ['SCHOOLS', 'Écoles']];
const SOURCE: Record<string, string> = {WEB: 'Application web', OFFLINE: 'Hors ligne', SYNC: 'Synchronisation', SYSTEM: 'Système', IMPORT: 'Import', MIGRATION: 'Migration'};
const GROUP_GAP_MS = 10 * 60 * 1000;
const msg = (e: unknown) => e instanceof UserFacingError ? e.message : friendlyError(e);
const when = (iso: string) => new Date(iso).toLocaleString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'});
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'});
const exact = (iso: string) => `${new Date(iso).toLocaleString('fr-FR', {dateStyle: 'full', timeStyle: 'medium'})} (${Intl.DateTimeFormat().resolvedOptions().timeZone || 'heure locale'}) · ${iso}`;

function readUrl(): {f: AuditQuery; event: string | null} {
  const p = new URLSearchParams(window.location.search);
  const cat = p.get('acat') || ''; const res = p.get('ares') || '';
  return {f: {q: (p.get('aq') || '').slice(0, 120), category: (['FAILURES', 'SECURITY', 'PLATFORM', 'SCHOOLS'].includes(cat) ? cat : '') as AuditCategory,
    action: (p.get('aact') || '').slice(0, 96), school: (p.get('asch') || '').slice(0, 64), schoolName: (p.get('aschn') || '').slice(0, 160),
    actor: (p.get('aactor') || '').slice(0, 120), result: (['SUCCESS', 'REJECTED', 'FAILED'].includes(res) ? res : '') as AuditQuery['result'],
    from: /^\d{4}-\d{2}-\d{2}$/.test(p.get('afrom') || '') ? p.get('afrom')! : '', to: /^\d{4}-\d{2}-\d{2}$/.test(p.get('ato') || '') ? p.get('ato')! : '',
    sort: p.get('asort') === 'oldest' ? 'oldest' : 'newest'}, event: p.get('aevent')};
}
function writeUrl(f: AuditQuery, event: string | null, push = false) {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set('aq', f.q.trim()); if (f.category) p.set('acat', f.category); if (f.action) p.set('aact', f.action);
  if (f.school) { p.set('asch', f.school); p.set('aschn', f.schoolName); } if (f.actor.trim()) p.set('aactor', f.actor.trim());
  if (f.result) p.set('ares', f.result); if (f.from) p.set('afrom', f.from); if (f.to) p.set('ato', f.to); if (f.sort !== 'newest') p.set('asort', f.sort);
  if (event) p.set('aevent', event);
  const url = `${window.location.pathname}${p.toString() ? `?${p}` : ''}`;
  const state = {...(history.state || {}), edusyncScope: 'platform', edusyncScreen: 'audit', auditEvent: event || undefined};
  if (push) history.pushState(state, '', url); else history.replaceState(state, '', url);
}
/** Same action, actor, scope, resource and result, each occurrence within 10 minutes of the previous one. */
function groupRows(rows: AuditItem[]): AuditItem[][] {
  const out: AuditItem[][] = [];
  for (const r of rows) {
    const g = out[out.length - 1]; const last = g?.[g.length - 1];
    const same = last && last.action === r.action && last.actor_user_id === r.actor_user_id && last.school_id === r.school_id
      && last.entity_id === r.entity_id && last.result === r.result && Math.abs(new Date(last.occurred_at).getTime() - new Date(r.occurred_at).getTime()) <= GROUP_GAP_MS;
    if (same) g.push(r); else out.push([r]);
  }
  return out;
}
function ResultBadge({r}: {r: string}) {
  const ok = r === 'SUCCESS';
  return <span className={`sc-badge au-r-${r.toLowerCase()}`}><NavGlyph g={ok ? 'check' : 'alert'} size={12}/>{resultLabel(r)}</span>;
}

export function AuditPanel({token, canExport, links}: {token: string; canExport: boolean; links?: AuditLinks}) {
  const initial = useRef(readUrl());
  const [f, setF] = useState<AuditQuery>(initial.current.f);
  const [qInput, setQInput] = useState(initial.current.f.q);
  const [actorInput, setActorInput] = useState(initial.current.f.actor);
  const [cursors, setCursors] = useState<({at: string; id: string} | null)[]>([null]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{items: AuditItem[]; has_more: boolean; next: {at: string; id: string} | null} | null>(null);
  const [extra, setExtra] = useState<AuditItem[]>([]);
  const [moreCursor, setMoreCursor] = useState<{at: string; id: string} | null | undefined>(undefined);
  const [actions, setActions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [event, setEvent] = useState<string | null>(initial.current.event);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [searchOpen, setSearchOpen] = useState(Boolean(initial.current.f.q));
  const [sheet, setSheet] = useState(false);
  const [menu, setMenu] = useState(false);
  const [exporting, setExporting] = useState(false);
  const scrollY = useRef(0);
  const reqId = useRef(0);
  const set = (patch: Partial<AuditQuery>) => { setF(x => ({...x, ...patch})); setCursors([null]); setPage(1); setExtra([]); };
  useEffect(() => { if (qInput === f.q) return; const t = window.setTimeout(() => set({q: qInput}), 300); return () => window.clearTimeout(t); }, [qInput]);
  useEffect(() => { if (actorInput === f.actor) return; const t = window.setTimeout(() => set({actor: actorInput}), 350); return () => window.clearTimeout(t); }, [actorInput]);
  useEffect(() => {
    const id = ++reqId.current; const ctl = new AbortController();
    setLoading(true); setError('');
    fetchAudit(token, f, cursors[page - 1] ?? null, LIMIT, ctl.signal)
      .then(r => { if (id !== reqId.current) return; setData({items: r.items, has_more: r.has_more, next: r.next_cursor}); setActions(r.actions); setExtra([]); setMoreCursor(undefined);
        if (r.next_cursor) setCursors(c => { const n = c.slice(0, page); n[page] = r.next_cursor; return n; }); })
      .catch(e => { if (!ctl.signal.aborted && id === reqId.current) setError(msg(e)); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
    return () => ctl.abort();
  }, [token, f, page, retry]);
  useEffect(() => { writeUrl(f, event); }, [f]);
  useEffect(() => {
    const h = () => { const u = readUrl(); setEvent(u.event); if (!u.event) window.setTimeout(() => window.scrollTo(0, scrollY.current), 0); };
    window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h);
  }, []);
  function open(id: string) { scrollY.current = window.scrollY; setEvent(id); writeUrl(f, id, true); window.scrollTo(0, 0); }
  function back() { if (history.state?.auditEvent) history.back(); else { setEvent(null); writeUrl(f, null); window.setTimeout(() => window.scrollTo(0, scrollY.current), 0); } }
  async function loadMore() {
    const cursor = moreCursor === undefined ? data?.next : moreCursor;
    if (!cursor) return;
    try { setLoading(true); const r = await fetchAudit(token, f, cursor, LIMIT); setExtra(x => [...x, ...r.items]); setMoreCursor(r.next_cursor); }
    catch (e) { setError(msg(e)); } finally { setLoading(false); }
  }
  async function exportCsv() {
    setMenu(false);
    if (!f.from) { toast.error('Pour exporter, choisissez une date de début (période de 92 jours au maximum).'); setSheet(true); return; }
    try { setExporting(true); await downloadAuditCsv(token, f); toast.success('Export prêt : il reprend tous les filtres et il est lui-même tracé dans l’audit.'); }
    catch (e) { toast.error(msg(e)); } finally { setExporting(false); }
  }
  const rows = [...(data?.items || []), ...extra];
  const groups = groupRows(rows);
  const filtered = Boolean(f.q.trim() || f.category || f.action || f.school || f.actor.trim() || f.result || f.from || f.to);
  const extraCount = [f.action, f.school, f.actor.trim(), f.result, f.from, f.to].filter(Boolean).length + (f.sort !== 'newest' ? 1 : 0);
  const moreOnPhone = moreCursor === undefined ? data?.has_more : Boolean(moreCursor);
  const fields = <>
    <label className="sc-select"><span>Action</span><select value={f.action} onChange={e => set({action: e.target.value})}>
      <option value="">Toutes</option>{actions.map(a => <option key={a} value={a}>{auditActionLabel(a)}</option>)}</select></label>
    <label className="sc-select"><span>Résultat</span><select value={f.result} onChange={e => set({result: e.target.value as AuditQuery['result']})}>
      <option value="">Tous</option><option value="SUCCESS">Réussi</option><option value="REJECTED">Refusé</option><option value="FAILED">Échoué</option></select></label>
    <label className="sc-select au-actor"><span>Auteur</span><input type="search" value={actorInput} onChange={e => setActorInput(e.target.value)} placeholder="Nom ou e-mail" maxLength={120}/></label>
    <SchoolFilter token={token} value={f.school ? {id: f.school, name: f.schoolName} : null} onChange={s => set({school: s?.id || '', schoolName: s?.name || ''})}/>
    <label className="sc-select au-date"><span>Du</span><input type="date" value={f.from} max={f.to || undefined} onChange={e => set({from: e.target.value})} aria-label="Date de début"/></label>
    <label className="sc-select au-date"><span>Au</span><input type="date" value={f.to} min={f.from || undefined} onChange={e => set({to: e.target.value})} aria-label="Date de fin"/></label>
    <label className="sc-select"><span>Tri</span><select value={f.sort} onChange={e => set({sort: e.target.value as AuditQuery['sort']})}>
      <option value="newest">Plus récents</option><option value="oldest">Plus anciens</option></select></label>
  </>;

  return <>
    {event && <EventView token={token} id={event} links={links} onBack={back} onOpen={id => { setEvent(id); writeUrl(f, id); window.scrollTo(0, 0); }}/>}
    <div className="sc au" hidden={Boolean(event)}>
      <header className="sc-head">
        <div><h2>Journal d’audit</h2><p>Toutes les actions tracées de la plateforme et des écoles, selon vos autorisations.</p></div>
        <div className="sc-head-actions">
          <button type="button" className="sc-icon-btn sc-only-phone" aria-label="Rechercher dans le journal" aria-expanded={searchOpen} onClick={() => setSearchOpen(o => !o)}><NavGlyph g="search" size={18}/></button>
          {canExport && <div className="sc-menu au-menu">
            <button type="button" className="sc-btn sc-btn-ghost sc-hide-phone" disabled={exporting} onClick={() => void exportCsv()}><NavGlyph g="download" size={16}/>{exporting ? 'Export…' : 'Exporter (CSV)'}</button>
            <button type="button" className="sc-icon-btn sc-only-phone" aria-label="Plus d’actions" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(m => !m)}><NavGlyph g="more" size={18}/></button>
            {menu && <div className="sc-menu-pop" role="menu"><button type="button" role="menuitem" onClick={() => void exportCsv()}><NavGlyph g="download" size={16}/>Exporter (CSV)</button></div>}
          </div>}
        </div>
      </header>
      <div className={`sc-toolbar ${searchOpen ? 'sc-search-open' : ''}`}>
        <label className="sc-search"><NavGlyph g="search" size={17}/>
          <input type="search" value={qInput} onChange={e => setQInput(e.target.value)} placeholder="Action, objet, motif, auteur ou identifiant" aria-label="Rechercher dans le journal" maxLength={120}/>
          {loading && qInput !== '' && <i className="sc-spin" aria-hidden="true"/>}
          {qInput && <button type="button" className="sc-clear" aria-label="Effacer la recherche" onClick={() => setQInput('')}><NavGlyph g="close" size={15}/></button>}
        </label>
        <div className="sc-chips" role="group" aria-label="Catégorie">
          {CHIPS.map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.category === v} onClick={() => set({category: v})}>{l}</button>)}
        </div>
        <div className="sc-filters sc-hide-phone au-filters">{fields}</div>
        <button type="button" className="sc-btn sc-btn-ghost sc-only-phone sc-filter-btn" onClick={() => setSheet(true)}><NavGlyph g="sliders" size={16}/>Filtrer{extraCount ? <b className="sc-dot" aria-label="filtre actif"/> : null}</button>
      </div>
      <div className="sc-summary" role="status" aria-live="polite">
        {data ? <span><b>{rows.length.toLocaleString('fr-FR')}</b> événement{rows.length > 1 ? 's' : ''} affiché{rows.length > 1 ? 's' : ''}{data.has_more || moreCursor ? ' (suite disponible)' : ''}</span> : <i className="sc-skel sc-skel-line" aria-hidden="true"/>}
        {filtered && <button type="button" className="sc-link" onClick={() => { setQInput(''); setActorInput(''); set({...EMPTY}); }}>Réinitialiser les filtres</button>}
      </div>
      {error ? <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Impossible de charger le journal.</b><small>{error}</small></div>
        <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setRetry(k => k + 1)}>Réessayer</button></div>
        : !data && loading ? <div className="sc-list" aria-busy="true" aria-label="Chargement du journal">{Array.from({length: 7}).map((_, i) => <div key={i} className="sc-row au-row sc-row-skel">
            <span><i className="sc-skel" style={{width: 64}}/></span><span><i className="sc-skel" style={{width: '70%'}}/><i className="sc-skel" style={{width: '45%'}}/></span>
            <span className="au-col-scope"><i className="sc-skel" style={{width: '60%'}}/></span><span><i className="sc-skel" style={{width: 90}}/></span><span/></div>)}</div>
        : rows.length === 0 ? <div className="sc-empty"><NavGlyph g={f.q ? 'search' : 'audit'} size={24}/>
            <b>{f.q.trim() ? `Aucun résultat pour « ${f.q.trim()} ».` : f.school ? 'Aucun événement pour cette école.' : f.from || f.to ? 'Aucun événement dans cette période.' : filtered ? 'Aucun événement ne correspond à ces filtres.' : 'Aucun événement enregistré.'}</b>
            {filtered && <small>Élargissez la recherche ou les filtres.</small>}</div>
        : <div className={`sc-list ${loading ? 'sc-busy' : ''}`} role="table" aria-label="Événements du journal d’audit">
          <div className="sc-row au-row sc-row-head" role="row"><span role="columnheader">Résultat</span><span role="columnheader">Action</span>
            <span role="columnheader" className="au-col-scope">Portée</span><span role="columnheader">Date</span><span role="columnheader"><span className="es-sr">Ouvrir</span></span></div>
          {groups.map(g => {
            const r = g[0]; const key = r.id;
            if (g.length === 1) return <Row key={key} r={r} onOpen={open}/>;
            const isOpen = expanded.has(key);
            const times = [g[g.length - 1].occurred_at, g[0].occurred_at].sort();
            return <React.Fragment key={key}>
              <div className="sc-row au-row au-group" role="row" tabIndex={0} aria-expanded={isOpen}
                aria-label={`${auditActionLabel(r.action)}, ${g.length} occurrences, ${r.actor || 'Système'}. ${isOpen ? 'Replier' : 'Voir les occurrences'}`}
                onClick={() => setExpanded(s => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; })}
                onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); (e.currentTarget as HTMLElement).click(); } }}>
                <span role="cell" className="au-col-res"><ResultBadge r={r.result}/></span>
                <span role="cell" className="au-col-what"><b>{auditActionLabel(r.action)} <em className="au-times">× {g.length}</em></b><small>{r.actor || 'Système'}</small></span>
                <span role="cell" className="au-col-scope"><b>{r.school_name || 'Plateforme'}</b>{r.school_code && <small>{r.school_code}</small>}</span>
                <span role="cell" className="au-col-when"><small>{new Date(times[0]).toDateString() === new Date(times[1]).toDateString() ? `${hhmm(times[0])}–${hhmm(times[1])}` : `${when(times[0])} – ${when(times[1])}`}</small><small className="au-group-hint">{isOpen ? 'Replier' : 'Voir les occurrences'}</small></span>
                <span role="cell" className="au-col-chev" aria-hidden="true"><NavGlyph g={isOpen ? 'chevronDown' : 'chevronRight'} size={18}/></span>
              </div>
              {isOpen && g.map(o => <Row key={o.id} r={o} onOpen={open} nested/>)}
            </React.Fragment>;
          })}
        </div>}
      {data && rows.length > 0 && <>
        <nav className="sc-pager sc-hide-phone" aria-label="Pagination">
          <span>Page {page}</span>
          <div><button type="button" className="sc-btn sc-btn-ghost" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}><NavGlyph g="chevronLeft" size={16}/>Précédent</button>
            <button type="button" className="sc-btn sc-btn-ghost" disabled={!data.has_more || loading} onClick={() => setPage(page + 1)}>Suivant<NavGlyph g="chevronRight" size={16}/></button></div>
        </nav>
        {moreOnPhone && <button type="button" className="sc-btn sc-more sc-only-phone" disabled={loading} onClick={() => void loadMore()}>{loading ? 'Chargement…' : 'Charger la suite'}</button>}
      </>}
      {sheet && <div className="sc-fsheet-backdrop mobileSheetBackdrop" onMouseDown={e => e.currentTarget === e.target && setSheet(false)}>
        <div className="sc-fsheet au-sheet" role="dialog" aria-modal="true" aria-label="Filtrer le journal">
          <div className="sc-fsheet-head mobileSheetHead"><b>Filtrer</b><button type="button" aria-label="Fermer" onClick={() => setSheet(false)}><NavGlyph g="close" size={18}/></button></div>
          <div className="au-sheet-fields">{fields}</div>
          <div className="au-sheet-foot"><button type="button" className="sc-btn sc-btn-ghost" onClick={() => { setActorInput(''); set({...EMPTY, q: f.q, category: f.category}); }}>Réinitialiser</button>
            <button type="button" className="sc-btn sc-btn-primary" onClick={() => setSheet(false)}>Appliquer</button></div>
        </div></div>}
    </div>
  </>;
}

function Row({r, onOpen, nested}: {r: AuditItem; onOpen: (id: string) => void; nested?: boolean}) {
  return <div className={`sc-row au-row ${nested ? 'au-nested' : ''}`} role="row" tabIndex={0}
    aria-label={`${resultLabel(r.result)} : ${auditActionLabel(r.action)}, ${r.actor || 'Système'}, ${r.school_name || 'Plateforme'}, ${when(r.occurred_at)}. Ouvrir le détail`}
    onClick={() => onOpen(r.id)} onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); onOpen(r.id); } }}>
    <span role="cell" className="au-col-res"><ResultBadge r={r.result}/></span>
    <span role="cell" className="au-col-what"><b>{auditActionLabel(r.action)}</b><small>{r.actor || 'Système'}{r.reason ? ` · ${r.reason}` : ''}</small></span>
    <span role="cell" className="au-col-scope"><b>{r.school_name || 'Plateforme'}</b>{r.school_code && <small>{r.school_code}</small>}</span>
    <span role="cell" className="au-col-when"><small>{when(r.occurred_at)}</small></span>
    <span role="cell" className="au-col-chev" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span>
  </div>;
}

function SchoolFilter({token, value, onChange}: {token: string; value: {id: string; name: string} | null; onChange: (s: {id: string; name: string} | null) => void}) {
  const [q, setQ] = useState(''); const [items, setItems] = useState<{id: string; name: string; code: string}[]>([]); const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return; const ctl = new AbortController();
    const t = window.setTimeout(() => { fetchSchools(token, {q, status: '', config: '', sort: 'name'}, null, 8, ctl.signal).then(r => setItems(r.items.map(s => ({id: s.id, name: s.name, code: s.code})))).catch(() => setItems([])); }, 300);
    return () => { window.clearTimeout(t); ctl.abort(); };
  }, [q, open]);
  useEffect(() => { if (!open) return; const d = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); }; window.addEventListener('mousedown', d); return () => window.removeEventListener('mousedown', d); }, [open]);
  if (value) return <div className="sc-select au-school"><span>École</span><b title={value.name}>{value.name}</b>
    <button type="button" className="sc-clear" aria-label="Retirer le filtre école" onClick={() => onChange(null)}><NavGlyph g="close" size={14}/></button></div>;
  return <div className="sc-select au-school" ref={box}><span>École</span>
    <input type="search" value={q} placeholder="Toutes" aria-label="Filtrer par école" role="combobox" aria-expanded={open} onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true); }} maxLength={80}/>
    {open && items.length > 0 && <div className="sc-menu-pop au-school-pop" role="listbox">{items.map(s => <button key={s.id} type="button" role="option" aria-selected={false}
      onClick={() => { onChange({id: s.id, name: s.name}); setOpen(false); setQ(''); }}><b>{s.name}</b><small>{s.code}</small></button>)}</div>}
  </div>;
}

/* ---------------------------------------------------------------- event detail (read only) */
function EventView({token, id, links, onBack, onOpen}: {token: string; id: string; links?: AuditLinks; onBack: () => void; onOpen: (id: string) => void}) {
  const [d, setD] = useState<AuditDetail | null>(null); const [error, setError] = useState(''); const [nonce, setNonce] = useState(0);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { const ctl = new AbortController(); setD(null); setError(''); fetchAuditEvent(token, id, ctl.signal).then(setD).catch(e => { if (!ctl.signal.aborted) setError(msg(e)); }); return () => ctl.abort(); }, [token, id, nonce]);
  useEffect(() => { if (d) title.current?.focus({preventScroll: true}); }, [d?.id]);
  const backBtn = <PageTrail parents={[{label: 'Journal d’audit', onSelect: onBack}]} current={'Événement'}/>;
  if (error) return <div className="sc-sheet-page">{backBtn}<div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Événement indisponible.</b><small>{error}</small></div>
    <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setNonce(n => n + 1)}>Réessayer</button></div></div>;
  if (!d) return <div className="sc-sheet-page" aria-busy="true">{backBtn}<div className="sc-card"><i className="sc-skel" style={{width: '50%', height: 22}}/><i className="sc-skel" style={{width: '70%'}}/></div></div>;
  const copy = (v: string, label: string) => { void navigator.clipboard?.writeText(v).then(() => toast.success(`${label} copié`)); };
  const ctx = d.context; const actions: React.ReactNode[] = [];
  if (links && d.school_id && ctx.school_exists && links.canSchools) actions.push(<button key="s" type="button" className="sc-btn sc-btn-ghost" onClick={() => links.onOpenSchool(d.school_id!)}>Voir l’école</button>);
  if (links && d.entity_id && ctx.entity_is_school && d.entity_id !== d.school_id && links.canSchools) actions.push(<button key="es" type="button" className="sc-btn sc-btn-ghost" onClick={() => links.onOpenSchool(d.entity_id!)}>Voir l’école concernée</button>);
  if (links && d.actor_user_id && ctx.actor_is_member && links.canTeam) actions.push(<button key="m" type="button" className="sc-btn sc-btn-ghost" onClick={() => links.onOpenMember(d.actor_user_id!)}>Voir le membre plateforme</button>);
  if (links && d.entity_id && ctx.entity_is_user && links.canAccess) actions.push(<button key="u" type="button" className="sc-btn sc-btn-ghost" onClick={() => links.onOpenUser(d.entity_id!)}>Voir l’utilisateur concerné</button>);
  if (links && d.entity_id && ctx.entity_is_campaign && links.canNotify) actions.push(<button key="c" type="button" className="sc-btn sc-btn-ghost" onClick={() => links.onOpenCampaign(d.entity_id!)}>Voir la notification</button>);
  if (d.correlation_id) actions.push(<button key="cid" type="button" className="sc-btn sc-btn-ghost" onClick={() => copy(d.correlation_id!, 'Identifiant de corrélation')}><NavGlyph g="doc" size={15}/>Copier l’identifiant de corrélation</button>);
  const hasChanges = Boolean((d.old_json && Object.keys(d.old_json).length) || (d.new_json && Object.keys(d.new_json).length));
  return <div className="sc-sheet-page">
    {backBtn}
    <header className="sc-card sc-sheet-head">
      <div className="sc-sheet-id"><span className={`sc-sheet-logo au-logo au-logo-${d.result.toLowerCase()}`} aria-hidden="true"><NavGlyph g={d.result === 'SUCCESS' ? 'checkCircle' : 'alert'} size={24}/></span>
        <div><h2 ref={title} tabIndex={-1}>{auditActionLabel(d.action)}</h2><p>{exact(d.occurred_at)}</p><div className="sc-badges"><ResultBadge r={d.result}/></div></div></div>
    </header>
    {actions.length > 0 && <div className="au-actions">{actions}</div>}
    <div className="sc-sheet-grid">
      <section className="sc-card"><h3>Résumé</h3><dl className="sc-dl">
        <dt>Action</dt><dd>{auditActionLabel(d.action)}</dd><dt>Résultat</dt><dd>{resultLabel(d.result)}</dd>
        <dt>Auteur</dt><dd>{d.actor || 'Système'}{d.actor_email ? ` (${d.actor_email})` : ''}</dd>
        {d.reason && <><dt>Motif</dt><dd>{d.reason}</dd></>}</dl></section>
      <section className="sc-card"><h3>Contexte</h3><dl className="sc-dl">
        <dt>Portée</dt><dd>{d.school_id ? 'École' : 'Plateforme'}</dd>
        {d.school_id && <><dt>École</dt><dd>{d.school_name ? `${d.school_name} · ${d.school_code}` : 'École supprimée ou inconnue'}</dd></>}
        <dt>Origine</dt><dd>{SOURCE[d.source] || d.source}</dd></dl></section>
      <section className="sc-card"><h3>Ressource</h3><dl className="sc-dl">
        <dt>Type</dt><dd>{d.entity_type}</dd>{d.entity_id && <><dt>Identifiant</dt><dd><code className="au-code">{d.entity_id}</code></dd></>}</dl></section>
      <section className="sc-card"><h3>Technique</h3><dl className="sc-dl">
        <dt>Code de l’action</dt><dd><code className="au-code">{d.action}</code></dd><dt>Événement</dt><dd><code className="au-code">{d.id}</code></dd>
        {d.correlation_id && <><dt>Corrélation</dt><dd><code className="au-code">{d.correlation_id}</code></dd></>}
        {d.causation_id && <><dt>Cause</dt><dd><code className="au-code">{d.causation_id}</code></dd></>}
        {d.device_id && <><dt>Appareil</dt><dd><code className="au-code">{d.device_id}</code></dd></>}</dl></section>
    </div>
    {hasChanges && <section className="sc-card"><h3>Changements</h3><Changes before={d.old_json} after={d.new_json}/></section>}
    {d.related?.length > 0 && <section className="sc-card"><h3>Événements liés (même corrélation)</h3>
      <ul className="au-related">{d.related.map(x => <li key={x.id}><button type="button" className="sc-row au-row au-rel" onClick={() => onOpen(x.id)}>
        <span className="au-col-res"><ResultBadge r={x.result}/></span><span className="au-col-what"><b>{auditActionLabel(x.action)}</b></span><span className="au-col-when"><small>{when(x.occurred_at)}</small></span></button></li>)}</ul></section>}
    <p className="sc-hint"><NavGlyph g="lock" size={12}/> Le journal d’audit est en ajout seul : aucun événement ne peut être modifié ni supprimé. Les valeurs sensibles sont masquées.</p>
  </div>;
}

function Changes({before, after}: {before: Record<string, unknown> | null; after: Record<string, unknown> | null}) {
  const keys = Array.from(new Set([...Object.keys(before || {}), ...Object.keys(after || {})])).sort();
  const show = (v: unknown) => v === undefined ? '—' : v !== null && typeof v === 'object' ? JSON.stringify(v) : String(v);
  return <div className="au-diff-wrap"><table className="au-diff"><caption className="es-sr">Valeurs avant et après</caption>
    <thead><tr><th scope="col">Champ</th>{before && <th scope="col">Avant</th>}<th scope="col">{before ? 'Après' : 'Valeur'}</th></tr></thead>
    <tbody>{keys.map(k => { const a = show(before?.[k]), b = show(after?.[k]); return <tr key={k} className={before && a !== b ? 'au-changed' : ''}><th scope="row">{k}</th>{before && <td>{a}</td>}<td>{b}</td></tr>; })}</tbody></table></div>;
}
