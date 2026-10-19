import React, {useCallback, useEffect, useRef, useState} from 'react';
import {friendlyError, UserFacingError} from './errors';
import {fetchIdentities, fetchIdentity, fetchIdentityFilters, IDENTITY_STATUS_LABEL, SCOPE_LABEL, type FilterRole, type IdentitiesPage,
  type IdentityDetail, type IdentityFilters, type IdentityRow, type IdentityScope, type IdentityStatus} from './identities_api';
import {NavGlyph} from './nav_icons';
import {fetchSchools} from './schools_api';
import './schools.css';
import './identities.css';

/* Annuaire « Utilisateurs & accès » (plateforme), lot 2026-10. A read-only, cross-cutting directory of the identities the
   platform already holds: platform accounts (platform role) and school accounts (school membership). Managing them stays
   where it lives: Équipe plateforme (platform roles, security), the school sheet (administrator), the school space
   (local business roles). Server-side instant search (debounced, stale answers ignored), keyset pagination (pages on
   desktop, "Charger la suite" on phones), state in the URL (?iq=&scope=&istatus=&ischool=&role=&ipage= ; ?user=<id>). */

export type AccessPreset = {activeOnly?: boolean; nonce: number};
type Props = {token: string; has: (cap: string) => boolean; preset?: AccessPreset | null; active: boolean;
  onOpenSchool: (schoolId: string) => void; onOpenTeam: (target: TeamTarget) => void};
/** Navigation only: every change of platform access is made in Équipe plateforme. */
export type TeamTarget = {openMember?: string; addExisting?: {id: string; full_name: string; email: string}};

const LIMIT = 25;
const EMPTY: IdentityFilters = {q: '', scope: '', status: '', schoolId: '', schoolName: '', role: '', activeOnly: false};
const SCOPE_CHIPS: [IdentityFilters['scope'], string][] = [['', 'Tous'], ['PLATFORM', 'Plateforme'], ['SCHOOL', 'Écoles']];
const STATUSES: ['' | IdentityStatus, string][] = [['', 'Tous'], ['ACTIVE', 'Actifs'], ['PENDING', 'Activation en attente'], ['SUSPENDED', 'Accès plateforme suspendu'], ['DISABLED', 'Désactivés']];

/** Accounts deep link: the directory owns these URL keys (distinct from the schools screen keys). */
export const ACCESS_URL_KEYS = /[?&](user|iq|scope|istatus|ischool|role|ipage|iactive)=/;

function readUrl(): {f: IdentityFilters; user: string | null} {
  const p = new URLSearchParams(window.location.search);
  const sc = p.get('scope'); const st = p.get('istatus'); const role = p.get('role') || '';
  return {f: {q: (p.get('iq') || '').slice(0, 80), scope: (['PLATFORM', 'SCHOOL'].includes(sc || '') ? sc : '') as IdentityFilters['scope'],
    status: (['ACTIVE', 'PENDING', 'SUSPENDED', 'DISABLED'].includes(st || '') ? st : '') as IdentityFilters['status'],
    schoolId: /^[0-9a-f-]{36}$/i.test(p.get('ischool') || '') ? p.get('ischool')! : '', schoolName: (p.get('ischoolname') || '').slice(0, 160),
    role: /^[A-Z0-9_]{2,64}$/.test(role) ? role : '', activeOnly: p.get('iactive') === '1'}, user: p.get('user')};
}

function writeUrl(f: IdentityFilters, user: string | null, push = false) {
  const p = new URLSearchParams();
  if (user) p.set('user', user);
  else {
    if (f.q.trim()) p.set('iq', f.q.trim()); if (f.scope) p.set('scope', f.scope); if (f.status) p.set('istatus', f.status);
    if (f.schoolId) { p.set('ischool', f.schoolId); p.set('ischoolname', f.schoolName); } if (f.role) p.set('role', f.role);
    if (f.activeOnly) p.set('iactive', '1');
  }
  const url = `${window.location.pathname}${p.toString() ? `?${p}` : ''}`;
  const state = {...(history.state || {}), edusyncScope: 'platform', edusyncScreen: 'access', user: user || undefined};
  if (push) history.pushState(state, '', url); else history.replaceState(state, '', url);
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
const fullDate = (iso: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'}) : null;
function ago(iso: string | null): string {
  if (!iso) return 'Jamais connecté';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return 'À l’instant';
  if (s < 3600) return `Il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `Il y a ${Math.round(s / 3600)} h`;
  if (s < 86400 * 30) return `Il y a ${Math.round(s / 86400)} j`;
  return new Date(iso).toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'});
}

export function ScopeBadge({scope}: {scope: IdentityScope}) {
  return <span className={`id-scope id-scope-${scope.toLowerCase()}`}>{SCOPE_LABEL[scope]}</span>;
}
export function IdentityStatusBadge({status}: {status: IdentityStatus}) {
  return <span className={`sc-badge id-st-${status.toLowerCase()}`}><i aria-hidden="true"/>{IDENTITY_STATUS_LABEL[status]}</span>;
}

export function AccessDirectory({token, has, preset, active, onOpenSchool, onOpenTeam}: Props) {
  const initial = useRef(readUrl());
  const [f, setF] = useState<IdentityFilters>(initial.current.f);
  const [qInput, setQInput] = useState(initial.current.f.q);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<IdentitiesPage | null>(null);
  const [extra, setExtra] = useState<IdentityRow[]>([]);
  const [moreCursor, setMoreCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openUser, setOpenUser] = useState<string | null>(initial.current.user);
  const [searchOpen, setSearchOpen] = useState(Boolean(initial.current.f.q));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [roles, setRoles] = useState<FilterRole[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const listTop = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const reqId = useRef(0);

  useEffect(() => { if (active && roles.length === 0) void fetchIdentityFilters(token).then(r => setRoles(r.roles)); }, [active]);
  // Dashboard « Accès actifs » → the same definition, applied as a removable filter.
  useEffect(() => {
    if (!preset) return;
    setQInput(''); setF({...EMPTY, activeOnly: Boolean(preset.activeOnly)}); setCursors([null]); setPage(1); setOpenUser(null);
  }, [preset?.nonce]);
  // Debounced instant search: 300 ms after the last key; an older answer is ignored.
  useEffect(() => {
    if (qInput === f.q) return;
    const t = window.setTimeout(() => set({q: qInput}), 300);
    return () => window.clearTimeout(t);
  }, [qInput]);

  const load = useCallback(() => {
    const id = ++reqId.current; const ctl = new AbortController();
    setLoading(true); setError('');
    fetchIdentities(token, f, cursors[page - 1] ?? null, LIMIT, ctl.signal)
      .then(r => { if (id !== reqId.current) return; setData(r); setExtra([]); setMoreCursor(undefined);
        if (r.next_cursor) setCursors(c => { const n = c.slice(0, page); n[page] = r.next_cursor; return n; }); })
      .catch(e => { if (ctl.signal.aborted || id !== reqId.current) return; console.warn('[edusync] annuaire des utilisateurs en échec');
        setError(e instanceof UserFacingError ? e.message : friendlyError(e)); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
    return ctl;
  }, [token, f, page, reloadKey]);
  useEffect(() => { if (!active || openUser) return; const ctl = load(); return () => ctl.abort(); }, [load, active, openUser]);
  useEffect(() => { if (active) writeUrl(f, openUser); }, [f, openUser, active]);
  useEffect(() => {
    const h = () => setOpenUser(readUrl().user);
    window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h);
  }, []);

  function set(patch: Partial<IdentityFilters>) { setF(x => ({...x, ...patch})); setCursors([null]); setPage(1); setExtra([]); }
  const open = (id: string) => { setOpenUser(id); writeUrl(f, id, true); window.scrollTo(0, 0); };
  const back = () => { if (history.state?.user) history.back(); else { setOpenUser(null); writeUrl(f, null); } };
  const goPage = (n: number) => { setPage(n); listTop.current?.scrollIntoView({block: 'start'}); };
  async function loadMore() {
    const cursor = moreCursor === undefined ? data?.next_cursor : moreCursor;
    if (!cursor) return;
    try { setLoading(true); const r = await fetchIdentities(token, f, cursor, LIMIT); setExtra(x => [...x, ...r.items]); setMoreCursor(r.next_cursor); }
    catch (e) { setError(e instanceof UserFacingError ? e.message : friendlyError(e)); } finally { setLoading(false); }
  }

  if (openUser) return <IdentityView token={token} id={openUser} has={has} onBack={back} onOpenSchool={onOpenSchool} onOpenTeam={onOpenTeam}/>;

  const rows = [...(data?.items || []), ...extra];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / LIMIT)) : 1;
  const filtered = Boolean(f.q.trim() || f.scope || f.status || f.schoolId || f.role || f.activeOnly);
  const moreOnPhone = moreCursor === undefined ? data?.has_more : Boolean(moreCursor);
  const extraFilters = [f.status, f.schoolId, f.role].filter(Boolean).length;
  return <div className="sc id">
    <header className="sc-head">
      <div><h2>Utilisateurs & accès</h2><p>Annuaire des comptes plateforme et des comptes rattachés aux écoles (consultation)</p></div>
      <div className="sc-head-actions">
        <button type="button" className="sc-icon-btn sc-only-phone" aria-label="Rechercher un utilisateur" aria-expanded={searchOpen}
          onClick={() => { const o = !searchOpen; setSearchOpen(o); if (o) window.setTimeout(() => searchInput.current?.focus(), 0); }}><NavGlyph g="search" size={18}/></button>
      </div>
    </header>

    <div className={`sc-toolbar ${searchOpen ? 'sc-search-open' : ''}`}>
      <label className="sc-search">
        <NavGlyph g="search" size={17}/>
        <input ref={searchInput} type="search" value={qInput} onChange={e => setQInput(e.target.value)} placeholder="Nom ou adresse e-mail" aria-label="Rechercher un utilisateur" maxLength={80}/>
        {loading && qInput !== '' && <i className="sc-spin" aria-hidden="true"/>}
        {qInput && <button type="button" className="sc-clear" aria-label="Effacer la recherche" onClick={() => setQInput('')}><NavGlyph g="close" size={15}/></button>}
      </label>
      <div className="sc-chips" role="group" aria-label="Portée">
        {SCOPE_CHIPS.map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.scope === v} onClick={() => set({scope: v})}>{l}</button>)}
      </div>
      <div className="sc-filters sc-hide-phone">
        <FilterFields f={f} roles={roles} token={token} set={set}/>
      </div>
      <button type="button" className="sc-btn sc-btn-ghost sc-only-phone sc-filter-btn" onClick={() => setFiltersOpen(true)}>
        <NavGlyph g="sliders" size={16}/>Filtrer{extraFilters ? <b className="sc-dot" aria-label="filtre actif"/> : null}</button>
    </div>

    <div ref={listTop} className="sc-summary" role="status" aria-live="polite">
      {data ? <span><b>{data.total.toLocaleString('fr-FR')}</b> compte{data.total > 1 ? 's' : ''}{f.activeOnly ? ' avec un accès école actif' : ''}{filtered && !f.activeOnly ? ' correspondant' + (data.total > 1 ? 's' : '') : ''}</span>
        : <i className="sc-skel sc-skel-line" aria-hidden="true"/>}
      {f.activeOnly && <button type="button" className="sc-chip-clear" onClick={() => set({activeOnly: false})}>Accès actifs ×</button>}
      {f.schoolId && <button type="button" className="sc-chip-clear" onClick={() => set({schoolId: '', schoolName: ''})}>{f.schoolName || 'École'} ×</button>}
      {filtered && <button type="button" className="sc-link" onClick={() => { setQInput(''); set({...EMPTY}); }}>Réinitialiser les filtres</button>}
    </div>

    {error ? <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Impossible de charger les utilisateurs.</b><small>{error}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setReloadKey(k => k + 1)}>Réessayer</button></div>
      : !data && loading ? <Skeleton/>
      : rows.length === 0 ? <Empty f={f} filtered={filtered}/>
      : <div className={`sc-list ${loading ? 'sc-busy' : ''}`} role="table" aria-label="Utilisateurs et accès" aria-busy={loading}>
        <div className="sc-row id-row sc-row-head" role="row"><span role="columnheader">Utilisateur</span><span role="columnheader">Portée</span>
          <span role="columnheader">Rôle(s)</span><span role="columnheader" className="id-col-school">École</span><span role="columnheader">Statut</span>
          <span role="columnheader" className="id-col-seen">Dernière activité</span><span role="columnheader"><span className="es-sr">Ouvrir</span></span></div>
        {rows.map(u => {
          const roleList = [...u.platform_roles, ...u.school_roles];
          return <div key={u.id} className="sc-row id-row" role="row" tabIndex={0} aria-label={`${u.full_name}, ${SCOPE_LABEL[u.scope]}, ${IDENTITY_STATUS_LABEL[u.status]}. Ouvrir le détail`}
            onClick={() => open(u.id)} onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); open(u.id); } }}>
            <span role="cell" className="id-col-user"><span className="id-avatar" aria-hidden="true">{initials(u.full_name)}</span><span><b>{u.full_name}</b><small>{u.email}</small></span></span>
            <span role="cell" className="id-col-scope"><ScopeBadge scope={u.scope}/></span>
            <span role="cell" className="id-col-roles">{roleList.length ? <><b>{roleList[0]}</b>{roleList.length > 1 && <small> +{roleList.length - 1}</small>}</> : <small className="sc-muted">Aucun rôle actif</small>}</span>
            <span role="cell" className="id-col-school">{u.first_school_name ? <><b>{u.first_school_name}</b>{u.schools_count > 1 ? <small>+{u.schools_count - 1} autre{u.schools_count > 2 ? 's' : ''}</small> : <small>{u.first_school_code}</small>}</> : <span className="sc-muted" aria-label="Aucune école">—</span>}</span>
            <span role="cell" className="id-col-status"><IdentityStatusBadge status={u.status}/></span>
            <span role="cell" className="id-col-seen"><small title={fullDate(u.last_activity_at) || undefined}>{ago(u.last_activity_at)}</small></span>
            <span role="cell" className="id-col-chev" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span>
          </div>;
        })}
      </div>}

    {data && rows.length > 0 && <>
      <nav className="sc-pager sc-hide-phone" aria-label="Pagination">
        <span>{((page - 1) * LIMIT + 1).toLocaleString('fr-FR')}–{Math.min(page * LIMIT, data.total).toLocaleString('fr-FR')} sur {data.total.toLocaleString('fr-FR')}</span>
        <div>
          <button type="button" className="sc-btn sc-btn-ghost" disabled={page <= 1 || loading} onClick={() => goPage(page - 1)}><NavGlyph g="chevronLeft" size={16}/>Précédent</button>
          <span className="sc-page" aria-current="page">Page {page} sur {totalPages}</span>
          <button type="button" className="sc-btn sc-btn-ghost" disabled={!data.has_more || loading} onClick={() => goPage(page + 1)}>Suivant<NavGlyph g="chevronRight" size={16}/></button>
        </div>
      </nav>
      {moreOnPhone && <button type="button" className="sc-btn sc-more sc-only-phone" disabled={loading} onClick={() => void loadMore()}>{loading ? 'Chargement…' : `Charger la suite (${Math.max(0, data.total - rows.length - (page - 1) * LIMIT).toLocaleString('fr-FR')} restants)`}</button>}
    </>}

    {filtersOpen && <div className="sc-fsheet-backdrop mobileSheetBackdrop" onMouseDown={e => e.currentTarget === e.target && setFiltersOpen(false)}>
      <div className="sc-fsheet" role="dialog" aria-modal="true" aria-label="Filtrer les utilisateurs">
        <div className="sc-fsheet-head mobileSheetHead"><b>Filtrer</b><button type="button" aria-label="Fermer" onClick={() => setFiltersOpen(false)}><NavGlyph g="close" size={18}/></button></div>
        <fieldset><legend>Statut</legend><div className="sc-chips sc-chips-wrap">{STATUSES.map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.status === v} onClick={() => set({status: v})}>{l}</button>)}</div></fieldset>
        <div className="id-sheet-fields"><FilterFields f={f} roles={roles} token={token} set={set} withoutStatus/></div>
        <button type="button" className="sc-btn sc-btn-primary sc-block" onClick={() => setFiltersOpen(false)}>Voir {data ? data.total.toLocaleString('fr-FR') : ''} compte(s)</button>
      </div></div>}
  </div>;
}

function FilterFields({f, roles, token, set, withoutStatus}: {f: IdentityFilters; roles: FilterRole[]; token: string; set: (p: Partial<IdentityFilters>) => void; withoutStatus?: boolean}) {
  return <>
    {!withoutStatus && <label className="sc-select"><span>Statut</span>
      <select value={f.status} onChange={e => set({status: e.target.value as IdentityFilters['status']})}>{STATUSES.map(([v, l]) => <option key={l} value={v}>{l}</option>)}</select></label>}
    <label className="sc-select"><span>Rôle</span>
      <select value={f.role} onChange={e => set({role: e.target.value})}>
        <option value="">Tous</option>
        {(['PLATFORM', 'SCHOOL'] as const).map(level => <optgroup key={level} label={level === 'PLATFORM' ? 'Plateforme' : 'École'}>
          {roles.filter(r => r.level === level).map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</optgroup>)}
      </select></label>
    <SchoolPicker token={token} value={f.schoolId ? {id: f.schoolId, name: f.schoolName} : null} onChange={s => set({schoolId: s?.id || '', schoolName: s?.name || ''})}/>
  </>;
}

/** École filter: server-side suggestions from the schools directory (never the whole list in the browser). */
function SchoolPicker({token, value, onChange}: {token: string; value: {id: string; name: string} | null; onChange: (s: {id: string; name: string} | null) => void}) {
  const [q, setQ] = useState('');
  const [items, setItems] = useState<{id: string; name: string; code: string}[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const ctl = new AbortController();
    const t = window.setTimeout(() => {
      fetchSchools(token, {q, status: '', config: '', sort: 'name'}, null, 8, ctl.signal).then(r => setItems(r.items.map(s => ({id: s.id, name: s.name, code: s.code})))).catch(() => undefined);
    }, 300);
    return () => { window.clearTimeout(t); ctl.abort(); };
  }, [q, open]);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener('mousedown', down); return () => window.removeEventListener('mousedown', down);
  }, [open]);
  if (value) return <div className="sc-select id-school-picked"><span>École</span><b title={value.name}>{value.name}</b>
    <button type="button" className="sc-clear" aria-label="Retirer le filtre école" onClick={() => onChange(null)}><NavGlyph g="close" size={14}/></button></div>;
  return <div className="sc-select id-school-picker" ref={box}><span>École</span>
    <input type="search" value={q} placeholder="Toutes" aria-label="Filtrer par école" role="combobox" aria-expanded={open} aria-autocomplete="list"
      onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true); }} onKeyDown={e => { if (e.key === 'Escape') setOpen(false); }} maxLength={80}/>
    {open && items.length > 0 && <div className="sc-menu-pop id-school-pop" role="listbox">
      {items.map(s => <button key={s.id} type="button" role="option" aria-selected={false} onClick={() => { onChange({id: s.id, name: s.name}); setOpen(false); setQ(''); }}>
        <b>{s.name}</b><small>{s.code}</small></button>)}</div>}
  </div>;
}

function Skeleton() {
  return <div className="sc-list" aria-busy="true" aria-label="Chargement des utilisateurs">{Array.from({length: 6}).map((_, i) => <div key={i} className="sc-row id-row sc-row-skel">
    <span className="id-col-user"><i className="sc-skel" style={{width: 32, height: 32, borderRadius: 99}}/><span><i className="sc-skel" style={{width: '70%'}}/><i className="sc-skel" style={{width: '50%'}}/></span></span>
    <span><i className="sc-skel" style={{width: 80}}/></span><span><i className="sc-skel" style={{width: '70%'}}/></span><span className="id-col-school"><i className="sc-skel" style={{width: '60%'}}/></span>
    <span><i className="sc-skel" style={{width: 64}}/></span><span className="id-col-seen"><i className="sc-skel" style={{width: 70}}/></span><span/>
  </div>)}</div>;
}

function Empty({f, filtered}: {f: IdentityFilters; filtered: boolean}) {
  if (f.q.trim()) return <div className="sc-empty"><NavGlyph g="search" size={24}/><b>Aucun résultat pour « {f.q.trim()} ».</b><small>Vérifiez l’orthographe, ou cherchez par adresse e-mail.</small></div>;
  if (filtered) return <div className="sc-empty"><NavGlyph g="users" size={24}/><b>Aucun compte ne correspond à ces filtres.</b><small>Modifiez les filtres pour élargir la liste.</small></div>;
  return <div className="sc-empty"><NavGlyph g="users" size={24}/><b>Aucun utilisateur pour le moment.</b><small>Les comptes apparaîtront ici dès leur création (équipe plateforme ou écoles).</small></div>;
}

/* ---------------------------------------------------------------- read-only detail */
function IdentityView({token, id, has, onBack, onOpenSchool, onOpenTeam}: {token: string; id: string; has: (c: string) => boolean; onBack: () => void;
  onOpenSchool: (schoolId: string) => void; onOpenTeam: (target: TeamTarget) => void}) {
  const [d, setD] = useState<IdentityDetail | null>(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const title = useRef<HTMLHeadingElement>(null); const focusedFor = useRef('');
  useEffect(() => {
    const ctl = new AbortController(); setError('');
    fetchIdentity(token, id, ctl.signal).then(setD).catch(e => { if (!ctl.signal.aborted) setError(e instanceof UserFacingError ? e.message : friendlyError(e)); });
    return () => ctl.abort();
  }, [token, id, nonce]);
  useEffect(() => { if (d && focusedFor.current !== id) { focusedFor.current = id; title.current?.focus({preventScroll: true}); } }, [d, id]);
  const backBtn = <button type="button" className="sc-back" onClick={onBack}><NavGlyph g="chevronLeft" size={18}/>Utilisateurs & accès</button>;
  if (error) return <div className="sc-sheet-page">{backBtn}<div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Détail indisponible.</b><small>{error}</small></div>
    <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setNonce(n => n + 1)}>Réessayer</button></div></div>;
  if (!d) return <div className="sc-sheet-page" aria-busy="true">{backBtn}<div className="sc-card"><i className="sc-skel" style={{width: '50%', height: 22}}/><i className="sc-skel" style={{width: '30%'}}/></div></div>;
  const activeSchools = d.memberships.filter(m => m.active);
  const platformMember = d.platform_roles.length > 0;
  return <div className="sc-sheet-page">
    {backBtn}
    <header className="sc-card sc-sheet-head">
      <div className="sc-sheet-id">
        <span className="sc-sheet-logo id-logo" aria-hidden="true">{initials(d.full_name)}</span>
        <div><h2 ref={title} tabIndex={-1}>{d.full_name}</h2><p>{d.email}</p>
          <div className="sc-badges"><ScopeBadge scope={d.scope}/><IdentityStatusBadge status={d.status}/></div></div>
      </div>
      <p className="sc-muted sc-noaction">Consultation. Les modifications se font là où chaque accès est géré.</p>
    </header>

    <section className="sc-summary-grid id-summary" aria-label="Synthèse">
      <div className="sc-stat"><small>Portée</small><b>{SCOPE_LABEL[d.scope]}</b><em>{platformMember ? `${d.platform_roles.length} rôle(s) plateforme` : 'Aucun rôle plateforme'}</em></div>
      <div className={`sc-stat ${d.status === 'ACTIVE' ? 'sc-ok' : 'sc-warn'}`}><small>Statut</small><b>{IDENTITY_STATUS_LABEL[d.status]}</b><em>{d.active ? 'Compte actif' : 'Compte désactivé'}</em></div>
      <div className="sc-stat"><small>Écoles</small><b>{activeSchools.length}</b><em>{d.memberships.length - activeSchools.length ? `${d.memberships.length - activeSchools.length} rattachement(s) inactif(s)` : activeSchools.length ? 'Rattachement(s) actif(s)' : 'Aucun rattachement école'}</em></div>
      <div className="sc-stat"><small>Dernière activité</small><b>{ago(d.last_activity_at)}</b><em>Session plateforme ou école</em></div>
    </section>

    <div className="sc-sheet-grid">
      <section className="sc-card"><h3>Identité</h3>
        <dl className="sc-dl"><dt>Nom</dt><dd>{d.full_name}</dd><dt>E-mail</dt><dd>{d.email}</dd><dt>Compte créé le</dt><dd>{fullDate(d.created_at)}</dd>
          <dt>Dernière activité</dt><dd>{fullDate(d.last_activity_at) || 'Jamais connecté'}</dd></dl></section>
      <section className="sc-card"><div className="sc-card-head"><h3>Accès plateforme</h3>
          {platformMember && has('platform.collaborators.manage') && <button type="button" className="sc-link" onClick={() => onOpenTeam({openMember: d.id})}>Gérer dans Équipe plateforme</button>}</div>
        {platformMember ? <ul className="id-roles">{d.platform_roles.map(r => <li key={r.code}><b>{r.label}</b>{r.since && <small>depuis le {new Date(r.since).toLocaleDateString('fr-FR')}</small>}</li>)}</ul>
          : <p className="sc-muted">Aucun rôle plateforme : ce compte n’accède qu’aux espaces école.</p>}
        {!platformMember && d.active && has('platform.collaborators.manage') && <button type="button" className="sc-btn sc-btn-ghost"
          onClick={() => onOpenTeam({addExisting: {id: d.id, full_name: d.full_name, email: d.email}})}><NavGlyph g="users" size={16}/>Ajouter à l’équipe plateforme</button>}
      </section>
    </div>

    <section className="sc-card"><h3>Rattachements école</h3>
      {d.memberships.length === 0 ? <p className="sc-muted">Aucun rattachement école : compte de la plateforme uniquement.</p>
        : <ul className="id-memberships">{d.memberships.map(m => <li key={m.school_id} className={m.active ? '' : 'id-inactive'}>
          <div><b>{m.name}</b><small>{m.code} · {m.active ? 'Rattachement actif' : 'Rattachement désactivé'}{m.school_status !== 'ACTIVE' ? ` · école ${m.school_status === 'SUSPENDED' ? 'suspendue' : 'désactivée'}` : ''}</small>
            <small>{m.roles.length ? m.roles.join(' · ') : 'Aucun rôle actif'} — dernière activité : {ago(m.last_activity_at).toLowerCase()}</small></div>
          {has('platform.schools.read') && <button type="button" className="sc-btn sc-btn-ghost" onClick={() => onOpenSchool(m.school_id)}>Fiche école</button>}
        </li>)}</ul>}
      <p className="sc-hint">Les rôles métier (caissier, préfet, enseignant…) se gèrent dans l’espace de chaque école ; l’administrateur de l’école depuis sa fiche.</p>
    </section>

    {d.security && <section className="sc-card"><h3>Sécurité</h3>
      <dl className="sc-dl"><dt>Validation en deux étapes</dt><dd>{d.security.mfa_enrolled ? 'Activée' : 'Non activée'}</dd>
        <dt>Sessions ouvertes</dt><dd>{d.security.open_sessions}</dd>
        <dt>Première connexion</dt><dd>{d.must_change_password ? 'Mot de passe provisoire à remplacer' : 'Effectuée'}</dd></dl></section>}

  </div>;
}
