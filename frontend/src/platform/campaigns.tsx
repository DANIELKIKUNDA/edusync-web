import {OnlineActionButton} from './online_action';
import {PageTrail} from './navigation';
import React, {useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {platformRbacRoles, teamRoles, type InboxItem} from '../api';
import {Modal} from './account';
import {AudienceChangedError, fetchAuthors, fetchCampaign, fetchHistory, previewAudience, sendCampaign, SEVERITY, TARGET_LABEL, TARGETS,
  type Audience, type CampaignDetail, type CampaignPage, type CampaignRow, type HistoryFilters, type Severity, type Target, type TargetType} from './campaigns_api';
import {friendlyError, UserFacingError} from './errors';
import {fetchIdentities} from './identities_api';
import {NavGlyph} from './nav_icons';
import {Item as BellItem} from './notification_center';
import {fetchSchools} from './schools_api';
import {fetchMembers} from './team_api';
import './schools.css';
import './campaigns.css';
import {DateInput} from './date_input';

/* Notifications système (Plateforme EduSync), lot 2026-10. Internal in-app notifications only: read in the bell of
   each recipient; no SMS, WhatsApp or e-mail is sent. History (server-side search, filters, keyset pagination), read-only
   detail (a sent notification is immutable; « Dupliquer » prefills a new one), and a composer in four steps
   (Destinataires → Contenu → Options → Aperçu) with a server-side audience estimate. The audience is decided again by
   the server at send time (snapshot): it never reaches more deliveries than the sender confirmed. */

const LIMIT = 25;
const EMPTY: HistoryFilters = {q: '', severity: '', target: '', status: '', author: '', from: '', to: ''};
const msg = (e: unknown) => e instanceof UserFacingError ? e.message : friendlyError(e);
const fullDate = (iso: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {weekday: 'short', day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit'}) : '—';
const shortDate = (iso: string) => new Date(iso).toLocaleString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'});
const tzName = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return ''; } })();
type Prefill = {title: string; body: string; severity: Severity; link: string; target: Target};

export function SeverityBadge({s}: {s: Severity}) {
  return <span className={`sc-badge cp-sev-${s.toLowerCase()}`}><NavGlyph g={SEVERITY[s].icon} size={13}/>{SEVERITY[s].label}</span>;
}
function StatusBadge({s}: {s: 'ACTIVE' | 'EXPIRED'}) {
  return <span className={`sc-badge ${s === 'ACTIVE' ? 'cp-st-active' : 'cp-st-expired'}`}><i aria-hidden="true"/>{s === 'ACTIVE' ? 'Active' : 'Expirée'}</span>;
}

export function CampaignsPanel({token, canTeam}: {token: string; canTeam: boolean}) {
  const [openId, setOpenId] = useState<string | null>(() => new URLSearchParams(window.location.search).get('campaign'));
  const [composer, setComposer] = useState<Prefill | null | false>(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const h = () => setOpenId(new URLSearchParams(window.location.search).get('campaign'));
    window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h);
  }, []);
  const open = (id: string) => { setOpenId(id); history.pushState({...(history.state || {}), campaign: id}, '', `${window.location.pathname}?campaign=${id}`); window.scrollTo(0, 0); };
  const back = () => { if (history.state?.campaign) history.back(); else { setOpenId(null); history.replaceState(history.state, '', window.location.pathname); } };
  return <>
    {openId ? <CampaignDetailView token={token} id={openId} onBack={back} onDuplicate={p => setComposer(p)}/>
      : <History token={token} reload={reload} onOpen={open} onNew={() => setComposer(null)}/>}
    {composer !== false && <Composer token={token} canTeam={canTeam} prefill={composer} onClose={() => setComposer(false)}
      onSent={id => { setComposer(false); setReload(k => k + 1); open(id); }}/>}
  </>;
}

/* ---------------------------------------------------------------- history */
function History({token, reload, onOpen, onNew}: {token: string; reload: number; onOpen: (id: string) => void; onNew: () => void}) {
  const [f, setF] = useState<HistoryFilters>(EMPTY);
  const [qInput, setQInput] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CampaignPage | null>(null);
  const [extra, setExtra] = useState<CampaignRow[]>([]);
  const [moreCursor, setMoreCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [authors, setAuthors] = useState<{id: string; full_name: string}[]>([]);
  const [sheet, setSheet] = useState(false);
  const reqId = useRef(0);
  const set = (patch: Partial<HistoryFilters>) => { setF(x => ({...x, ...patch})); setCursors([null]); setPage(1); setExtra([]); };
  useEffect(() => { void fetchAuthors(token).then(setAuthors); }, [token, reload]);
  useEffect(() => { if (qInput === f.q) return; const t = window.setTimeout(() => set({q: qInput}), 300); return () => window.clearTimeout(t); }, [qInput]);
  useEffect(() => {
    const id = ++reqId.current; const ctl = new AbortController();
    setLoading(true); setError('');
    fetchHistory(token, f, cursors[page - 1] ?? null, LIMIT, ctl.signal)
      .then(r => { if (id !== reqId.current) return; setData(r); setExtra([]); setMoreCursor(undefined);
        if (r.next_cursor) setCursors(c => { const n = c.slice(0, page); n[page] = r.next_cursor; return n; }); })
      .catch(e => { if (!ctl.signal.aborted && id === reqId.current) setError(msg(e)); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
    return () => ctl.abort();
  }, [token, f, page, reload, retry]);
  async function loadMore() {
    const cursor = moreCursor === undefined ? data?.next_cursor : moreCursor;
    if (!cursor) return;
    try { setLoading(true); const r = await fetchHistory(token, f, cursor, LIMIT); setExtra(x => [...x, ...r.items]); setMoreCursor(r.next_cursor); }
    catch (e) { setError(msg(e)); } finally { setLoading(false); }
  }
  const rows = [...(data?.items || []), ...extra];
  const filtered = Boolean(f.q.trim() || f.severity || f.target || f.status || f.author || f.from || f.to);
  const extraCount = [f.severity, f.target, f.author, f.from, f.to].filter(Boolean).length;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / LIMIT)) : 1;
  const moreOnPhone = moreCursor === undefined ? data?.has_more : Boolean(moreCursor);
  const fields = <>
    <label className="sc-select"><span>Gravité</span><select value={f.severity} onChange={e => set({severity: e.target.value as HistoryFilters['severity']})}>
      <option value="">Toutes</option>{(Object.keys(SEVERITY) as Severity[]).map(k => <option key={k} value={k}>{SEVERITY[k].label}</option>)}</select></label>
    <label className="sc-select"><span>Cible</span><select value={f.target} onChange={e => set({target: e.target.value as HistoryFilters['target']})}>
      <option value="">Toutes</option>{TARGETS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
    <label className="sc-select"><span>Auteur</span><select value={f.author} onChange={e => set({author: e.target.value})}>
      <option value="">Tous</option>{authors.map(a => <option key={a.id} value={a.id}>{a.full_name}</option>)}</select></label>
    <label className="sc-select cp-date"><span>Du</span><DateInput value={f.from} onChange={e => set({from: e.target.value})} aria-label="Envoyées à partir du"/></label>
    <label className="sc-select cp-date"><span>Au</span><DateInput value={f.to} onChange={e => set({to: e.target.value})} aria-label="Envoyées jusqu’au"/></label>
  </>;
  return <div className="sc cp">
    <header className="sc-head">
      <div><h2>Notifications système</h2><p>Notification interne à l’application : aucun SMS, WhatsApp ni e-mail.</p></div>
      <div className="sc-head-actions"><OnlineActionButton type="button" className="sc-btn sc-btn-primary" onClick={onNew}><NavGlyph g="plus" size={16}/><span>Nouvelle notification</span></OnlineActionButton></div>
    </header>
    <div className="sc-toolbar sc-search-open">
      <label className="sc-search"><NavGlyph g="search" size={17}/>
        <input type="search" value={qInput} onChange={e => setQInput(e.target.value)} placeholder="Titre ou auteur" aria-label="Rechercher une notification" maxLength={80}/>
        {loading && qInput !== '' && <i className="sc-spin" aria-hidden="true"/>}
        {qInput && <button type="button" className="sc-clear" aria-label="Effacer la recherche" onClick={() => setQInput('')}><NavGlyph g="close" size={15}/></button>}
      </label>
      <div className="sc-chips" role="group" aria-label="Statut">
        {([['', 'Toutes'], ['ACTIVE', 'Actives'], ['EXPIRED', 'Expirées']] as const).map(([v, l]) => <button key={l} type="button" className="sc-chip" aria-pressed={f.status === v} onClick={() => set({status: v})}>{l}</button>)}
      </div>
      <div className="sc-filters sc-hide-phone cp-filters">{fields}</div>
      <button type="button" className="sc-btn sc-btn-ghost sc-only-phone sc-filter-btn" onClick={() => setSheet(true)}><NavGlyph g="sliders" size={16}/>Filtrer{extraCount ? <b className="sc-dot" aria-label="filtre actif"/> : null}</button>
    </div>
    <div className="sc-summary" role="status" aria-live="polite">
      {data ? <span><b>{data.total.toLocaleString('fr-FR')}</b> notification{data.total > 1 ? 's' : ''}{filtered ? ' correspondante' + (data.total > 1 ? 's' : '') : ' envoyée' + (data.total > 1 ? 's' : '')}</span> : <i className="sc-skel sc-skel-line" aria-hidden="true"/>}
      {filtered && <button type="button" className="sc-link" onClick={() => { setQInput(''); set({...EMPTY}); }}>Réinitialiser les filtres</button>}
    </div>
    {error ? <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Impossible de charger l’historique.</b><small>{error}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setRetry(k => k + 1)}>Réessayer</button></div>
      : !data && loading ? <div className="sc-list" aria-busy="true" aria-label="Chargement de l’historique">{Array.from({length: 5}).map((_, i) => <div key={i} className="sc-row cp-row sc-row-skel">
          <span><i className="sc-skel" style={{width: '70%'}}/><i className="sc-skel" style={{width: '40%'}}/></span><span><i className="sc-skel" style={{width: 90}}/></span>
          <span className="cp-col-target"><i className="sc-skel" style={{width: '60%'}}/></span><span className="cp-col-reads"><i className="sc-skel" style={{width: 50}}/></span><span><i className="sc-skel" style={{width: 60}}/></span><span/></div>)}</div>
      : rows.length === 0 ? <div className="sc-empty"><NavGlyph g={f.q ? 'search' : 'bell'} size={24}/>
          <b>{f.q.trim() ? `Aucun résultat pour « ${f.q.trim()} ».` : filtered ? 'Aucune notification ne correspond à ces filtres.' : 'Aucune notification envoyée pour le moment.'}</b>
          {!filtered && <OnlineActionButton type="button" className="sc-btn sc-btn-primary" onClick={onNew}><NavGlyph g="plus" size={16}/>Créer la première notification</OnlineActionButton>}</div>
      : <div className={`sc-list ${loading ? 'sc-busy' : ''}`} role="table" aria-label="Historique des notifications">
        <div className="sc-row cp-row sc-row-head" role="row"><span role="columnheader">Notification</span><span role="columnheader">Gravité</span>
          <span role="columnheader" className="cp-col-target">Cible</span><span role="columnheader" className="cp-col-reads">Lues</span><span role="columnheader">Statut</span><span role="columnheader"><span className="es-sr">Ouvrir</span></span></div>
        {rows.map(c => <div key={c.id} className="sc-row cp-row" role="row" tabIndex={0} aria-label={`${c.title}, ${SEVERITY[c.severity].label}, ${TARGET_LABEL[c.target_scope] || c.target_scope}, ${c.status === 'ACTIVE' ? 'active' : 'expirée'}. Ouvrir le détail`}
          onClick={() => onOpen(c.id)} onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); onOpen(c.id); } }}>
          <span role="cell" className="cp-col-title"><b>{c.title}</b><small>{shortDate(c.created_at)}{c.author ? ` · ${c.author}` : ''}</small></span>
          <span role="cell" className="cp-col-sev"><SeverityBadge s={c.severity}/></span>
          <span role="cell" className="cp-col-target"><b>{TARGET_LABEL[c.target_scope] || c.target_scope}</b><small>{c.recipient_count.toLocaleString('fr-FR')} destinataire(s)</small></span>
          <span role="cell" className="cp-col-reads"><b>{c.read_count.toLocaleString('fr-FR')}</b><small>/ {c.recipient_count.toLocaleString('fr-FR')}</small></span>
          <span role="cell" className="cp-col-status"><StatusBadge s={c.status}/>{c.expires_at && <small>{c.status === 'ACTIVE' ? 'expire' : 'expirée'} le {shortDate(c.expires_at)}</small>}</span>
          <span role="cell" className="cp-col-chev" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span>
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
    {sheet && <div className="sc-fsheet-backdrop mobileSheetBackdrop" onMouseDown={e => e.currentTarget === e.target && setSheet(false)}>
      <div className="sc-fsheet" role="dialog" aria-modal="true" aria-label="Filtrer les notifications">
        <div className="sc-fsheet-head mobileSheetHead"><b>Filtrer</b><button type="button" aria-label="Fermer" onClick={() => setSheet(false)}><NavGlyph g="close" size={18}/></button></div>
        <div className="cp-sheet-fields">{fields}</div>
        <button type="button" className="sc-btn sc-btn-primary sc-block" onClick={() => setSheet(false)}>Voir {data ? data.total.toLocaleString('fr-FR') : ''} notification(s)</button>
      </div></div>}
  </div>;
}

/* ---------------------------------------------------------------- detail (read only) */
function CampaignDetailView({token, id, onBack, onDuplicate}: {token: string; id: string; onBack: () => void; onDuplicate: (p: Prefill) => void}) {
  const [d, setD] = useState<CampaignDetail | null>(null); const [error, setError] = useState(''); const [nonce, setNonce] = useState(0);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { const ctl = new AbortController(); setError(''); fetchCampaign(token, id, ctl.signal).then(setD).catch(e => { if (!ctl.signal.aborted) setError(msg(e)); }); return () => ctl.abort(); }, [token, id, nonce]);
  useEffect(() => { if (d) title.current?.focus({preventScroll: true}); }, [d?.id]);
  const backBtn = <PageTrail parents={[{label: 'Notifications système', onSelect: onBack}]} current={'Détail de notification'}/>;
  if (error) return <div className="sc-sheet-page">{backBtn}<div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Détail indisponible.</b><small>{error}</small></div>
    <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setNonce(n => n + 1)}>Réessayer</button></div></div>;
  if (!d) return <div className="sc-sheet-page" aria-busy="true">{backBtn}<div className="sc-card"><i className="sc-skel" style={{width: '50%', height: 22}}/><i className="sc-skel" style={{width: '80%'}}/></div></div>;
  const t = d.target;
  const pct = d.recipient_count ? Math.round(100 * d.read_count / d.recipient_count) : 0;
  return <div className="sc-sheet-page">
    {backBtn}
    <header className="sc-card sc-sheet-head">
      <div className="sc-sheet-id"><span className={`sc-sheet-logo cp-logo cp-logo-${d.severity.toLowerCase()}`} aria-hidden="true"><NavGlyph g={SEVERITY[d.severity].icon} size={24}/></span>
        <div><h2 ref={title} tabIndex={-1}>{d.title}</h2><p>Envoyée le {fullDate(d.created_at)}{d.author ? ` par ${d.author}` : ''}</p>
          <div className="sc-badges"><SeverityBadge s={d.severity}/><StatusBadge s={d.status}/></div></div></div>
      <div className="sc-sheet-actions"><button type="button" className="sc-btn sc-btn-ghost" onClick={() => onDuplicate({title: d.title, body: d.body, severity: d.severity, link: d.link_path || '',
        target: d.target_json || {type: d.target_scope as TargetType, school_ids: [], role_code: null, user_id: null}})}><NavGlyph g="layers" size={16}/>Dupliquer</button></div>
    </header>
    <section className="sc-summary-grid cp-summary" aria-label="Synthèse">
      <div className="sc-stat"><small>Destinataires</small><b>{d.recipient_count.toLocaleString('fr-FR')}</b><em>{d.people_count != null ? `${d.people_count.toLocaleString('fr-FR')} personne(s)` : 'Personnes : non mesuré'}</em></div>
      <div className="sc-stat"><small>Lues</small><b>{d.read_count.toLocaleString('fr-FR')}</b><em>{pct} % des destinataires</em></div>
      <div className={`sc-stat ${d.status === 'ACTIVE' ? 'sc-ok' : 'sc-warn'}`}><small>Statut</small><b>{d.status === 'ACTIVE' ? 'Active' : 'Expirée'}</b><em>{d.expires_at ? `${d.status === 'ACTIVE' ? 'Expire' : 'Expirée'} le ${fullDate(d.expires_at)}` : 'Sans expiration'}</em></div>
    </section>
    <div className="sc-sheet-grid">
      <section className="sc-card"><h3>Message</h3><p className="cp-body">{d.body}</p>
        {d.link_path && <p className="cp-link-line"><NavGlyph g="external" size={14}/>Lien interne : <code>{d.link_path}</code></p>}
        <p className="sc-hint">Une notification envoyée n’est jamais modifiée : « Dupliquer » prépare une nouvelle notification.</p></section>
      <section className="sc-card"><h3>Cible</h3>
        <dl className="sc-dl"><dt>Type</dt><dd>{TARGET_LABEL[t.type] || t.type}</dd>
          {t.role && <><dt>Rôle</dt><dd>{t.role}</dd></>}
          {t.user && <><dt>Personne</dt><dd>{t.user}</dd></>}
          {t.schools && <><dt>Écoles</dt><dd>{t.schools.map(s => s.name).join(', ')}{(t.schools_total || 0) > t.schools.length ? ` et ${(t.schools_total || 0) - t.schools.length} autre(s)` : ''}</dd></>}
          {t.type === 'SCHOOL_ROLE' && !t.schools && <><dt>Portée</dt><dd>Toutes les écoles actives</dd></>}
          <dt>Audience</dt><dd>Déterminée au moment de l’envoi ; un compte ajouté plus tard à la cible ne la reçoit pas.</dd>
          {d.audit_event_id && <><dt>Audit</dt><dd>Événement « notification envoyée » <code className="cp-ref">{d.audit_event_id.slice(0, 8)}</code>, consultable dans le Journal d’audit.</dd></>}
        </dl></section>
    </div>
  </div>;
}

/* ---------------------------------------------------------------- composer */
type Pick = {id: string; label: string; sub?: string};

function SearchPicker({label, placeholder, search, value, onPick, multiple = false, disabled}: {label: string; placeholder: string;
  search: (q: string, signal: AbortSignal) => Promise<Pick[]>; value: Pick[]; onPick: (v: Pick[]) => void; multiple?: boolean; disabled?: boolean}) {
  const [q, setQ] = useState(''); const [items, setItems] = useState<Pick[] | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (disabled) return;
    const ctl = new AbortController(); setLoading(true);
    const t = window.setTimeout(() => { setError(''); search(q.trim(), ctl.signal).then(setItems).catch(e => { if (!ctl.signal.aborted) setError(msg(e)); }).finally(() => setLoading(false)); }, 300);
    return () => { window.clearTimeout(t); ctl.abort(); };
  }, [q, disabled, retry]);
  const chosen = new Set(value.map(v => v.id));
  return <div className="cp-picker">
    <label className="sc-field"><span className="cp-picker-label">{label}</span>
      <input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder} disabled={disabled} maxLength={80} aria-label={label}/></label>
    {value.length > 0 && <div className="cp-chosen" aria-label="Sélection">{value.map(v => <span key={v.id} className="cp-chip">{v.label}
      <button type="button" aria-label={`Retirer ${v.label}`} onClick={() => onPick(value.filter(x => x.id !== v.id))}><NavGlyph g="close" size={12}/></button></span>)}</div>}
    {error ? <div className="sc-error" role="alert"><NavGlyph g="alert" size={16}/><div><b>Chargement impossible.</b><small>{error}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setRetry(k => k + 1)}>Réessayer</button></div>
      : items === null || (loading && !items.length) ? <div className="cp-options" aria-busy="true"><i className="sc-skel" style={{width: '70%'}}/><i className="sc-skel" style={{width: '55%'}}/></div>
      : items.length === 0 ? <p className="sc-muted cp-none">{q ? 'Aucun résultat.' : 'Aucun élément actif.'}</p>
      : <ul className="cp-options" role="listbox" aria-multiselectable={multiple} aria-label={label}>{items.map(it => <li key={it.id}>
        <button type="button" role="option" aria-selected={chosen.has(it.id)} className={chosen.has(it.id) ? 'cp-opt-on' : ''}
          onClick={() => onPick(multiple ? (chosen.has(it.id) ? value.filter(v => v.id !== it.id) : [...value, it]) : [it])}>
          <span><b>{it.label}</b>{it.sub && <small>{it.sub}</small>}</span>{chosen.has(it.id) && <NavGlyph g="check" size={16}/>}</button></li>)}</ul>}
  </div>;
}

function Composer({token, canTeam, prefill, onClose, onSent}: {token: string; canTeam: boolean; prefill: Prefill | null; onClose: () => void; onSent: (id: string) => void}) {
  const [step, setStep] = useState<0 | 1 | 2 | 3>(0);
  const [type, setType] = useState<TargetType>(prefill?.target.type && (canTeam || !prefill.target.type.startsWith('PLATFORM')) ? prefill.target.type : 'ALL_ACTIVE_SCHOOLS');
  const [schools, setSchools] = useState<Pick[]>([]);
  const [member, setMember] = useState<Pick[]>([]);
  const [role, setRole] = useState(prefill?.target.role_code || '');
  const [schoolRoles, setSchoolRoles] = useState<{code: string; label: string}[] | null>(null);
  const [platformRoles, setPlatformRoles] = useState<{code: string; label: string}[] | null>(null);
  const [title, setTitle] = useState(prefill?.title || ''); const [body, setBody] = useState(prefill?.body || '');
  const [severity, setSeverity] = useState<Severity>(prefill?.severity || 'INFO');
  const [link, setLink] = useState(prefill?.link || ''); const [expires, setExpires] = useState('');
  const [audience, setAudience] = useState<Audience | null>(null); const [audErr, setAudErr] = useState(''); const [estimating, setEstimating] = useState(false);
  const [ack, setAck] = useState(false); const [changed, setChanged] = useState<string>('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());   // one key per composition: a double click or a lost response never sends twice
  useEffect(() => { platformRbacRoles(token).then(r => setSchoolRoles(r)).catch(() => setSchoolRoles([])); if (canTeam) teamRoles(token).then(r => setPlatformRoles(r.items.filter(x => x.status === 'ACTIVE'))).catch(() => setPlatformRoles([])); }, [token]);
  const target: Target = {type, school_ids: ['SCHOOLS', 'SCHOOL_ROLE', 'SCHOOL_USER'].includes(type) ? schools.map(s => s.id) : [],
    role_code: ['SCHOOL_ROLE', 'PLATFORM_ROLE'].includes(type) ? role || null : null,
    user_id: ['SCHOOL_USER', 'PLATFORM_USER'].includes(type) ? member[0]?.id || null : null};
  const individual = type === 'SCHOOL_USER' || type === 'PLATFORM_USER';
  const def = TARGETS.find(t => t.value === type)!;
  function targetReady(): string {
    if (type === 'SCHOOLS' && !schools.length) return 'Choisissez au moins une école.';
    if ((type === 'SCHOOL_ROLE' || type === 'PLATFORM_ROLE') && !role) return 'Choisissez le rôle.';
    if (type === 'SCHOOL_USER' && (schools.length !== 1 || !member.length)) return 'Choisissez l’école puis le membre.';
    if (type === 'PLATFORM_USER' && !member.length) return 'Choisissez le membre de l’équipe.';
    return '';
  }
  async function estimate() {
    setEstimating(true); setAudErr(''); setAudience(null);
    try { const a = await previewAudience(token, target); setAudience(a); return a; } catch (e) { setAudErr(msg(e)); return null; } finally { setEstimating(false); }
  }
  async function next() {
    setError('');
    if (step === 0) { const why = targetReady(); if (why) { setError(why); return; } const a = await estimate(); if (!a || a.deliveries === 0) return; setStep(1); return; }
    if (step === 1) {
      if (title.trim().length < 2) { setError('Le titre est obligatoire (2 caractères minimum, hors espaces).'); return; }
      if (body.trim().length < 2) { setError('Le message est obligatoire (2 caractères minimum, hors espaces).'); return; }
      setStep(2); return;
    }
    if (step === 2) {
      if (link && (!/^\/[A-Za-z0-9/_?=&.-]*$/.test(link) || link.startsWith('//'))) { setError('Lien interne uniquement : un chemin commençant par « / » (aucune adresse externe).'); return; }
      if (expires && new Date(expires).getTime() <= Date.now()) { setError('L’expiration doit être dans le futur.'); return; }
      setAck(false); await estimate(); setStep(3);
    }
  }
  async function send() {
    setError('');
    if (!audience || audience.deliveries === 0) { setError('Aucun destinataire ne correspond actuellement à cette cible.'); return; }
    if (!individual && !ack) { setError('Cochez la confirmation d’envoi.'); return; }
    setBusy(true);
    try {
      const r = await sendCampaign(token, key.current, {title: title.trim(), body: body.trim(), severity, target, link_path: link || null,
        expires_at: expires ? new Date(expires).toISOString() : null, confirmed_recipients: individual ? null : audience.deliveries});
      toast.success(`Notification envoyée à ${r.recipient_count.toLocaleString('fr-FR')} destinataire(s). Aucun SMS n’est envoyé.`);
      onSent(r.id);
    } catch (e) {
      if (e instanceof AudienceChangedError) { setAudience({...audience, ...e.audience}); setAck(false); setChanged(e.message); key.current = crypto.randomUUID(); }
      else setError(msg(e));
    } finally { setBusy(false); }
  }
  const preview: InboxItem = {id: 'preview', category: `SYSTEM_${severity}`, severity, title: title.trim() || 'Titre', body: body.trim() || 'Message', link_path: link || null,
    created_at: new Date().toISOString(), read_at: null, expires_at: expires ? new Date(expires).toISOString() : null};
  const audLine = audience && (audience.deliveries === 0 ? audience.message || 'Aucun destinataire ne correspond actuellement à cette cible.'
    : `${audience.deliveries.toLocaleString('fr-FR')} destinataire(s)${audience.people !== audience.deliveries ? ` · ${audience.people.toLocaleString('fr-FR')} personne(s) (un compte de plusieurs écoles la voit dans chacune)` : ''}${audience.schools ? ` · ${audience.schools.toLocaleString('fr-FR')} école(s)` : ''}`);
  return <Modal title="Nouvelle notification" subtitle="Notification interne à l’application. Aucun SMS, WhatsApp ni e-mail n’est envoyé." onClose={onClose} wide>
    <div className="cp-wizard">
      <ol className="cp-steps" aria-label="Étapes">{['Destinataires', 'Contenu', 'Options', 'Aperçu'].map((l, i) => <li key={l} className={step === i ? 'cp-step-on' : step > i ? 'cp-step-done' : ''} aria-current={step === i ? 'step' : undefined}><span>{i + 1}</span>{l}</li>)}</ol>
      {step === 0 && <div className="sc-form">
        <fieldset className="cp-targets"><legend>Destinataires</legend>
          {TARGETS.filter(t => !t.team || canTeam).map(t => <label key={t.value} className={type === t.value ? 'cp-on' : ''}>
            <input type="radio" name="cp-target" checked={type === t.value} onChange={() => { setType(t.value); setSchools([]); setMember([]); setRole(''); setAudience(null); setAudErr(''); }}/>
            <span><b>{t.label}</b><small>{t.hint}</small></span></label>)}
        </fieldset>
        {(type === 'SCHOOLS' || type === 'SCHOOL_ROLE') && <SearchPicker label={type === 'SCHOOLS' ? 'Écoles *' : 'Limiter à ces écoles (facultatif : sinon toutes les écoles actives)'}
          placeholder="Nom ou code de l’école" multiple value={schools} onPick={v => { setSchools(v); setAudience(null); }}
          search={(q, signal) => fetchSchools(token, {q, status: 'ACTIVE', config: '', sort: 'name'}, null, 10, signal).then(r => r.items.map(s => ({id: s.id, label: s.name, sub: s.code})))}/>}
        {type === 'SCHOOL_ROLE' && <div className="sc-field"><label htmlFor="cp-srole">Rôle école *</label>
          {schoolRoles === null ? <i className="sc-skel" style={{width: '60%'}}/> : <select id="cp-srole" value={role} onChange={e => { setRole(e.target.value); setAudience(null); }}>
            <option value="">Choisir…</option>{schoolRoles.map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select>}</div>}
        {type === 'SCHOOL_USER' && <>
          <SearchPicker label="1. École *" placeholder="Nom ou code de l’école" value={schools} onPick={v => { setSchools(v); setMember([]); setAudience(null); }}
            search={(q, signal) => fetchSchools(token, {q, status: 'ACTIVE', config: '', sort: 'name'}, null, 10, signal).then(r => r.items.map(s => ({id: s.id, label: s.name, sub: s.code})))}/>
          {schools.length === 1 && <SearchPicker key={schools[0].id} label={`2. Membre de ${schools[0].label} *`} placeholder="Nom ou e-mail" value={member} onPick={v => { setMember(v); setAudience(null); }}
            search={(q, signal) => fetchIdentities(token, {q, scope: 'SCHOOL', status: '', schoolId: schools[0].id, schoolName: schools[0].label, role: '', activeOnly: true}, null, 10, signal)
              .then(r => r.items.map(u => ({id: u.id, label: u.full_name, sub: `${u.email}${u.school_roles[0] ? ` · ${u.school_roles[0]}` : ''}`})))}/>}
        </>}
        {type === 'PLATFORM_ROLE' && <div className="sc-field"><label htmlFor="cp-prole">Rôle plateforme *</label>
          {platformRoles === null ? <i className="sc-skel" style={{width: '60%'}}/> : <select id="cp-prole" value={role} onChange={e => { setRole(e.target.value); setAudience(null); }}>
            <option value="">Choisir…</option>{platformRoles.map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select>}</div>}
        {type === 'PLATFORM_USER' && <SearchPicker label="Membre de l’équipe *" placeholder="Nom ou e-mail" value={member} onPick={v => { setMember(v); setAudience(null); }}
          search={(q, signal) => fetchMembers(token, {q, status: 'ACTIVE', role: ''}, null, 10, signal).then(r => r.items.map(u => ({id: u.id, label: u.full_name, sub: `${u.email} · ${u.role_labels.join(', ')}`})))}/>}
        <p className="sc-hint"><NavGlyph g="info" size={12}/> {def.hint} Comptes suspendus ou désactivés et écoles inactives exclus.</p>
        {estimating && <p className="cp-aud" aria-busy="true"><i className="sc-spin" aria-hidden="true"/>Estimation des destinataires…</p>}
        {audErr && <div className="sc-error" role="alert"><NavGlyph g="alert" size={16}/><div><b>Impossible d’estimer les destinataires.</b><small>{audErr}</small></div>
          <button type="button" className="sc-btn sc-btn-ghost" onClick={() => void estimate()}>Réessayer</button></div>}
        {audience && <p className={`cp-aud ${audience.deliveries === 0 ? 'cp-aud-zero' : ''}`} role="status"><NavGlyph g={audience.deliveries ? 'users' : 'alert'} size={15}/>{audLine}</p>}
      </div>}
      {step === 1 && <div className="sc-form">
        <div className="sc-form-row">
          <div className="sc-field"><label htmlFor="cp-title">Titre *</label><input id="cp-title" value={title} onChange={e => setTitle(e.target.value)} maxLength={180}/><small className="cp-count">{title.trim().length}/180</small></div>
          <fieldset className="cp-sev-pick"><legend>Gravité</legend>{(Object.keys(SEVERITY) as Severity[]).map(k => <label key={k} className={severity === k ? 'cp-on' : ''}>
            <input type="radio" name="cp-sev" checked={severity === k} onChange={() => setSeverity(k)}/><NavGlyph g={SEVERITY[k].icon} size={14}/>{SEVERITY[k].label}</label>)}</fieldset>
        </div>
        <div className="sc-field"><label htmlFor="cp-body">Message *</label><textarea id="cp-body" rows={6} value={body} onChange={e => setBody(e.target.value)} maxLength={2000}/>
          <small className="cp-count">{body.trim().length}/2000 · texte simple, retours à la ligne conservés</small></div>
      </div>}
      {step === 2 && <div className="sc-form">
        <div className="sc-field"><label htmlFor="cp-link">Lien interne (facultatif)</label><input id="cp-link" value={link} onChange={e => setLink(e.target.value)} placeholder="/aide/paiements" maxLength={200}/>
          <small className="sc-hint">Chemin dans EduSync commençant par « / ». Le destinataire n’y accède que s’il en a le droit.</small></div>
        <div className="sc-field"><label htmlFor="cp-exp">Expiration (facultatif)</label><input id="cp-exp" type="datetime-local" value={expires} onChange={e => setExpires(e.target.value)} className="cp-dt"/>
          <small className="sc-hint">Heure locale{tzName ? ` (${tzName})` : ''}. Après cette date, la notification disparaît des cloches mais reste dans l’historique.</small></div>
      </div>}
      {step === 3 && <div className="cp-review">
        <dl className="sc-dl"><dt>Cible</dt><dd>{TARGET_LABEL[type]}{schools.length ? ` · ${schools.map(s => s.label).join(', ')}` : ''}{role ? ` · ${(type === 'SCHOOL_ROLE' ? schoolRoles : platformRoles)?.find(r => r.code === role)?.label || role}` : ''}{member[0] ? ` · ${member[0].label}` : ''}</dd>
          <dt>Destinataires</dt><dd>{estimating ? 'Estimation…' : audLine}</dd>
          <dt>Gravité</dt><dd><SeverityBadge s={severity}/></dd><dt>Titre</dt><dd>{title.trim()}</dd>
          <dt>Lien interne</dt><dd>{link || '—'}</dd><dt>Expiration</dt><dd>{expires ? fullDate(new Date(expires).toISOString()) : 'Sans expiration'}</dd></dl>
        <div className="cp-preview"><p className="cp-preview-h">Aperçu dans la cloche du destinataire</p><ul className="nc-list"><BellItem n={preview} onRead={() => undefined} canRead={false}/></ul></div>
        {changed && <div className="es-alert es-alert-warn" role="alert">{changed}</div>}
        {!individual && audience && audience.deliveries > 0 && <label className="cp-ack"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/>
          <span><b>Vous êtes sur le point d’envoyer cette notification à {audience.deliveries.toLocaleString('fr-FR')} destinataire(s){audience.schools ? ` dans ${audience.schools.toLocaleString('fr-FR')} école(s)` : ''}.</b>
            <small>L’audience est recalculée au moment de l’envoi ; elle ne dépassera jamais ce nombre sans nouvelle confirmation.</small></span></label>}
      </div>}
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot">
        <button type="button" className="es-btn es-btn-ghost" onClick={() => { setError(''); if (step === 0) onClose(); else setStep((step - 1) as 0 | 1 | 2); }}>{step === 0 ? 'Annuler' : 'Retour'}</button>
        {step < 3 ? <OnlineActionButton type="button" className="es-btn es-btn-primary" disabled={estimating || (step === 0 && audience?.deliveries === 0)} onClick={() => void next()}>Continuer</OnlineActionButton>
          : <OnlineActionButton type="button" className="es-btn es-btn-primary" disabled={busy || estimating || !audience?.deliveries} onClick={() => void send()}>{busy ? 'Envoi…' : individual ? 'Envoyer la notification' : 'Confirmer l’envoi'}</OnlineActionButton>}
      </div>
    </div>
  </Modal>;
}
