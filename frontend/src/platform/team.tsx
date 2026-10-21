import {OnlineActionButton} from './online_action';
import {PageTrail} from './navigation';
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {toast} from 'sonner';
import {teamCapabilities, teamRoles, type PlatformCapability, type PlatformRole} from '../api';
import {Modal} from './account';
import {friendlyError, UserFacingError} from './errors';
import {auditActionLabel} from './labels';
import {NavGlyph} from './nav_icons';
import {
  addExisting, assignRole, cloneRole, createMember, createRole, fetchCandidates, fetchMember, fetchMembers, grantCapability, MEMBER_STATUS_LABEL,
  removeAccess, resendInvitation, resetMfa, resetPassword, revokeCapability, revokeRole, revokeSessions, RISK_LABEL, roleStatus, setMemberStatus, updateRole,
  type Candidate, type MemberDetail, type MemberFilters, type MemberRow, type MembersPage, type MemberStatus,
} from './team_api';
import './schools.css';
import './team.css';

/* Équipe plateforme (Plateforme EduSync), lot 2026-10. Two views: Comptes (members, instant server-side search, filters,
   keyset pagination) and Rôles (standard roles: read-only, can be cloned; custom roles: create, edit with a diff and
   the members affected, activate, archive). The member sheet shows where every capability comes from (role or
   individual grant), the supplementary capabilities, the non-delegable ones, security and history. Every sensitive
   action asks for a reason and shows its effect before confirmation; the server stays the source of truth. */

export type TeamPreset = {openMember?: string; addExisting?: {id: string; full_name: string; email: string}; nonce: number};
type Props = {token: string; preset?: TeamPreset | null; onChanged?: () => void};

const LIMIT = 25;
const STATUS_CHIPS: [MemberFilters['status'], string][] = [['', 'Tous'], ['ACTIVE', 'Actifs'], ['PENDING', 'Activation en attente'], ['SUSPENDED', 'Suspendus']];
const ROLE_STATUS: Record<string, string> = {DRAFT: 'Brouillon', OWNER_APPROVED: 'Approuvé', ACTIVE: 'Actif', ARCHIVED: 'Archivé'};
const newKey = () => crypto.randomUUID();
const msg = (e: unknown) => e instanceof UserFacingError ? e.message : friendlyError(e);
const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
const fullDate = (iso: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'}) : '—';
function ago(iso: string | null) {
  if (!iso) return 'Jamais connecté';
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return 'À l’instant';
  if (mins < 60) return `Il y a ${mins} min`;
  if (mins < 60 * 24) return `Il y a ${Math.round(mins / 60)} h`;
  if (mins < 60 * 24 * 30) return `Il y a ${Math.round(mins / 1440)} j`;
  return new Date(iso).toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'});
}
function groupBy<T>(items: T[], key: (x: T) => string): [string, T[]][] {
  const m = new Map<string, T[]>(); items.forEach(x => m.set(key(x), [...(m.get(key(x)) || []), x])); return [...m.entries()];
}

export function MemberStatusBadge({status}: {status: MemberStatus}) {
  return <span className={`sc-badge tm-ms-${status.toLowerCase()}`}><i aria-hidden="true"/>{MEMBER_STATUS_LABEL[status]}</span>;
}

export function TeamPage({token, preset, onChanged}: Props) {
  const [tab, setTab] = useState<'users' | 'roles'>('users');
  const [roles, setRoles] = useState<PlatformRole[] | null>(null);
  const [caps, setCaps] = useState<PlatformCapability[]>([]);
  const [refsError, setRefsError] = useState('');
  const [openMember, setOpenMember] = useState<string | null>(() => new URLSearchParams(window.location.search).get('member'));
  const [adding, setAdding] = useState<null | {existing?: {id: string; full_name: string; email: string}}>(null);
  const [reload, setReload] = useState(0);
  const loadRefs = useCallback(async () => {
    try { setRefsError(''); const [r, c] = await Promise.all([teamRoles(token), teamCapabilities(token)]); setRoles(r.items); setCaps(c.items); }
    catch (e) { setRefsError(msg(e)); }
  }, [token]);
  useEffect(() => { void loadRefs(); }, [loadRefs]);
  useEffect(() => {
    if (!preset) return;
    if (preset.openMember) open(preset.openMember);
    if (preset.addExisting) { setTab('users'); setAdding({existing: preset.addExisting}); }
  }, [preset?.nonce]);
  useEffect(() => {
    const h = () => setOpenMember(new URLSearchParams(window.location.search).get('member'));
    window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h);
  }, []);
  function open(id: string) {
    setOpenMember(id);
    history.pushState({...(history.state || {}), edusyncScope: 'platform', edusyncScreen: 'team', member: id}, '', `${window.location.pathname}?member=${id}`);
    window.scrollTo(0, 0);
  }
  function back() { if (history.state?.member) history.back(); else { setOpenMember(null); history.replaceState(history.state, '', window.location.pathname); } }
  const changed = () => { setReload(k => k + 1); void loadRefs(); onChanged?.(); };
  const activeRoles = (roles || []).filter(r => r.status === 'ACTIVE');

  if (openMember) return <MemberSheet token={token} id={openMember} roles={activeRoles} caps={caps} onBack={back} onChanged={changed}/>;
  return <div className="sc tm">
    <header className="sc-head">
      <div><h2>Équipe plateforme</h2><p>Membres de la Plateforme EduSync, rôles et capacités</p></div>
      <div className="sc-head-actions">
        {tab === 'users'
          ? <OnlineActionButton type="button" className="sc-btn sc-btn-primary" onClick={() => setAdding({})} disabled={!activeRoles.length}><NavGlyph g="plus" size={16}/><span>Ajouter un membre</span></OnlineActionButton>
          : <RoleCreateButton token={token} caps={caps} onSaved={changed}/>}
      </div>
    </header>
    <div className="es-tabs tm-tabs" role="tablist" aria-label="Équipe plateforme">
      <button role="tab" aria-selected={tab === 'users'} className={tab === 'users' ? 'es-on' : ''} onClick={() => setTab('users')}><NavGlyph g="users" size={16}/>Comptes</button>
      <button role="tab" aria-selected={tab === 'roles'} className={tab === 'roles' ? 'es-on' : ''} onClick={() => setTab('roles')}><NavGlyph g="shield" size={16}/>Rôles{roles ? ` · ${roles.length}` : ''}</button>
    </div>
    {refsError && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Rôles et capacités indisponibles.</b><small>{refsError}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => void loadRefs()}>Réessayer</button></div>}
    {tab === 'users' ? <MembersView token={token} roles={roles || []} reload={reload} onOpen={open}/>
      : <RolesView token={token} roles={roles} caps={caps} onChanged={changed}/>}
    {adding && <AddMemberWizard token={token} roles={activeRoles} caps={caps} existing={adding.existing} onClose={() => setAdding(null)}
      onDone={id => { setAdding(null); changed(); open(id); }}/>}
  </div>;
}

/* ---------------------------------------------------------------- Comptes */
function MembersView({token, roles, reload, onOpen}: {token: string; roles: PlatformRole[]; reload: number; onOpen: (id: string) => void}) {
  const [f, setF] = useState<MemberFilters>({q: '', status: '', role: ''});
  const [qInput, setQInput] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<MembersPage | null>(null);
  const [extra, setExtra] = useState<MemberRow[]>([]);
  const [moreCursor, setMoreCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const reqId = useRef(0);
  const set = (patch: Partial<MemberFilters>) => { setF(x => ({...x, ...patch})); setCursors([null]); setPage(1); setExtra([]); };
  useEffect(() => { if (qInput === f.q) return; const t = window.setTimeout(() => set({q: qInput}), 300); return () => window.clearTimeout(t); }, [qInput]);
  useEffect(() => {
    const id = ++reqId.current; const ctl = new AbortController();
    setLoading(true); setError('');
    fetchMembers(token, f, cursors[page - 1] ?? null, LIMIT, ctl.signal)
      .then(r => { if (id !== reqId.current) return; setData(r); setExtra([]); setMoreCursor(undefined);
        if (r.next_cursor) setCursors(c => { const n = c.slice(0, page); n[page] = r.next_cursor; return n; }); })
      .catch(e => { if (!ctl.signal.aborted && id === reqId.current) setError(msg(e)); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
    return () => ctl.abort();
  }, [token, f, page, reload, retry]);
  async function loadMore() {
    const cursor = moreCursor === undefined ? data?.next_cursor : moreCursor;
    if (!cursor) return;
    try { setLoading(true); const r = await fetchMembers(token, f, cursor, LIMIT); setExtra(x => [...x, ...r.items]); setMoreCursor(r.next_cursor); }
    catch (e) { setError(msg(e)); } finally { setLoading(false); }
  }
  const rows = [...(data?.items || []), ...extra];
  const filtered = Boolean(f.q.trim() || f.status || f.role);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / LIMIT)) : 1;
  const moreOnPhone = moreCursor === undefined ? data?.has_more : Boolean(moreCursor);
  return <>
    <div className="sc-toolbar sc-search-open">
      <label className="sc-search"><NavGlyph g="search" size={17}/>
        <input type="search" value={qInput} onChange={e => setQInput(e.target.value)} placeholder="Nom ou adresse e-mail" aria-label="Rechercher un membre" maxLength={80}/>
        {loading && qInput !== '' && <i className="sc-spin" aria-hidden="true"/>}
        {qInput && <button type="button" className="sc-clear" aria-label="Effacer la recherche" onClick={() => setQInput('')}><NavGlyph g="close" size={15}/></button>}
      </label>
      <div className="sc-chips" role="group" aria-label="Statut">
        {STATUS_CHIPS.map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.status === v} onClick={() => set({status: v})}>{l}</button>)}
      </div>
      <label className="sc-select tm-role-filter"><span>Rôle</span>
        <select value={f.role} onChange={e => set({role: e.target.value})}><option value="">Tous</option>
          {roles.filter(r => r.status === 'ACTIVE').map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select></label>
    </div>
    <div className="sc-summary" role="status" aria-live="polite">
      {data ? <span><b>{data.total.toLocaleString('fr-FR')}</b> membre{data.total > 1 ? 's' : ''}{filtered ? ' correspondant' + (data.total > 1 ? 's' : '') : ''}</span> : <i className="sc-skel sc-skel-line" aria-hidden="true"/>}
      {filtered && <button type="button" className="sc-link" onClick={() => { setQInput(''); set({q: '', status: '', role: ''}); }}>Réinitialiser les filtres</button>}
    </div>
    {error ? <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Impossible de charger l’équipe.</b><small>{error}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setRetry(k => k + 1)}>Réessayer</button></div>
      : !data && loading ? <div className="sc-list" aria-busy="true" aria-label="Chargement de l’équipe">{Array.from({length: 5}).map((_, i) => <div key={i} className="sc-row tm-mrow sc-row-skel">
          <span className="tm-col-user"><i className="sc-skel" style={{width: 34, height: 34, borderRadius: 99}}/><span><i className="sc-skel" style={{width: '70%'}}/><i className="sc-skel" style={{width: '45%'}}/></span></span>
          <span><i className="sc-skel" style={{width: '60%'}}/></span><span><i className="sc-skel" style={{width: 70}}/></span><span className="tm-col-seen"><i className="sc-skel" style={{width: 80}}/></span><span/></div>)}</div>
      : rows.length === 0 ? <div className="sc-empty"><NavGlyph g={f.q ? 'search' : 'users'} size={24}/>
          <b>{f.q.trim() ? `Aucun membre pour « ${f.q.trim()} ».` : filtered ? 'Aucun membre ne correspond à ces filtres.' : 'Aucun membre dans l’équipe plateforme.'}</b>
          <small>{filtered ? 'Modifiez la recherche ou les filtres.' : 'Ajoutez un membre : nouvelle identité ou utilisateur existant.'}</small></div>
      : <div className={`sc-list ${loading ? 'sc-busy' : ''}`} role="table" aria-label="Membres de l’équipe plateforme" aria-busy={loading}>
        <div className="sc-row tm-mrow sc-row-head" role="row"><span role="columnheader">Membre</span><span role="columnheader">Rôle(s)</span>
          <span role="columnheader">Statut</span><span role="columnheader" className="tm-col-seen">Dernière activité</span><span role="columnheader"><span className="es-sr">Ouvrir</span></span></div>
        {rows.map(u => <div key={u.id} className="sc-row tm-mrow" role="row" tabIndex={0} aria-label={`${u.full_name}, ${u.role_labels.join(', ') || 'aucun rôle actif'}, ${MEMBER_STATUS_LABEL[u.status]}. Ouvrir la fiche`}
          onClick={() => onOpen(u.id)} onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); onOpen(u.id); } }}>
          <span role="cell" className="tm-col-user"><span className="tm-avatar" aria-hidden="true">{initials(u.full_name)}</span>
            <span><b>{u.full_name}{u.is_me && <em className="tm-you">Vous</em>}</b><small>{u.email}</small></span></span>
          <span role="cell" className="tm-col-roles">{u.role_labels.length ? <><b>{u.role_labels[0]}</b>{u.role_labels.length > 1 && <small> +{u.role_labels.length - 1}</small>}</> : <small className="sc-muted">Aucun rôle actif</small>}
            {u.grants_count > 0 && <em className="tm-extra" title="Capacités supplémentaires individuelles">+{u.grants_count} capacité{u.grants_count > 1 ? 's' : ''}</em>}</span>
          <span role="cell" className="tm-col-status"><MemberStatusBadge status={u.status}/></span>
          <span role="cell" className="tm-col-seen"><small title={fullDate(u.last_activity)}>{ago(u.last_activity)}</small></span>
          <span role="cell" className="tm-col-chev" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span>
        </div>)}
      </div>}
    {data && rows.length > 0 && <>
      <nav className="sc-pager sc-hide-phone" aria-label="Pagination">
        <span>{((page - 1) * LIMIT + 1).toLocaleString('fr-FR')}–{Math.min(page * LIMIT, data.total).toLocaleString('fr-FR')} sur {data.total.toLocaleString('fr-FR')}</span>
        <div><button type="button" className="sc-btn sc-btn-ghost" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}><NavGlyph g="chevronLeft" size={16}/>Précédent</button>
          <span className="sc-page" aria-current="page">Page {page} sur {totalPages}</span>
          <button type="button" className="sc-btn sc-btn-ghost" disabled={!data.has_more || loading} onClick={() => setPage(page + 1)}>Suivant<NavGlyph g="chevronRight" size={16}/></button></div>
      </nav>
      {moreOnPhone && <button type="button" className="sc-btn sc-more sc-only-phone" disabled={loading} onClick={() => void loadMore()}>{loading ? 'Chargement…' : 'Charger la suite'}</button>}
    </>}
  </>;
}

/* ---------------------------------------------------------------- add a member (two paths) */
function AddMemberWizard({token, roles, caps, existing, onClose, onDone}: {token: string; roles: PlatformRole[]; caps: PlatformCapability[];
  existing?: {id: string; full_name: string; email: string}; onClose: () => void; onDone: (id: string) => void}) {
  const [step, setStep] = useState<'kind' | 'who' | 'roles' | 'summary' | 'done'>(existing ? 'roles' : 'kind');
  const [kind, setKind] = useState<'new' | 'existing'>(existing ? 'existing' : 'new');
  const [name, setName] = useState(''); const [email, setEmail] = useState('');
  const [picked, setPicked] = useState<Candidate | null>(existing ? {...existing, active: true, schools_count: 0, first_school: null} : null);
  const [q, setQ] = useState(''); const [cands, setCands] = useState<Candidate[] | null>(null); const [candErr, setCandErr] = useState('');
  const [roleCodes, setRoleCodes] = useState<string[]>([]);
  const [delivery, setDelivery] = useState<'INVITATION' | 'TEMPORARY'>('INVITATION');
  const [emailOk, setEmailOk] = useState<boolean | null>(null);
  const [reason, setReason] = useState(''); const [ack, setAck] = useState(false);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{id: string; temporary_password: string | null; kept?: number} | null>(null);
  const key = useRef(newKey());
  useEffect(() => { void fetchMembers(token, {q: '', status: '', role: ''}, null, 1).then(r => { setEmailOk(r.email_invitations_available); if (!r.email_invitations_available) setDelivery('TEMPORARY'); }).catch(() => setEmailOk(false)); }, []);
  useEffect(() => {
    if (kind !== 'existing' || step !== 'who' || q.trim().length < 2) { setCands(null); return; }
    const ctl = new AbortController();
    const t = window.setTimeout(() => { setCandErr(''); fetchCandidates(token, q.trim(), ctl.signal).then(r => setCands(r.items)).catch(e => { if (!ctl.signal.aborted) setCandErr(msg(e)); }); }, 300);
    return () => { window.clearTimeout(t); ctl.abort(); };
  }, [q, kind, step]);
  const chosen = roles.filter(r => roleCodes.includes(r.code));
  const inherited = useMemo(() => [...new Set(chosen.flatMap(r => r.capabilities))].sort(), [roleCodes, roles]);
  const managerChosen = roleCodes.includes('MANAGER_SYSTEME');
  const who = kind === 'new' ? {name: name.trim(), email: email.trim().toLowerCase()} : {name: picked?.full_name || '', email: picked?.email || ''};

  function next() {
    setError('');
    if (step === 'kind') { setStep('who'); return; }
    if (step === 'who') {
      if (kind === 'new') {
        if (name.trim().length < 3) { setError('Indiquez le nom complet (3 caractères minimum).'); return; }
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) { setError('Saisissez une adresse e-mail valide.'); return; }
      } else if (!picked) { setError('Choisissez le compte existant.'); return; }
      setStep('roles'); return;
    }
    if (step === 'roles') { if (!roleCodes.length) { setError('Choisissez au moins un rôle.'); return; } setStep('summary'); }
  }
  async function submit() {
    setError('');
    if (reason.trim().length < 5) { setError('Le motif est obligatoire (5 caractères minimum).'); return; }
    if (managerChosen && !ack) { setError('Confirmez l’attribution du rôle Manager Système.'); return; }
    setBusy(true);
    try {
      if (kind === 'new') {
        const r = await createMember(token, key.current, {email: who.email, full_name: who.name, role_codes: roleCodes, reason: reason.trim(), delivery});
        setResult({id: r.id, temporary_password: r.temporary_password});
      } else {
        const r = await addExisting(token, key.current, picked!.id, {role_codes: roleCodes, reason: reason.trim()});
        setResult({id: r.id, temporary_password: null, kept: r.school_memberships_kept});
      }
      setStep('done');
    } catch (e) {
      const m = msg(e); setError(m);
      if (kind === 'new' && /Utilisateur existant/.test(m)) { setKind('existing'); setQ(who.email); setStep('who'); key.current = newKey(); }
    } finally { setBusy(false); }
  }
  const titles = {kind: 'Ajouter un membre', who: kind === 'new' ? 'Nouvelle identité' : 'Utilisateur existant', roles: 'Rôle(s) plateforme', summary: 'Vérifier avant validation', done: 'Membre ajouté'};
  return <Modal title={titles[step]} subtitle="Portée : Plateforme EduSync" onClose={onClose} wide>
    <div className="tm-wizard">
      {step !== 'done' && <ol className="tm-steps" aria-label="Étapes">{(['kind', 'who', 'roles', 'summary'] as const).map((s, i) => <li key={s} aria-current={step === s ? 'step' : undefined}
        className={step === s ? 'tm-step-on' : ''}><span>{i + 1}</span>{['Type', 'Identité', 'Rôles', 'Résumé'][i]}</li>)}</ol>}
      {step === 'kind' && <div className="tm-kinds" role="radiogroup" aria-label="Type de membre">
        {([['new', 'Nouvelle identité', 'La personne n’a pas encore de compte EduSync. Elle reçoit une invitation et choisit son mot de passe.', 'plus'],
           ['existing', 'Utilisateur existant', 'La personne a déjà un compte EduSync (par exemple dans une école). Le même compte reçoit l’accès plateforme : aucun doublon, son accès école est conservé.', 'users']] as const)
          .map(([v, t, d, g]) => <label key={v} className={`tm-kind ${kind === v ? 'tm-kind-on' : ''}`}>
            <input type="radio" name="tm-kind" value={v} checked={kind === v} onChange={() => setKind(v)}/>
            <NavGlyph g={g} size={20}/><span><b>{t}</b><small>{d}</small></span></label>)}
      </div>}
      {step === 'who' && kind === 'new' && <div className="sc-form">
        <div className="sc-form-row">
          <div className="sc-field"><label htmlFor="tm-name">Nom complet *</label><input id="tm-name" value={name} onChange={e => setName(e.target.value)} autoComplete="off" maxLength={180}/></div>
          <div className="sc-field"><label htmlFor="tm-email">Adresse e-mail *</label><input id="tm-email" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="off" maxLength={320}/></div>
        </div>
        <fieldset className="sc-delivery"><legend>Mise en service du compte</legend>
          <label><input type="radio" name="tm-delivery" checked={delivery === 'INVITATION'} disabled={!emailOk} onChange={() => setDelivery('INVITATION')}/>
            <span>Invitation par e-mail — la personne choisit son mot de passe, puis configure la validation en deux étapes{emailOk === false ? ' (e-mail non configuré)' : ''}</span></label>
          <label><input type="radio" name="tm-delivery" checked={delivery === 'TEMPORARY'} onChange={() => setDelivery('TEMPORARY')}/>
            <span>Mot de passe provisoire généré par le serveur, affiché une seule fois, à remplacer à la première connexion</span></label>
        </fieldset>
      </div>}
      {step === 'who' && kind === 'existing' && <div className="sc-form">
        <div className="sc-field"><label htmlFor="tm-q">Rechercher le compte (nom ou e-mail)</label>
          <input id="tm-q" type="search" value={q} onChange={e => { setQ(e.target.value); setPicked(null); }} placeholder="Au moins 2 caractères" autoComplete="off" maxLength={80}/></div>
        {candErr && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Recherche impossible.</b><small>{candErr}</small></div></div>}
        {cands && (cands.length === 0 ? <p className="sc-muted">Aucun compte hors équipe ne correspond. Un membre déjà présent se gère depuis sa fiche.</p>
          : <ul className="tm-cands" role="listbox" aria-label="Comptes trouvés">{cands.map(cnd => <li key={cnd.id}>
            <button type="button" role="option" aria-selected={picked?.id === cnd.id} disabled={!cnd.active} className={picked?.id === cnd.id ? 'tm-cand-on' : ''} onClick={() => setPicked(cnd)}>
              <span className="tm-avatar" aria-hidden="true">{initials(cnd.full_name)}</span>
              <span><b>{cnd.full_name}</b><small>{cnd.email}</small><small>{!cnd.active ? 'Compte désactivé' : cnd.schools_count ? `${cnd.first_school}${cnd.schools_count > 1 ? ` +${cnd.schools_count - 1}` : ''} — accès école conservé` : 'Aucun rattachement école'}</small></span>
              {picked?.id === cnd.id && <NavGlyph g="checkCircle" size={18}/>}</button></li>)}</ul>)}
      </div>}
      {step === 'roles' && <div className="sc-form">
        {kind === 'existing' && picked && <p className="tm-who-line"><span className="tm-avatar" aria-hidden="true">{initials(picked.full_name)}</span><span><b>{picked.full_name}</b><small>{picked.email}</small></span></p>}
        <fieldset className="tm-pick"><legend>Rôle(s) *</legend>{roles.map(r => <label key={r.code}>
          <input type="checkbox" checked={roleCodes.includes(r.code)} onChange={e => setRoleCodes(e.target.checked ? [...roleCodes, r.code] : roleCodes.filter(x => x !== r.code))}/>
          <span><b>{r.label}</b><small>{r.kind === 'PLATFORM_STANDARD' ? 'Standard' : `Personnalisé · ${r.code}`} · {r.capabilities.length} capacité(s)</small></span></label>)}</fieldset>
      </div>}
      {step === 'summary' && <div className="tm-summary">
        <dl className="sc-dl"><dt>Nom</dt><dd>{who.name}</dd><dt>E-mail</dt><dd>{who.email}</dd><dt>Portée</dt><dd>Plateforme EduSync</dd>
          <dt>Origine</dt><dd>{kind === 'new' ? (delivery === 'INVITATION' ? 'Nouvelle identité — invitation par e-mail' : 'Nouvelle identité — mot de passe provisoire') : 'Compte existant (même identité, accès école conservé)'}</dd>
          <dt>Rôle(s)</dt><dd>{chosen.map(r => r.label).join(', ')}</dd>
          <dt>Capacités</dt><dd>{inherited.length} héritée(s) · 0 supplémentaire · <b>{inherited.length} au total</b></dd></dl>
        <CapabilityGroups codes={inherited} caps={caps}/>
        {managerChosen && <label className="tm-ack"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/>
          <span><b>Je confirme l’attribution du rôle Manager Système.</b><small>Il donne la gouvernance complète de la plateforme, y compris de cette équipe.</small></span></label>}
        <div className="sc-field"><label htmlFor="tm-reason">Motif * (tracé dans l’audit)</label><input id="tm-reason" value={reason} onChange={e => setReason(e.target.value)} placeholder="Ex. : arrivée dans l’équipe support" maxLength={500}/></div>
      </div>}
      {step === 'done' && result && <div className="sc-success">
        <span className="sc-success-icon" aria-hidden="true"><NavGlyph g="checkCircle" size={30}/></span>
        <b>{who.name}</b>
        {result.temporary_password ? <OneTimeSecret value={result.temporary_password}/>
          : kind === 'new' ? <p>Invitation envoyée à {who.email}. Le lien est valable 48 heures et ne sert qu’une fois.</p>
          : <p>Accès plateforme donné au compte existant.{result.kept ? ` Ses ${result.kept} rattachement(s) école sont conservés.` : ''}</p>}
      </div>}
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot">
        {step === 'done' ? <OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={() => onDone(result!.id)}>Ouvrir la fiche</OnlineActionButton> : <>
          <button type="button" className="es-btn es-btn-ghost" onClick={() => { setError(''); if (step === 'kind' || (existing && step === 'roles')) onClose(); else setStep(step === 'summary' ? 'roles' : step === 'roles' ? 'who' : 'kind'); }}>
            {step === 'kind' || (existing && step === 'roles') ? 'Annuler' : 'Retour'}</button>
          {step === 'summary'
            ? <OnlineActionButton type="button" className="es-btn es-btn-primary" disabled={busy} onClick={() => void submit()}>{busy ? 'Validation…' : kind === 'new' ? (delivery === 'INVITATION' ? 'Créer le compte et envoyer l’invitation' : 'Créer le compte') : `Donner l’accès plateforme à ${who.name.split(' ')[0] || 'ce compte'}`}</OnlineActionButton>
            : <OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={next}>Continuer</OnlineActionButton>}
        </>}
      </div>
    </div>
  </Modal>;
}

function OneTimeSecret({value}: {value: string}) {
  const [shown, setShown] = useState(false);
  return <div className="tm-secret-box"><p>Mot de passe provisoire — affiché une seule fois :</p>
    <div className="tm-secret"><code aria-label="Mot de passe provisoire">{shown ? value : '•'.repeat(value.length)}</code>
      <button type="button" className="es-btn es-btn-ghost" aria-pressed={shown} onClick={() => setShown(x => !x)}>{shown ? 'Masquer' : 'Afficher'}</button>
      <button type="button" className="es-btn es-btn-ghost" onClick={() => { void navigator.clipboard?.writeText(value).then(() => toast.success('Copié')); }}>Copier</button></div>
    <small>Transmettez-le par un canal sûr. Il n’est enregistré nulle part en clair et doit être remplacé à la première connexion.</small></div>;
}

function CapabilityGroups({codes, caps, added = [], removed = []}: {codes: string[]; caps: PlatformCapability[]; added?: string[]; removed?: string[]}) {
  const all = [...new Set([...codes, ...removed])];
  const list = all.map(c => caps.find(x => x.code === c) || {code: c, label: c, group_name: 'Autres', risk: ''} as PlatformCapability);
  if (!list.length) return <p className="sc-muted">Aucune capacité.</p>;
  return <div className="tm-groups">{groupBy(list, c => c.group_name).map(([g, items]) => <div key={g} className="tm-group"><h4>{g}</h4>
    <ul>{items.map(c => <li key={c.code} className={added.includes(c.code) ? 'tm-add' : removed.includes(c.code) ? 'tm-del' : ''}>
      {added.includes(c.code) ? <b aria-label="ajoutée">+</b> : removed.includes(c.code) ? <b aria-label="retirée">−</b> : null}{c.label}<small>{c.code}</small></li>)}</ul></div>)}</div>;
}

/* ---------------------------------------------------------------- member sheet */
type Confirm = {title: string; body: React.ReactNode; button: string; danger?: boolean; strong?: string; run: (reason: string, key: string) => Promise<unknown>; ok: string};

function MemberSheet({token, id, roles, caps, onBack, onChanged}: {token: string; id: string; roles: PlatformRole[]; caps: PlatformCapability[]; onBack: () => void; onChanged: () => void}) {
  const [d, setD] = useState<MemberDetail | null>(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [granting, setGranting] = useState(false);
  const [assign, setAssign] = useState('');
  const [mfaReset, setMfaReset] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const title = useRef<HTMLHeadingElement>(null); const focusedFor = useRef('');
  useEffect(() => {
    const ctl = new AbortController(); setError('');
    fetchMember(token, id, ctl.signal).then(setD).catch(e => { if (!ctl.signal.aborted) setError(msg(e)); });
    return () => ctl.abort();
  }, [token, id, nonce]);
  useEffect(() => { if (d && focusedFor.current !== id) { focusedFor.current = id; title.current?.focus({preventScroll: true}); } }, [d, id]);
  const refresh = () => { setNonce(n => n + 1); onChanged(); };
  const backBtn = <PageTrail parents={[{label: 'Équipe plateforme', onSelect: onBack}]} current={d?.full_name || 'Fiche membre'}/>;
  if (error && !d) return <div className="sc-sheet-page">{backBtn}<div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Fiche indisponible.</b><small>{error}</small></div>
    <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setNonce(n => n + 1)}>Réessayer</button></div></div>;
  if (!d) return <div className="sc-sheet-page" aria-busy="true">{backBtn}<div className="sc-card"><i className="sc-skel" style={{width: '50%', height: 22}}/><i className="sc-skel" style={{width: '30%'}}/></div></div>;

  const me = d.is_me;
  const activeRoles = d.roles.filter(r => r.active);
  const status: MemberStatus = !d.account_active ? 'DISABLED' : d.platform_status === 'SUSPENDED' ? 'SUSPENDED'
    : (d.must_change_password || d.invitation_state === 'PENDING') ? 'PENDING' : 'ACTIVE';
  const assignable = roles.filter(r => !activeRoles.some(a => a.code === r.code));
  const effective = d.capabilities.map(c => c.code);
  const grantable = caps.filter(c => c.delegable && !effective.includes(c.code));
  const isManager = activeRoles.some(r => r.code === 'MANAGER_SYSTEME');
  const preview = (add: string[], del: string[]) => <div className="tm-preview">
    <p><b>Avant</b> {d.effective_count} capacité(s) effective(s) → <b>Après</b> {d.effective_count + add.length - del.length}</p>
    <CapabilityGroups codes={[...add]} removed={del} added={add} caps={caps}/></div>;
  function roleDiff(code: string, adding: boolean) {
    const role = roles.find(r => r.code === code) || null;
    const roleCaps = role?.capabilities || d!.capabilities.filter(c => c.origins.some(o => o.kind === 'ROLE' && o.code === code)).map(c => c.code);
    if (adding) return {add: roleCaps.filter(c => !effective.includes(c)), del: [] as string[]};
    const lost = d!.capabilities.filter(c => c.origins.some(o => o.kind === 'ROLE' && o.code === code) && c.origins.length === 1).map(c => c.code);
    return {add: [] as string[], del: lost};
  }
  return <div className="sc-sheet-page">
    {backBtn}
    <header className="sc-card sc-sheet-head">
      <div className="sc-sheet-id">
        <span className="sc-sheet-logo tm-logo" aria-hidden="true">{initials(d.full_name)}</span>
        <div><h2 ref={title} tabIndex={-1}>{d.full_name}{me && <em className="tm-you">Vous</em>}</h2><p>{d.email}</p>
          <div className="sc-badges">{d.is_member && <MemberStatusBadge status={status}/>}{d.invitation_state === 'EXPIRED' && <span className="sc-badge tm-ms-suspended"><i aria-hidden="true"/>Invitation expirée</span>}
            {!d.is_member && <span className="sc-badge tm-ms-disabled"><i aria-hidden="true"/>Sans accès plateforme</span>}</div></div>
      </div>
      {!me && d.is_member && <div className="sc-sheet-actions">
        {(d.invitation_state === 'PENDING' || d.invitation_state === 'EXPIRED') && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setConfirm({title: 'Renvoyer l’invitation',
          body: <p>Un nouveau lien à usage unique est envoyé à {d.email} ; l’ancien cesse de fonctionner.</p>, button: 'Renvoyer', ok: 'Invitation renvoyée',
          run: (r, k) => resendInvitation(token, k, id, r)})}><NavGlyph g="message" size={16}/>Renvoyer l’invitation</OnlineActionButton>}
        {d.platform_status === 'SUSPENDED'
          ? <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setConfirm({title: 'Réactiver l’accès plateforme', body: <p>Ses rôles et capacités redeviennent effectifs immédiatement.</p>,
              button: 'Réactiver', ok: 'Compte réactivé', run: (r, k) => setMemberStatus(token, k, id, 'reactivate', r)})}>Réactiver</OnlineActionButton>
          : <OnlineActionButton type="button" className="sc-btn sc-btn-danger" onClick={() => setConfirm({title: 'Suspendre l’accès plateforme', danger: true,
              body: <><p><b>Suspension temporaire</b> : toutes ses sessions plateforme sont coupées ; ses rôles et capacités sont <b>conservés</b> et reviennent à la réactivation.</p>
                <p className="sc-muted">Pour retirer définitivement l’accès, utilisez « Retirer l’accès plateforme ».</p></>,
              button: 'Suspendre', ok: 'Compte suspendu', strong: isManager ? 'Je confirme la suspension d’un Manager Système.' : undefined,
              run: (r, k) => setMemberStatus(token, k, id, 'suspend', r)})}>Suspendre</OnlineActionButton>}
        <OnlineActionButton type="button" className="sc-btn sc-btn-danger" onClick={() => setConfirm({title: 'Retirer l’accès plateforme', danger: true,
          body: <><p><b>Retrait définitif</b> : tous ses rôles plateforme ({activeRoles.map(r => r.label).join(', ') || 'aucun'}) et ses {d.supplementary_count} capacité(s) supplémentaire(s) prennent fin ; ses sessions plateforme sont fermées.</p>
            <p>{d.school_memberships ? `Son compte EduSync et ses ${d.school_memberships} rattachement(s) école restent intacts.` : 'Son compte EduSync reste intact.'}</p>{preview([], effective)}</>,
          button: 'Retirer l’accès', ok: 'Accès plateforme retiré', strong: isManager ? 'Je confirme le retrait d’accès d’un Manager Système.' : undefined,
          run: (r, k) => removeAccess(token, k, id, r)})}>Retirer l’accès plateforme</OnlineActionButton>
      </div>}
      {me && <p className="sc-muted sc-noaction">Votre compte : vos propres droits ne se modifient pas ici.</p>}
    </header>

    <section className="sc-summary-grid tm-summary-grid" aria-label="Synthèse">
      <div className={`sc-stat ${status === 'ACTIVE' && d.is_member ? 'sc-ok' : 'sc-warn'}`}><small>Statut</small><b>{d.is_member ? MEMBER_STATUS_LABEL[status] : 'Sans accès plateforme'}</b><em>{status === 'SUSPENDED' ? (d.status_reason ? `Motif : ${d.status_reason}` : 'Accès suspendu') : d.must_change_password ? 'Mot de passe provisoire à remplacer' : d.invitation_state === 'PENDING' ? 'Invitation envoyée, non encore acceptée' : status === 'DISABLED' ? 'Compte EduSync désactivé' : 'Accès plateforme opérationnel'}</em></div>
      <div className="sc-stat"><small>Dernière activité</small><b>{ago(d.last_activity)}</b><em>Session plateforme</em></div>
      <div className="sc-stat"><small>Rôle(s)</small><b>{activeRoles.length}</b><em>{activeRoles.map(r => r.label).join(', ') || 'Aucun rôle actif'}</em></div>
      <div className="sc-stat"><small>Capacités effectives</small><b>{d.effective_count}</b><em>{d.inherited_count} héritée(s) · {d.supplementary_count} supplémentaire(s)</em></div>
    </section>

    <div className="sc-sheet-grid">
      <section className="sc-card"><div className="sc-card-head"><h3>Rôles</h3></div>
        <ul className="tm-plain">{activeRoles.map(r => <li key={r.code}><span><b>{r.label}</b><small>{r.kind === 'PLATFORM_STANDARD' ? 'Standard' : `Personnalisé · ${r.code}`}{r.status !== 'ACTIVE' ? ` · rôle ${ROLE_STATUS[r.status]?.toLowerCase()}` : ''}</small></span>
          {!me && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => { const diff = roleDiff(r.code, false); setConfirm({title: `Retirer le rôle « ${r.label} »`, danger: r.code === 'MANAGER_SYSTEME',
            body: <>{activeRoles.length === 1 && <p><b>C’est son seul rôle</b> : son accès plateforme et ses capacités supplémentaires prennent fin.</p>}{preview(diff.add, diff.del)}</>,
            button: 'Retirer le rôle', ok: 'Rôle retiré', strong: r.code === 'MANAGER_SYSTEME' ? 'Je confirme la rétrogradation d’un Manager Système.' : undefined,
            run: (rs, k) => revokeRole(token, k, id, r.code, rs)}); }}>Retirer</OnlineActionButton>}</li>)}
          {!activeRoles.length && <li className="sc-muted">Aucun rôle actif.</li>}</ul>
        {!me && d.is_member && assignable.length > 0 && <div className="tm-assign">
          <select aria-label="Rôle à attribuer" value={assign} onChange={e => setAssign(e.target.value)}><option value="">Attribuer un rôle…</option>{assignable.map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select>
          <button type="button" className="sc-btn" disabled={!assign} onClick={() => { const role = roles.find(r => r.code === assign)!; const diff = roleDiff(assign, true);
            setConfirm({title: `Attribuer « ${role.label} »`, body: preview(diff.add, []), button: 'Attribuer le rôle', ok: 'Rôle attribué',
              strong: assign === 'MANAGER_SYSTEME' ? 'Je confirme la promotion au rôle Manager Système.' : undefined,
              run: async (rs, k) => { await assignRole(token, k, id, assign, rs); setAssign(''); }}); }}>Attribuer</button></div>}
      </section>
      <section className="sc-card"><h3>Sécurité</h3>
        <dl className="sc-dl"><dt>Validation en deux étapes</dt><dd>{d.mfa?.enrolled ? `Activée depuis le ${new Date(d.mfa.confirmed_at || '').toLocaleDateString('fr-FR')} · ${d.mfa.recovery_codes_remaining} code(s) de secours` : 'À configurer à la prochaine connexion'}</dd>
          <dt>Sessions plateforme</dt><dd>{d.sessions.length}</dd>
          <dt>Droits modifiés</dt><dd>{d.rights_changed ? `${fullDate(d.rights_changed.occurred_at)}${d.rights_changed.actor ? ` par ${d.rights_changed.actor}` : ''}` : '—'}</dd></dl>
        {!me && d.is_member && <div className="tm-actions">
          {d.mfa?.enrolled && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setMfaReset(true)}>Réinitialiser la validation en deux étapes</OnlineActionButton>}
          {d.sessions.length > 0 && <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setConfirm({title: 'Déconnecter tous ses appareils', body: <p>Ses {d.sessions.length} session(s) plateforme sont fermées.</p>,
            button: 'Déconnecter', ok: 'Appareils déconnectés', run: (r, k) => revokeSessions(token, k, id, r)})}>Déconnecter ses appareils</button>}
          <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setConfirm({title: 'Réinitialiser le mot de passe', body: <p>Un mot de passe provisoire est généré et affiché une fois ; toutes ses sessions sont coupées.</p>,
            button: 'Réinitialiser', ok: 'Mot de passe réinitialisé', run: async (r, k) => { const out = await resetPassword(token, k, id, r); if (out.temporary_password) setSecret(out.temporary_password); }})}>Réinitialiser le mot de passe</OnlineActionButton>
        </div>}
      </section>
    </div>

    <section className="sc-card"><div className="sc-card-head"><h3>Capacités effectives <small>({d.effective_count})</small></h3>
      {!me && d.is_member && status !== 'SUSPENDED' && grantable.length > 0 && activeRoles.length > 0 && <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setGranting(true)}><NavGlyph g="plus" size={16}/>Capacité supplémentaire</button>}</div>
      <p className="tm-counts"><span>Capacités héritées du rôle : <b>{d.inherited_count}</b></span><span>Capacités supplémentaires : <b>{d.supplementary_count}</b></span><span>Total effectif : <b>{d.effective_count}</b></span></p>
      {d.capabilities.length === 0 ? <p className="sc-muted">Aucune capacité effective.</p> : <div className="tm-groups">{groupBy(d.capabilities, c => c.group_name).map(([g, items]) => <details key={g} className="tm-group" open>
        <summary><h4>{g}</h4><small>{items.length}</small></summary>
        <ul>{items.map(c => <li key={c.code}><span><b>{c.label}</b><small>{c.code}{c.risk ? ` · risque ${RISK_LABEL[c.risk]?.toLowerCase() || c.risk}` : ''}</small>
          <span className="tm-origins">{c.origins.map((o, i) => o.kind === 'ROLE' ? <em key={i} className="tm-origin">{o.label}</em>
            : <em key={i} className="tm-origin tm-origin-grant" title={`Motif : ${o.reason}`}>Attribution individuelle{o.valid_until ? ` · jusqu’au ${fullDate(o.valid_until)}` : ''}{o.granted_by ? ` · par ${o.granted_by}` : ''}</em>)}</span></span>
          {!me && c.origins.some(o => o.kind === 'GRANT') && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setConfirm({title: `Retirer « ${c.label} »`,
            body: <><p>Seule l’attribution individuelle prend fin ; les rôles ne changent pas.{c.origins.length > 1 ? ' La capacité reste héritée d’un rôle.' : ''}</p>{preview([], c.origins.length > 1 ? [] : [c.code])}</>,
            button: 'Retirer la capacité', ok: 'Capacité retirée', run: (r, k) => revokeCapability(token, k, id, c.code, r)})}>Retirer</OnlineActionButton>}</li>)}</ul></details>)}</div>}
      <details className="tm-group tm-reserved"><summary><h4>Capacités critiques non délégables</h4><small>{d.non_delegable.length}</small></summary>
        <ul>{d.non_delegable.map(c => <li key={c.code}><span><b><NavGlyph g="lock" size={13}/> {c.label}</b><small>{c.reason}</small></span></li>)}</ul></details>
    </section>

    <section className="sc-card"><h3>Historique</h3>
      <ol className="tm-history">{d.audit.map((a, i) => <li key={i}><b>{auditActionLabel(a.action)}</b><small>{fullDate(a.occurred_at)}{a.actor ? ` · ${a.actor}` : ''}{a.reason ? ` · ${a.reason}` : ''}</small></li>)}
        {!d.audit.length && <li className="sc-muted">Aucun événement.</li>}</ol></section>

    {confirm && <ConfirmDialog c={confirm} onClose={() => setConfirm(null)} onDone={() => { setConfirm(null); refresh(); }}/>}
    {granting && <GrantDialog token={token} member={d} caps={grantable} allCaps={caps} onClose={() => setGranting(false)} onDone={() => { setGranting(false); refresh(); }}/>}
    {mfaReset && <MfaResetDialog name={d.full_name} onClose={() => setMfaReset(false)} onConfirm={async (why, withPassword) => {
      let p: string | null = null;
      try { p = (await resetMfa(token, newKey(), id, why, withPassword)).temporary_password; } catch (e) { toast.error(msg(e)); setMfaReset(false); return; }
      toast.success(withPassword ? 'Validation en deux étapes et mot de passe réinitialisés' : 'Validation en deux étapes réinitialisée');
      setMfaReset(false); if (p) setSecret(p); refresh();
    }}/>}
    {secret && <Modal title="Mot de passe provisoire" subtitle={d.full_name} onClose={() => setSecret(null)}><OneTimeSecret value={secret}/>
      <div className="es-modal-foot"><OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={() => setSecret(null)}>Terminé</OnlineActionButton></div></Modal>}
  </div>;
}


function ConfirmDialog({c, onClose, onDone}: {c: Confirm; onClose: () => void; onDone: () => void}) {
  const [reason, setReason] = useState(''); const [ack, setAck] = useState(false); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const key = useRef(newKey());
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (reason.trim().length < 5) { setError('Le motif est obligatoire (5 caractères minimum).'); return; }
    if (c.strong && !ack) { setError('Cochez la confirmation.'); return; }
    setBusy(true);
    try { await c.run(reason.trim(), key.current); toast.success(c.ok); onDone(); } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title={c.title} onClose={onClose} wide>
    <form className="sc-form" onSubmit={submit} noValidate>
      <div className="tm-confirm-body">{c.body}</div>
      {c.strong && <label className="tm-ack"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/><span><b>{c.strong}</b><small>Un code de confirmation peut vous être demandé.</small></span></label>}
      <div className={`sc-field ${error ? 'sc-invalid' : ''}`}><label htmlFor="tm-c-reason">Motif * (tracé dans l’audit)</label>
        <textarea id="tm-c-reason" rows={2} value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/>{error && <small role="alert">{error}</small>}</div>
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton type="submit" className={`es-btn ${c.danger ? 'es-btn-danger' : 'es-btn-primary'}`} disabled={busy}>{busy ? 'Traitement…' : c.button}</OnlineActionButton></div>
    </form>
  </Modal>;
}

function GrantDialog({token, member, caps, allCaps, onClose, onDone}: {token: string; member: MemberDetail; caps: PlatformCapability[]; allCaps: PlatformCapability[]; onClose: () => void; onDone: () => void}) {
  const [code, setCode] = useState(''); const [temporary, setTemporary] = useState(false); const [until, setUntil] = useState('');
  const [reason, setReason] = useState(''); const [ack, setAck] = useState(false); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const key = useRef(newKey());
  const cap = caps.find(c => c.code === code);
  const critical = cap?.risk === 'CRITICAL';
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!cap) { setError('Choisissez une capacité.'); return; }
    let iso: string | null = null;
    if (temporary) { const t = new Date(until); if (!until || Number.isNaN(t.getTime()) || t.getTime() <= Date.now()) { setError('La date de fin doit être dans le futur.'); return; } iso = t.toISOString(); }
    if (reason.trim().length < 5) { setError('Le motif est obligatoire (5 caractères minimum).'); return; }
    if (critical && !ack) { setError('Cochez la confirmation pour une capacité critique.'); return; }
    setBusy(true);
    try { const r = await grantCapability(token, key.current, member.id, {capability_code: code, reason: reason.trim(), valid_until: iso}); toast.success(`Capacité ajoutée : ${r.effective_before} → ${r.effective_after}`); onDone(); }
    catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title="Capacité supplémentaire" subtitle={`${member.full_name} · le rôle n’est pas modifié`} onClose={onClose} wide>
    <form className="sc-form" onSubmit={submit} noValidate>
      <div className="sc-field"><label htmlFor="tm-g-cap">Capacité *</label>
        <select id="tm-g-cap" value={code} onChange={e => { setCode(e.target.value); setAck(false); }}><option value="">Choisir…</option>
          {groupBy(caps, c => c.group_name).map(([g, items]) => <optgroup key={g} label={g}>{items.map(c => <option key={c.code} value={c.code}>{c.label}</option>)}</optgroup>)}</select>
        <small className="sc-hint">Seules les capacités que vous détenez et qui sont délégables sont proposées.</small></div>
      {cap && <div className="tm-preview"><p><b>{cap.label}</b> <small>{cap.code} · {cap.group_name} · risque {RISK_LABEL[cap.risk]?.toLowerCase() || cap.risk}</small></p>
        <p><b>Avant</b> {member.effective_count} capacité(s) effective(s) → <b>Après</b> {member.effective_count + 1}</p>
        <CapabilityGroups codes={[cap.code]} added={[cap.code]} caps={allCaps}/></div>}
      <fieldset className="sc-delivery"><legend>Durée</legend>
        <label><input type="radio" name="tm-g-dur" checked={!temporary} onChange={() => setTemporary(false)}/><span>Permanente (jusqu’au retrait)</span></label>
        <label><input type="radio" name="tm-g-dur" checked={temporary} onChange={() => setTemporary(true)}/><span>Temporaire, jusqu’à une date et heure : elle disparaît alors d’elle-même</span></label>
        {temporary && <input type="datetime-local" aria-label="Date et heure de fin" value={until} onChange={e => setUntil(e.target.value)} className="tm-until"/>}
      </fieldset>
      {critical && <label className="tm-ack"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/><span><b>Capacité critique : je confirme cette délégation.</b><small>Un code de confirmation peut vous être demandé.</small></span></label>}
      <div className={`sc-field ${error ? 'sc-invalid' : ''}`}><label htmlFor="tm-g-reason">Motif * (tracé dans l’audit)</label>
        <textarea id="tm-g-reason" rows={2} value={reason} onChange={e => setReason(e.target.value)} placeholder="Ex. : remplacement pendant les congés" maxLength={500}/>{error && <small role="alert">{error}</small>}</div>
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton type="submit" className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Attribution…' : 'Ajouter la capacité'}</OnlineActionButton></div>
    </form>
  </Modal>;
}

/** Lost phone: reason (identity checked out of band), optional password reset, explicit consequences. */
function MfaResetDialog({name, onClose, onConfirm}: {name: string; onClose: () => void; onConfirm: (reason: string, withPassword: boolean) => Promise<void>}) {
  const [why, setWhy] = useState(''); const [withPassword, setWithPassword] = useState(false); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (why.trim().length < 5) { setError('Le motif est obligatoire (5 caractères minimum).'); return; }
    try { setBusy(true); await onConfirm(why.trim(), withPassword); } finally { setBusy(false); }
  }
  return <Modal title="Réinitialiser la validation en deux étapes" subtitle={name} onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      <div className="es-alert es-alert-warn" role="note"><NavGlyph g="alert" size={16}/><span>Vérifiez d’abord l’identité de la personne par un autre canal (appel, rencontre). Ses sessions plateforme seront coupées, elle sera prévenue dans EduSync, et elle configurera une nouvelle application à sa prochaine connexion.</span></div>
      <div className="sc-field"><label htmlFor="tm-mfa-why">Motif *</label><textarea id="tm-mfa-why" rows={3} value={why} onChange={e => setWhy(e.target.value)} placeholder="Ex. : téléphone perdu, identité vérifiée par appel le…"/></div>
      <label className="mfa-reset-pw"><input type="checkbox" checked={withPassword} onChange={e => setWithPassword(e.target.checked)}/><span><b>Réinitialiser aussi le mot de passe</b><small>Recommandé si le téléphone a été volé ou si le mot de passe a pu être vu. Un mot de passe provisoire est généré et affiché une fois ; toutes ses sessions sont coupées.</small></span></label>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><OnlineActionButton className="es-btn es-btn-danger" disabled={busy}>{busy ? 'Réinitialisation…' : 'Réinitialiser'}</OnlineActionButton></div>
    </form>
  </Modal>;
}

/* ---------------------------------------------------------------- Rôles */
function RolesView({token, roles, caps, onChanged}: {token: string; roles: PlatformRole[] | null; caps: PlatformCapability[]; onChanged: () => void}) {
  const [edit, setEdit] = useState<PlatformRole | null>(null);
  const [view, setView] = useState<PlatformRole | null>(null);
  const [clone, setClone] = useState<PlatformRole | null>(null);
  const [status, setStatus] = useState<{role: PlatformRole; action: 'activate' | 'archive'} | null>(null);
  if (roles === null) return <div className="sc-list" aria-busy="true" aria-label="Chargement des rôles">{Array.from({length: 3}).map((_, i) => <div key={i} className="sc-card"><i className="sc-skel" style={{width: '40%', height: 18}}/><i className="sc-skel" style={{width: '70%'}}/></div>)}</div>;
  if (!roles.length) return <div className="sc-empty"><NavGlyph g="shield" size={24}/><b>Aucun rôle plateforme.</b></div>;
  return <>
    <ul className="tm-roles">{roles.map(r => {
      const std = r.kind === 'PLATFORM_STANDARD';
      const sameLabel = roles.filter(x => x.label.trim().toLowerCase() === r.label.trim().toLowerCase()).length > 1;
      return <li key={r.id} className={r.status === 'ARCHIVED' ? 'tm-archived' : ''}>
        <div className="tm-role-head"><div><b>{r.label}</b><small>{r.code}{sameLabel ? ' · même libellé qu’un autre rôle' : ''}</small></div>
          <span className="tm-badges"><em className={`tm-chip ${std ? 'tm-chip-std' : ''}`}>{std ? 'Standard · non modifiable' : 'Personnalisé'}</em><em className={`tm-chip tm-st-${r.status.toLowerCase()}`}>{ROLE_STATUS[r.status] || r.status}</em></span></div>
        {r.description && <p>{r.description}</p>}
        <details className="tm-role-caps-d"><summary>{r.capabilities.length} capacité(s) · {groupBy(r.capabilities, c => caps.find(x => x.code === c)?.group_name || 'Autres').map(([g]) => g).join(', ') || '—'}</summary>
          <CapabilityGroups codes={r.capabilities} caps={caps}/></details>
        <div className="tm-role-foot"><small>{r.active_users ? `${r.active_users} membre(s)` : 'Aucun membre'} · modifié {ago(r.updated_at).toLowerCase()}</small>
          <span>
            {std && <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setView(r)}>Consulter</button>}
            {!std && r.status !== 'ARCHIVED' && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setEdit(r)}>Modifier</OnlineActionButton>}
            {!std && r.status === 'DRAFT' && <OnlineActionButton type="button" className="sc-btn" onClick={() => setStatus({role: r, action: 'activate'})}>Activer</OnlineActionButton>}
            <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => setClone(r)}>Cloner</OnlineActionButton>
            {!std && r.status !== 'ARCHIVED' && <OnlineActionButton type="button" className="sc-btn sc-btn-danger" onClick={() => setStatus({role: r, action: 'archive'})}>Archiver</OnlineActionButton>}
          </span></div>
      </li>;
    })}</ul>
    {view && <Modal title={view.label} subtitle={`${view.code} · rôle standard, non modifiable : clonez-le pour l’adapter`} onClose={() => setView(null)} wide>
      <CapabilityGroups codes={view.capabilities} caps={caps}/>
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={() => setView(null)}>Fermer</button>
        <OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={() => { setClone(view); setView(null); }}>Cloner ce rôle</OnlineActionButton></div></Modal>}
    {edit && <RoleEditor token={token} role={edit} caps={caps} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); onChanged(); }}/>}
    {clone && <CloneDialog token={token} role={clone} onClose={() => setClone(null)} onDone={() => { setClone(null); onChanged(); }}/>}
    {status && <ConfirmDialog c={{title: status.action === 'activate' ? `Activer « ${status.role.label} »` : `Archiver « ${status.role.label} »`, danger: status.action === 'archive',
      body: status.action === 'activate' ? <p>Le rôle pourra ensuite être attribué.</p>
        : <p>{status.role.active_users ? <><b>Ce rôle est attribué à {status.role.active_users} membre(s).</b> Ils perdent immédiatement ses capacités ; les attributions restent visibles dans l’historique.</> : 'Aucun membre ne détient ce rôle.'} Un rôle archivé ne peut plus être attribué ni modifié (clonez-le pour repartir).</p>,
      button: status.action === 'activate' ? 'Activer' : 'Archiver', ok: status.action === 'activate' ? 'Rôle activé' : 'Rôle archivé',
      run: (r, k) => roleStatus(token, k, status.role.id, status.action, r)}} onClose={() => setStatus(null)} onDone={() => { setStatus(null); onChanged(); }}/>}
  </>;
}

function RoleCreateButton({token, caps, onSaved}: {token: string; caps: PlatformCapability[]; onSaved: () => void}) {
  const [open, setOpen] = useState(false);
  return <><OnlineActionButton type="button" className="sc-btn sc-btn-primary" onClick={() => setOpen(true)}><NavGlyph g="plus" size={16}/><span>Nouveau rôle</span></OnlineActionButton>
    {open && <RoleEditor token={token} role={null} caps={caps} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); onSaved(); }}/>}</>;
}

function CapabilityPicker({caps, value, onChange}: {caps: PlatformCapability[]; value: string[]; onChange: (v: string[]) => void}) {
  return <fieldset className="tm-pick tm-pick-caps"><legend>Capacités du rôle</legend>
    {groupBy(caps, c => c.group_name).map(([g, list]) => <details key={g} className="tm-cap-group" open><summary><h4>{g}</h4><small>{list.filter(c => value.includes(c.code)).length}/{list.length}</small></summary>{list.map(c => {
      const why = c.reserved ? 'Réservée au Manager Système : non délégable.' : !c.held ? 'Vous ne détenez pas cette capacité.' : '';
      return <label key={c.code} className={!c.delegable ? 'tm-cap-off' : ''}>
        <input type="checkbox" disabled={!c.delegable} checked={value.includes(c.code)} onChange={e => onChange(e.target.checked ? [...value, c.code] : value.filter(x => x !== c.code))} aria-describedby={why ? `why-${c.code}` : undefined}/>
        <span><b>{c.label}</b><small>{c.code} · risque {RISK_LABEL[c.risk]?.toLowerCase() || c.risk}</small>{why && <small id={`why-${c.code}`} className="tm-why"><NavGlyph g="lock" size={12}/>{why}</small>}</span>
      </label>;
    })}</details>)}
  </fieldset>;
}

function RoleEditor({token, role, caps, onClose, onSaved}: {token: string; role: PlatformRole | null; caps: PlatformCapability[]; onClose: () => void; onSaved: () => void}) {
  const [code, setCode] = useState(''); const [label, setLabel] = useState(role?.label || ''); const [description, setDescription] = useState(role?.description || '');
  const [selected, setSelected] = useState<string[]>(role?.capabilities || []); const [reason, setReason] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const key = useRef(newKey());
  const added = role ? selected.filter(c => !role.capabilities.includes(c)) : []; const removed = role ? role.capabilities.filter(c => !selected.includes(c)) : [];
  const needsReason = role?.status === 'ACTIVE';
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!role && !/^[A-Z][A-Z0-9_]{2,63}$/.test(code)) { setError('Code : majuscules, chiffres et « _ », 3 caractères minimum, commençant par une lettre.'); return; }
    if (label.trim().length < 3) { setError('Le libellé doit compter au moins 3 caractères.'); return; }
    if (needsReason && reason.trim().length < 5) { setError('Motif obligatoire : ce rôle actif est attribué.'); return; }
    try {
      setBusy(true);
      if (role) await updateRole(token, key.current, role.id, {label, description, capabilities: selected, version: role.version, reason: reason.trim() || undefined});
      else await createRole(token, key.current, {code, label, description, capabilities: selected});
      toast.success(role ? 'Rôle modifié' : 'Rôle créé en brouillon : activez-le pour l’attribuer'); onSaved();
    } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title={role ? `Modifier « ${role.label} »` : 'Nouveau rôle plateforme'} subtitle="Un rôle personnalisé ne donne jamais accès aux données des écoles." onClose={onClose} wide>
    <form className="sc-form" onSubmit={save} noValidate>
      {!role && <div className="sc-field"><label htmlFor="tm-r-code">Code *</label><input id="tm-r-code" value={code} onChange={e => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_'))} placeholder="SUPPORT_NIVEAU_1" autoComplete="off"/></div>}
      <div className="sc-field"><label htmlFor="tm-r-label">Libellé *</label><input id="tm-r-label" value={label} onChange={e => setLabel(e.target.value)} placeholder="Support niveau 1"/></div>
      <div className="sc-field"><label htmlFor="tm-r-desc">Description</label><textarea id="tm-r-desc" rows={2} value={description} onChange={e => setDescription(e.target.value)} placeholder="À quoi sert ce rôle ?"/></div>
      <CapabilityPicker caps={caps} value={selected} onChange={setSelected}/>
      {role && (added.length > 0 || removed.length > 0) && <div className="tm-preview"><p><b>{role.active_users ? `Cette modification affectera ${role.active_users} membre(s).` : 'Aucun membre ne détient ce rôle.'}</b></p>
        <CapabilityGroups codes={added} added={added} removed={removed} caps={caps}/></div>}
      {needsReason && <div className="sc-field"><label htmlFor="tm-r-reason">Motif * (tracé dans l’audit)</label><input id="tm-r-reason" value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/></div>}
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Enregistrement…' : role ? 'Enregistrer' : 'Créer le brouillon'}</OnlineActionButton></div>
    </form>
  </Modal>;
}

function CloneDialog({token, role, onClose, onDone}: {token: string; role: PlatformRole; onClose: () => void; onDone: () => void}) {
  const [label, setLabel] = useState(`${role.label} (copie)`); const [code, setCode] = useState(`${role.code}_COPIE`.slice(0, 64));
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const key = useRef(newKey());
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!/^[A-Z][A-Z0-9_]{2,63}$/.test(code)) { setError('Code : majuscules, chiffres et « _ », commençant par une lettre.'); return; }
    if (label.trim().length < 3) { setError('Le libellé doit compter au moins 3 caractères.'); return; }
    try { setBusy(true); await cloneRole(token, key.current, role.id, {code, label: label.trim()}); toast.success('Rôle cloné en brouillon'); onDone(); }
    catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title={`Cloner « ${role.label} »`} subtitle="Le clone est un rôle personnalisé indépendant, créé en brouillon. Les capacités réservées ne sont jamais copiées." onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      <div className="sc-field"><label htmlFor="tm-cl-label">Libellé *</label><input id="tm-cl-label" value={label} onChange={e => setLabel(e.target.value)}/></div>
      <div className="sc-field"><label htmlFor="tm-cl-code">Code *</label><input id="tm-cl-code" value={code} onChange={e => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_'))} autoComplete="off"/></div>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Clonage…' : 'Cloner'}</OnlineActionButton></div>
    </form>
  </Modal>;
}
