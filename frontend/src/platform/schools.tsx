import React, {useCallback, useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {NavGlyph} from './nav_icons';
import {friendlyError, UserFacingError} from './errors';
import {CONFIG_LABEL, downloadSchoolsCsv, fetchSchools, STATUS_LABEL, type ConfigState, type SchoolFilters, type SchoolRow, type SchoolsPage, type SchoolStatus} from './schools_api';
import {SchoolSheetView, SchoolFormDialog, AdminDialog, StatusDialog, type SchoolAction} from './school_sheet';
import './schools.css';

/* Module Écoles (plateforme), lot 2026-10. Server-side instant search (debounced, previous request cancelled), status
   chips (the three real statuses), a separate configuration filter, server sorts, keyset pagination (pages on desktop,
   "Charger la suite" on phones), clickable rows, contextual actions from capabilities and the real status.
   The view state lives in the URL (?q=&status=&config=&sort=&page= ; ?school=<id> for a sheet). */

export type SchoolsPreset = {status?: string; filter?: 'needs_admin'; openId?: string; nonce: number};
type Props = {token: string; has: (cap: string) => boolean; preset?: SchoolsPreset | null; active: boolean; onChanged: () => void};

const LIMIT = 25;
const phone = () => typeof window !== 'undefined' && window.matchMedia('(max-width:767.98px)').matches;
const STATUS_CHIPS: ['' | SchoolStatus, string][] = [['', 'Toutes'], ['ACTIVE', 'Actives'], ['SUSPENDED', 'Suspendues'], ['DISABLED', 'Désactivées']];
const SORTS: [SchoolFilters['sort'], string][] = [['name', 'Nom (A → Z)'], ['created', 'Plus récentes'], ['status', 'Statut']];
const CONFIGS: ['' | ConfigState, string][] = [['', 'Toutes'], ['COMPLETE', 'Complète'], ['INCOMPLETE', 'À finaliser'], ['ADMIN_PENDING', 'Activation en attente'], ['ADMIN_MISSING', 'Administrateur à créer']];

function readUrl(): {f: SchoolFilters; page: number; school: string | null} {
  const p = new URLSearchParams(window.location.search);
  const st = p.get('status'); const cf = p.get('config'); const so = p.get('sort');
  return {
    f: {q: (p.get('q') || '').slice(0, 80), status: (['ACTIVE', 'SUSPENDED', 'DISABLED'].includes(st || '') ? st : '') as SchoolFilters['status'],
      config: (['COMPLETE', 'INCOMPLETE', 'ADMIN_PENDING', 'ADMIN_MISSING'].includes(cf || '') ? cf : '') as SchoolFilters['config'],
      sort: (['name', 'created', 'status'].includes(so || '') ? so : 'name') as SchoolFilters['sort'], needsAdmin: p.get('needs_admin') === '1'},
    page: Math.max(1, Number(p.get('page') || 1) || 1), school: p.get('school'),
  };
}

function writeUrl(f: SchoolFilters, page: number, school: string | null, push = false) {
  const p = new URLSearchParams();
  if (school) p.set('school', school);
  else {
    if (f.q.trim()) p.set('q', f.q.trim()); if (f.status) p.set('status', f.status); if (f.config) p.set('config', f.config);
    if (f.sort !== 'name') p.set('sort', f.sort); if (f.needsAdmin) p.set('needs_admin', '1'); if (page > 1) p.set('page', String(page));
  }
  const url = `${window.location.pathname}${p.toString() ? `?${p}` : ''}`;
  const state = {...(history.state || {}), edusyncScope: 'platform', edusyncScreen: 'schools', school: school || undefined};
  if (push) history.pushState(state, '', url); else history.replaceState(state, '', url);
}

export function StatusBadge({status}: {status: SchoolStatus}) {
  return <span className={`sc-badge sc-st-${status.toLowerCase()}`}><i aria-hidden="true"/>{STATUS_LABEL[status]}</span>;
}
export function ConfigBadge({state}: {state: ConfigState}) {
  return <span className={`sc-config sc-cf-${state.toLowerCase()}`}>{CONFIG_LABEL[state]}</span>;
}

export function SchoolsModule({token, has, preset, active, onChanged}: Props) {
  const initial = useRef(readUrl());
  const [f, setF] = useState<SchoolFilters>(initial.current.f);
  const [qInput, setQInput] = useState(initial.current.f.q);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SchoolsPage | null>(null);
  const [extra, setExtra] = useState<SchoolRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openSchool, setOpenSchool] = useState<string | null>(initial.current.school);
  const [searchOpen, setSearchOpen] = useState(Boolean(initial.current.f.q));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [action, setAction] = useState<SchoolAction | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const listTop = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const reqId = useRef(0);

  // Dashboard → filtered list (one source of truth with the indicator that was clicked).
  useEffect(() => {
    if (!preset) return;
    if (preset.openId) { setOpenSchool(preset.openId); writeUrl(f, page, preset.openId, true); return; }
    const next: SchoolFilters = {q: '', status: (preset.status || '') as SchoolFilters['status'], config: '', sort: 'name', needsAdmin: preset.filter === 'needs_admin'};
    setQInput(''); setF(next); setCursors([null]); setPage(1); setOpenSchool(null); setExtra([]);
  }, [preset?.nonce]);

  // Debounced instant search: 300 ms after the last key, the server is asked; an older answer is ignored.
  useEffect(() => {
    if (qInput === f.q) return;
    const t = window.setTimeout(() => { setF(x => ({...x, q: qInput})); setCursors([null]); setPage(1); setExtra([]); }, 300);
    return () => window.clearTimeout(t);
  }, [qInput]);

  const load = useCallback(() => {
    const id = ++reqId.current; const ctl = new AbortController();
    setLoading(true); setError('');
    fetchSchools(token, f, cursors[page - 1] ?? null, LIMIT, ctl.signal)
      .then(r => { if (id !== reqId.current) return; setData(r); setExtra([]); if (r.next_cursor) setCursors(c => { const n = c.slice(0, page); n[page] = r.next_cursor; return n; }); })
      .catch(e => { if (ctl.signal.aborted || id !== reqId.current) return; console.warn('[edusync] liste des écoles en échec'); setError(e instanceof UserFacingError ? e.message : friendlyError(e)); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
    return ctl;
  }, [token, f, page, reloadKey]);
  useEffect(() => { if (!active) return; const ctl = load(); return () => ctl.abort(); }, [load, active]);
  useEffect(() => { if (active) writeUrl(f, page, openSchool); }, [f, page, openSchool, active]);
  // Browser / Android back from a sheet returns to the list with its filters.
  useEffect(() => {
    const h = () => { const u = readUrl(); setOpenSchool(u.school); };
    window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h);
  }, []);

  const set = (patch: Partial<SchoolFilters>) => { setF(x => ({...x, ...patch, needsAdmin: false})); setCursors([null]); setPage(1); setExtra([]); };
  const open = (id: string) => { setOpenSchool(id); writeUrl(f, page, id, true); window.scrollTo(0, 0); };
  const back = () => { if (history.state?.school) history.back(); else { setOpenSchool(null); writeUrl(f, page, null); } };
  const goPage = (n: number) => { setPage(n); listTop.current?.scrollIntoView({block: 'start'}); };
  async function loadMore() {
    const cursor = extra.length ? moreCursor.current : data?.next_cursor;
    if (!cursor) return;
    try { setLoading(true); const r = await fetchSchools(token, f, cursor, LIMIT); moreCursor.current = r.next_cursor; setExtra(x => [...x, ...r.items]); setHasMore(r.has_more); }
    catch (e) { setError(e instanceof UserFacingError ? e.message : friendlyError(e)); } finally { setLoading(false); }
  }
  const moreCursor = useRef<string | null>(null);
  const [hasMore, setHasMore] = useState<boolean | null>(null);
  useEffect(() => { moreCursor.current = null; setHasMore(null); }, [data]);
  const changed = () => { setReloadKey(k => k + 1); onChanged(); };
  async function exportCsv() { try { await downloadSchoolsCsv(token, f); toast.success('Export téléchargé'); } catch (e) { toast.error(e instanceof UserFacingError ? e.message : friendlyError(e)); } }

  if (openSchool) return <>
    <SchoolSheetView token={token} id={openSchool} has={has} onBack={back} onChanged={changed}/>
  </>;

  const rows = [...(data?.items || []), ...extra];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / LIMIT)) : 1;
  const filtered = Boolean(f.q.trim() || f.status || f.config || f.needsAdmin);
  const moreOnPhone = hasMore ?? data?.has_more;
  return <div className="sc">
    <header className="sc-head">
      <div><h2>Écoles</h2><p>Pilotage et administration des écoles de la plateforme EduSync</p></div>
      <div className="sc-head-actions">
        <button type="button" className="sc-icon-btn sc-only-phone" aria-label="Rechercher une école" aria-expanded={searchOpen} onClick={() => { const open = !searchOpen; setSearchOpen(open); if (open) window.setTimeout(() => searchInput.current?.focus(), 0); }}><NavGlyph g="search" size={18}/></button>
        <button type="button" className="sc-btn sc-btn-ghost sc-hide-phone" onClick={() => void exportCsv()} disabled={!data || data.total === 0}><NavGlyph g="download" size={16}/>Exporter</button>
        {has('platform.schools.create') && <button type="button" className="sc-btn sc-btn-primary" onClick={() => setCreating(true)}><NavGlyph g="plus" size={16}/><span>Nouvelle école</span></button>}
      </div>
    </header>

    <div className={`sc-toolbar ${searchOpen ? 'sc-search-open' : ''}`}>
      <label className="sc-search">
        <NavGlyph g="search" size={17}/>
        <input ref={searchInput} type="search" value={qInput} onChange={e => setQInput(e.target.value)} placeholder="Nom de l’école, code EduSync ou promoteur" aria-label="Rechercher une école" maxLength={80}/>
        {loading && qInput !== '' && <i className="sc-spin" aria-hidden="true"/>}
        {qInput && <button type="button" className="sc-clear" aria-label="Effacer la recherche" onClick={() => setQInput('')}><NavGlyph g="close" size={15}/></button>}
      </label>
      <div className="sc-chips" role="group" aria-label="Statut">
        {STATUS_CHIPS.map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.status === v && !f.needsAdmin} onClick={() => set({status: v})}>{l}</button>)}
      </div>
      <div className="sc-filters sc-hide-phone">
        <label className="sc-select"><span>Configuration</span>
          <select value={f.config} onChange={e => set({config: e.target.value as SchoolFilters['config']})}>{CONFIGS.map(([v, l]) => <option key={l} value={v}>{l}</option>)}</select></label>
        <label className="sc-select"><span>Trier</span>
          <select value={f.sort} onChange={e => set({sort: e.target.value as SchoolFilters['sort']})}>{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      </div>
      <button type="button" className="sc-btn sc-btn-ghost sc-only-phone sc-filter-btn" onClick={() => setFiltersOpen(true)}>
        <NavGlyph g="sliders" size={16}/>Filtrer{(f.config || f.sort !== 'name') ? <b className="sc-dot" aria-label="filtre actif"/> : null}</button>
    </div>

    <div ref={listTop} className="sc-summary" role="status" aria-live="polite">
      {data ? <span><b>{data.total.toLocaleString('fr-FR')}</b> école{data.total > 1 ? 's' : ''}{f.needsAdmin ? ' actives sans administrateur' : ''}{filtered ? ' correspondante' + (data.total > 1 ? 's' : '') : ''}</span>
        : <i className="sc-skel sc-skel-line" aria-hidden="true"/>}
      {f.needsAdmin && <button type="button" className="sc-chip-clear" onClick={() => set({})}>Sans administrateur ×</button>}
      {filtered && <button type="button" className="sc-link" onClick={() => { setQInput(''); set({q: '', status: '', config: ''}); }}>Réinitialiser les filtres</button>}
    </div>

    {error ? <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Impossible de charger les écoles.</b><small>{error}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setReloadKey(k => k + 1)}>Réessayer</button></div>
      : !data && loading ? <SkeletonList/>
      : rows.length === 0 ? <EmptyState f={f} filtered={filtered} canCreate={has('platform.schools.create')} onCreate={() => setCreating(true)}/>
      : <div className={`sc-list ${loading ? 'sc-busy' : ''}`} role="table" aria-label="Liste des écoles" aria-busy={loading}>
        <div className="sc-row sc-row-head" role="row"><span role="columnheader">École</span><span role="columnheader" className="sc-col-contact">Promoteur / contact</span>
          <span role="columnheader">Statut</span><span role="columnheader">Configuration</span><span role="columnheader" className="sc-col-users">Utilisateurs</span><span role="columnheader" className="sc-col-actions"><span className="es-sr">Actions</span></span></div>
        {rows.map(s => <div key={s.id} className="sc-row" role="row" tabIndex={0} aria-label={`${s.name}, ${s.code}, statut ${STATUS_LABEL[s.status]}, ${CONFIG_LABEL[s.config_state]}. Ouvrir la fiche`}
          onClick={() => open(s.id)} onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); open(s.id); } }}>
          <span role="cell" className="sc-col-school"><b>{s.name}</b><small>{s.code}{s.city || s.province ? ` · ${[s.city, s.province].filter(Boolean).join(', ')}` : ''}</small></span>
          <span role="cell" className="sc-col-contact">{s.contact_name ? <><b>{s.contact_name}</b><small>{s.contact_phone_display || '—'}</small></> : <small className="sc-muted">Non renseigné</small>}</span>
          <span role="cell"><StatusBadge status={s.status}/></span>
          <span role="cell"><ConfigBadge state={s.config_state}/></span>
          <span role="cell" className="sc-col-users"><b>{s.users_count}</b><small className="sc-only-phone"> utilisateur{s.users_count > 1 ? 's' : ''}</small></span>
          <span role="cell" className="sc-col-actions"><RowMenu school={s} has={has} onOpen={() => open(s.id)} onAction={setAction}/>
            <span className="sc-chev sc-only-phone" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span></span>
        </div>)}
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
      {moreOnPhone && <button type="button" className="sc-btn sc-more sc-only-phone" disabled={loading} onClick={() => void loadMore()}>{loading ? 'Chargement…' : `Charger la suite (${Math.max(0, data.total - rows.length - (page - 1) * LIMIT).toLocaleString('fr-FR')} restantes)`}</button>}
    </>}

    {filtersOpen && <div className="sc-fsheet-backdrop mobileSheetBackdrop" onMouseDown={e => e.currentTarget === e.target && setFiltersOpen(false)}>
      <div className="sc-fsheet" role="dialog" aria-modal="true" aria-label="Filtrer les écoles">
        <div className="sc-fsheet-head mobileSheetHead"><b>Filtrer</b><button type="button" aria-label="Fermer" onClick={() => setFiltersOpen(false)}><NavGlyph g="close" size={18}/></button></div>
        <fieldset><legend>Configuration</legend><div className="sc-chips sc-chips-wrap">{CONFIGS.map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.config === v} onClick={() => set({config: v})}>{l}</button>)}</div></fieldset>
        <fieldset><legend>Trier par</legend><div className="sc-chips sc-chips-wrap">{SORTS.map(([v, l]) => <button key={v} type="button" className="sc-chip" aria-pressed={f.sort === v} onClick={() => set({sort: v})}>{l}</button>)}</div></fieldset>
        <button type="button" className="sc-btn sc-btn-primary sc-block" onClick={() => setFiltersOpen(false)}>Voir {data ? data.total.toLocaleString('fr-FR') : ''} école(s)</button>
      </div></div>}
    {creating && <SchoolFormDialog token={token} has={has} onClose={() => setCreating(false)} onCreated={id => { changed(); setCreating(false); open(id); }}/>}
    {action?.kind === 'admin' && <AdminDialog token={token} school={action.school} onClose={() => setAction(null)} onDone={() => { setAction(null); changed(); }}/>}
    {(action?.kind === 'suspend' || action?.kind === 'reactivate') && <StatusDialog token={token} kind={action.kind} school={action.school} onClose={() => setAction(null)} onDone={() => { setAction(null); changed(); }}/>}
  </div>;
}

function RowMenu({school, has, onOpen, onAction}: {school: SchoolRow; has: (c: string) => boolean; onOpen: () => void; onAction: (a: SchoolAction) => void}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', down); window.addEventListener('keydown', key);
    ref.current?.querySelector<HTMLElement>('[role=menuitem]')?.focus();
    return () => { window.removeEventListener('mousedown', down); window.removeEventListener('keydown', key); };
  }, [open]);
  const items = [
    {key: 'open', label: 'Ouvrir la fiche', icon: 'external', go: onOpen},
    school.status !== 'DISABLED' && has('platform.school_admin.bootstrap') && {key: 'admin', label: school.has_admin ? 'Ajouter un administrateur' : 'Créer l’administrateur initial', icon: 'key', go: () => onAction({kind: 'admin', school})},
    school.status === 'ACTIVE' && has('platform.schools.suspend') && {key: 'suspend', label: 'Suspendre l’école', icon: 'alert', danger: true, go: () => onAction({kind: 'suspend', school})},
    school.status === 'SUSPENDED' && has('platform.schools.activate') && {key: 'reactivate', label: 'Réactiver l’école', icon: 'checkCircle', go: () => onAction({kind: 'reactivate', school})},
  ].filter(Boolean) as {key: string; label: string; icon: string; danger?: boolean; go: () => void}[];
  return <div className="sc-menu" ref={ref} onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
    <button type="button" className="sc-icon-btn sc-dots" aria-label={`Actions pour ${school.name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(x => !x)}><NavGlyph g="more" size={18}/></button>
    {open && <div className="sc-menu-pop" role="menu">{items.map(i => <button key={i.key} type="button" role="menuitem" className={i.danger ? 'sc-danger' : ''} onClick={() => { setOpen(false); i.go(); }}>
      <NavGlyph g={i.icon} size={16}/>{i.label}</button>)}</div>}
  </div>;
}

function SkeletonList() {
  return <div className="sc-list" aria-busy="true" aria-label="Chargement des écoles">{Array.from({length: 6}).map((_, i) => <div key={i} className="sc-row sc-row-skel">
    <span><i className="sc-skel" style={{width: '62%'}}/><i className="sc-skel" style={{width: '38%'}}/></span><span className="sc-col-contact"><i className="sc-skel" style={{width: '70%'}}/></span>
    <span><i className="sc-skel" style={{width: 64}}/></span><span><i className="sc-skel" style={{width: 110}}/></span><span className="sc-col-users"><i className="sc-skel" style={{width: 24}}/></span><span/>
  </div>)}</div>;
}

function EmptyState({f, filtered, canCreate, onCreate}: {f: SchoolFilters; filtered: boolean; canCreate: boolean; onCreate: () => void}) {
  const statusText = f.status === 'ACTIVE' ? 'Aucune école active.' : f.status === 'SUSPENDED' ? 'Aucune école suspendue.' : f.status === 'DISABLED' ? 'Aucune école désactivée.' : null;
  if (f.q.trim()) return <div className="sc-empty"><NavGlyph g="search" size={24}/><b>Aucun résultat pour « {f.q.trim()} ».</b><small>Vérifiez l’orthographe ou cherchez par code EduSync (EDS-…) ou par nom du promoteur.</small></div>;
  if (filtered) return <div className="sc-empty"><NavGlyph g="school" size={24}/><b>{statusText || 'Aucune école ne correspond à ces filtres.'}</b><small>Modifiez les filtres pour élargir la liste.</small></div>;
  return <div className="sc-empty"><NavGlyph g="school" size={24}/><b>Aucune école créée pour le moment.</b>
    {canCreate ? <button type="button" className="sc-btn sc-btn-primary" onClick={onCreate}><NavGlyph g="plus" size={16}/>Créer la première école</button> : <small>Les écoles apparaîtront ici dès leur création.</small>}</div>;
}
