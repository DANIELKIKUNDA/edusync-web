import {OnlineActionButton} from './online_action';
import {PageTrail} from './navigation';
import React, {useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {Modal} from './account';
import {friendlyError, UserFacingError} from './errors';
import {auditActionLabel, resultLabel} from './labels';
import {NavGlyph} from './nav_icons';
import {bootstrapAdmin, CONFIG_LABEL, createSchool, fetchCitySuggestions, fetchSchoolSheet, RDC_PROVINCES, resetAdminAccess, setMembershipActive, setSchoolStatus,
  updateSchool, type AdminInfo, type SchoolIdentity, type SchoolSheet} from './schools_api';
import {ConfigBadge, StatusBadge} from './schools';

/* School sheet (lot 2026-10): executive summary first (who, status, configuration, administrator, users, last
   activity, incidents, allowed actions), then identity, promoter / main contact (institutional), administrators
   (technical access — the platform governs only this role), configuration gates and governance history. */

export type SchoolAction = {kind: 'admin' | 'suspend' | 'reactivate' | 'edit'; school: {id: string; name: string; code: string; status: string}};
const msg = (e: unknown) => (e instanceof UserFacingError ? e.message : friendlyError(e));
const when = (iso: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'}) : null;
function ago(iso: string | null) {
  if (!iso) return 'Aucune activité enregistrée';
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return 'À l’instant'; if (mins < 60) return `Il y a ${mins} min`; if (mins < 1440) return `Il y a ${Math.round(mins / 60)} h`;
  if (mins < 43200) return `Il y a ${Math.round(mins / 1440)} j`; return when(iso)!;
}
// The initial administrator is the platform's job; the other gates are completed by the school itself.
const gateLabel = (k: string, ok: boolean, config: string) => k === 'initial_admin'
  ? (!ok ? 'À créer par la plateforme' : config === 'ADMIN_PENDING' ? 'Activation en attente' : 'Prêt')
  : (ok ? 'Prêt' : 'À faire par l’école');
const GATES: Record<string, string> = {school_identity: 'Identité de l’école', initial_admin: 'Administrateur de l’école', academic_year: 'Année scolaire', classes: 'Classes ouvertes', fee_catalog: 'Catalogue des frais'};
const ADMIN_STATE: Record<AdminInfo['state'], string> = {ACTIVE: 'Actif', PENDING: 'Activation en attente', DISABLED: 'Accès désactivé'};

export function SchoolSheetView({token, id, has, onBack, onChanged}: {token: string; id: string; has: (c: string) => boolean; onBack: () => void; onChanged: () => void}) {
  const [d, setD] = useState<SchoolSheet | null>(null);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<null | {kind: 'edit' | 'admin' | 'suspend' | 'reactivate'} | {kind: 'reset' | 'disable'; admin: AdminInfo}>(null);
  const [nonce, setNonce] = useState(0);
  // keyboard and screen-reader users land on the school name when a sheet opens (not after each refresh)
  const title = useRef<HTMLHeadingElement>(null); const focusedFor = useRef('');
  useEffect(() => { if (d && focusedFor.current !== id) { focusedFor.current = id; title.current?.focus({preventScroll: true}); } }, [d, id]);
  useEffect(() => {
    const ctl = new AbortController(); setError('');
    fetchSchoolSheet(token, id, ctl.signal).then(setD).catch(e => { if (!ctl.signal.aborted) setError(msg(e)); });
    return () => ctl.abort();
  }, [token, id, nonce]);
  const refresh = () => { setNonce(n => n + 1); onChanged(); };
  const backBtn = <PageTrail parents={[{label: 'Écoles', onSelect: onBack}]} current={d?.school.name || 'Fiche école'}/>;
  if (error) return <div className="sc-sheet-page">{backBtn}<div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Fiche indisponible.</b><small>{error}</small></div>
    <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setNonce(n => n + 1)}>Réessayer</button></div></div>;
  if (!d) return <div className="sc-sheet-page" aria-busy="true">{backBtn}<div className="sc-card"><i className="sc-skel" style={{width: '50%', height: 22}}/><i className="sc-skel" style={{width: '30%'}}/></div>
    <div className="sc-summary-grid">{Array.from({length: 6}).map((_, i) => <div key={i} className="sc-stat"><i className="sc-skel" style={{width: '60%'}}/><i className="sc-skel" style={{width: '40%', height: 20}}/></div>)}</div></div>;
  const s = d.school; const st = s.status;
  const canEdit = st !== 'DISABLED' && has('platform.schools.update');
  const canAdmin = st !== 'DISABLED' && has('platform.school_admin.bootstrap');
  const actions = [
    canEdit && <OnlineActionButton key="edit" type="button" className="sc-btn sc-btn-ghost" onClick={() => setDialog({kind: 'edit'})}><NavGlyph g="doc" size={16}/>Modifier</OnlineActionButton>,
    canAdmin && <button key="admin" type="button" className={`sc-btn ${d.admins.length === 0 ? 'sc-btn-primary' : 'sc-btn-ghost'}`} onClick={() => setDialog({kind: 'admin'})}>
      <NavGlyph g="key" size={16}/>{d.admins.length === 0 ? 'Créer l’administrateur initial' : d.counters.admins_active === 0 ? 'Remplacer l’administrateur' : 'Ajouter un administrateur'}</button>,
    st === 'ACTIVE' && has('platform.schools.suspend') && <OnlineActionButton key="suspend" type="button" className="sc-btn sc-btn-danger" onClick={() => setDialog({kind: 'suspend'})}>Suspendre</OnlineActionButton>,
    st === 'SUSPENDED' && has('platform.schools.activate') && <OnlineActionButton key="react" type="button" className="sc-btn sc-btn-primary" onClick={() => setDialog({kind: 'reactivate'})}>Réactiver</OnlineActionButton>,
  ].filter(Boolean);
  const h = d.health; const pendingAdmins = d.admins.filter(a => a.state === 'PENDING').length;
  return <div className="sc-sheet-page">
    {backBtn}
    <header className="sc-card sc-sheet-head">
      <div className="sc-sheet-id">
        <span className="sc-sheet-logo" aria-hidden="true">{s.name.split(/\s+/).filter(w => w.length > 2).slice(0, 2).map(w => w[0]).join('').toUpperCase() || 'É'}</span>
        <div><h2 ref={title} tabIndex={-1}>{s.name}</h2><p><span className="sc-code">{s.code}</span>{s.city || s.province ? ` · ${[s.city, s.province].filter(Boolean).join(', ')}` : ''}</p>
          <div className="sc-badges"><StatusBadge status={st}/><ConfigBadge state={d.config_state}/></div></div>
      </div>
      {actions.length > 0 ? <div className="sc-sheet-actions">{actions}</div> : <p className="sc-muted sc-noaction">{st === 'DISABLED' ? 'École désactivée : aucune action disponible depuis la plateforme.' : 'Consultation seule.'}</p>}
    </header>

    {/* pending = created but not yet signed in (temporary password to change or e-mail invitation to accept) */}
    <section className="sc-summary-grid" aria-label="Synthèse">
      <div className={`sc-stat ${h.access_ok ? 'sc-ok' : 'sc-warn'}`}><small>Accès</small><b>{h.access_ok ? 'Opérationnel' : st === 'ACTIVE' && pendingAdmins > 0 ? 'En activation' : st === 'ACTIVE' && d.admins.length === 0 ? 'À ouvrir' : 'À rétablir'}</b>
        <em>{st !== 'ACTIVE' ? `École ${st === 'SUSPENDED' ? 'suspendue' : 'désactivée'}` : h.admin_active ? 'Administrateur actif' : pendingAdmins > 0 ? 'Première connexion de l’administrateur attendue' : 'Aucun administrateur actif'}</em></div>
      <div className={`sc-stat ${d.config_state === 'COMPLETE' ? 'sc-ok' : 'sc-warn'}`}><small>Configuration</small><b>{d.ready_count}/{d.total_gates} étapes</b><em>{CONFIG_LABEL[d.config_state]}</em></div>
      <div className="sc-stat"><small>Utilisateurs actifs</small><b>{d.counters.users_active}</b><em>{d.counters.users_disabled ? `${d.counters.users_disabled} accès désactivé(s)` : 'Aucun accès désactivé'}</em></div>
      <div className="sc-stat"><small>Administrateurs actifs</small><b>{d.counters.admins_active}</b><em>{pendingAdmins ? `${pendingAdmins} en attente d’activation` : 'Aucune activation en attente'}</em></div>
      <div className="sc-stat" title="Dernière activité d’une session ouverte dans l’espace de cette école (tous utilisateurs)."><small>Dernière activité</small><b>{ago(h.last_activity_at)}</b><em>Session utilisateur dans l’espace école</em></div>
      <div className={`sc-stat ${h.open_conflicts ? 'sc-warn' : 'sc-ok'}`}><small>Incidents ouverts</small><b>{h.open_conflicts}</b><em>Conflits de synchronisation</em></div>
    </section>

    <div className="sc-sheet-grid">
      <section className="sc-card"><div className="sc-card-head"><h3>Général</h3></div>
        <dl className="sc-dl">
          <dt>Code EduSync</dt><dd className="sc-code">{s.code}</dd>
          <dt>Province</dt><dd>{s.province || '—'}</dd><dt>Ville</dt><dd>{s.city || '—'}</dd><dt>Adresse</dt><dd>{s.address || '—'}</dd>
          <dt>Téléphone de l’école</dt><dd>{s.phone_display || '—'}</dd><dt>E-mail de l’école</dt><dd>{s.email || '—'}</dd>
          <dt>Créée le</dt><dd>{when(s.created_at)}</dd>
        </dl></section>
      <section className="sc-card"><div className="sc-card-head"><h3>Promoteur / contact principal</h3>{canEdit && <OnlineActionButton type="button" className="sc-link" onClick={() => setDialog({kind: 'edit'})}>Modifier</OnlineActionButton>}</div>
        {s.contact_name ? <dl className="sc-dl"><dt>Nom</dt><dd>{s.contact_name}</dd><dt>Fonction</dt><dd>{s.contact_function || '—'}</dd>
          <dt>Téléphone</dt><dd>{s.contact_phone_display ? <a href={`tel:${s.contact_phone}`}>{s.contact_phone_display}</a> : '—'}</dd>
          <dt>E-mail</dt><dd>{s.contact_email ? <a href={`mailto:${s.contact_email}`}>{s.contact_email}</a> : '—'}</dd></dl>
          : <p className="sc-muted">Aucun contact institutionnel renseigné.{canEdit ? ' Ajoutez le promoteur ou le responsable principal de l’école.' : ''}</p>}
        <p className="sc-hint">Contact institutionnel de la plateforme. Distinct de l’administrateur, qui gère l’accès technique de l’école.</p></section>
    </div>

    <section className="sc-card"><div className="sc-card-head"><h3>Administrateurs / accès</h3>{canAdmin && d.admins.length > 0 && <OnlineActionButton type="button" className="sc-link" onClick={() => setDialog({kind: 'admin'})}>Ajouter</OnlineActionButton>}</div>
      {d.admins.length === 0 ? <div className="sc-callout"><NavGlyph g="key" size={18}/><div><b>Aucun administrateur.</b><small>L’école ne peut pas encore se configurer : créez son administrateur initial.</small></div></div>
        : <ul className="sc-admins">{d.admins.map(a => <li key={a.membership_id}>
          <span className="sc-admin-avatar" aria-hidden="true">{a.full_name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()}</span>
          <div><b>{a.full_name}</b><small>{a.email}</small><small>{a.last_seen_at ? `Dernière connexion : ${ago(a.last_seen_at).toLowerCase()}` : 'Jamais connecté à cette école'}</small></div>
          <span className={`sc-admin-state sc-as-${a.state.toLowerCase()}`}>{ADMIN_STATE[a.state]}</span>
          <div className="sc-admin-actions">
            {a.state !== 'DISABLED' && has('platform.school_admin.bootstrap') && st !== 'DISABLED' && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => setDialog({kind: 'reset', admin: a})}>Réinitialiser l’accès</OnlineActionButton>}
            {a.membership_active && has('platform.access.manage') && <OnlineActionButton type="button" className="sc-btn sc-btn-ghost sc-btn-sm sc-danger-text" onClick={() => setDialog({kind: 'disable', admin: a})}>Désactiver l’accès</OnlineActionButton>}
          </div></li>)}</ul>}
      <p className="sc-hint">La plateforme gouverne uniquement l’administrateur de l’école (continuité et sécurité de l’accès). Les autres rôles — caissier, secrétaire, préfet, enseignant… — se gèrent dans l’espace de l’école.</p>
    </section>

    <div className="sc-sheet-grid">
      <section className="sc-card"><div className="sc-card-head"><h3>Configuration</h3><span className="sc-muted">{d.ready_count}/{d.total_gates}</span></div>
        <ul className="sc-gates">{Object.entries(d.readiness).map(([k, ok]) => <li key={k} className={ok ? 'sc-gate-ok' : ''}><NavGlyph g={ok ? 'checkCircle' : 'clock'} size={17}/>{GATES[k] || k}<em>{gateLabel(k, ok, d.config_state)}</em></li>)}</ul></section>
      {d.history && <section className="sc-card"><div className="sc-card-head"><h3>Historique de gouvernance</h3></div>
        {d.history.length === 0 ? <p className="sc-muted">Aucune opération enregistrée.</p>
          : <ul className="sc-history">{d.history.map(e => <li key={e.id}><span className={`sc-dot2 ${e.result === 'SUCCESS' ? '' : 'sc-dot-warn'}`} aria-hidden="true"/>
            <div><b>{auditActionLabel(e.action)}</b><small>{when(e.occurred_at)} · {e.actor || 'Système'}{e.result !== 'SUCCESS' ? ` · ${resultLabel(e.result)}` : ''}</small>{e.reason && <small className="sc-reason">Motif : {e.reason}</small>}</div></li>)}</ul>}</section>}
    </div>

    {dialog?.kind === 'edit' && <SchoolFormDialog token={token} has={has} initial={d} onClose={() => setDialog(null)} onCreated={() => { setDialog(null); refresh(); }}/>}
    {dialog?.kind === 'admin' && <AdminDialog token={token} school={s} emailAvailable={d.email_invitations_available} replacing={d.admins.length > 0 && d.counters.admins_active === 0} onClose={() => setDialog(null)} onDone={() => { setDialog(null); refresh(); }}/>}
    {(dialog?.kind === 'suspend' || dialog?.kind === 'reactivate') && <StatusDialog token={token} kind={dialog.kind} school={s} onClose={() => setDialog(null)} onDone={() => { setDialog(null); refresh(); }}/>}
    {dialog?.kind === 'reset' && <ResetAccessDialog token={token} schoolId={s.id} admin={dialog.admin} emailAvailable={d.email_invitations_available} onClose={() => setDialog(null)} onDone={refresh}/>}
    {dialog?.kind === 'disable' && <DisableAccessDialog token={token} admin={dialog.admin} onClose={() => setDialog(null)} onDone={() => { setDialog(null); refresh(); }}/>}
  </div>;
}

// ---------------------------------------------------------------- create / edit
const EMPTY: SchoolIdentity = {name: '', province: '', city: '', address: '', email: '', phone: '', contact_name: '', contact_function: '', contact_phone: '', contact_email: ''};
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
function phoneOk(v: string) {
  const raw = v.trim(); if (!raw) return true;
  const digits = raw.replace(/\D/g, '');
  if (raw.startsWith('+') && !raw.startsWith('+243')) return digits.length >= 8 && digits.length <= 15;
  const local = digits.replace(/^00243|^243|^0/, '');
  return local.length === 9 && /^[89]/.test(local);
}

export function SchoolFormDialog({token, has, initial, onClose, onCreated}: {token: string; has: (c: string) => boolean; initial?: SchoolSheet; onClose: () => void; onCreated: (id: string) => void}) {
  const editing = Boolean(initial);
  const [v, setV] = useState<SchoolIdentity>(() => initial ? Object.fromEntries(Object.keys(EMPTY).map(k => [k, ((initial.school as any)[k] ?? '') as string])) as SchoolIdentity : EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof SchoolIdentity, string>>>({});
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [key] = useState(() => crypto.randomUUID());
  const [cities, setCities] = useState<string[]>([]);
  const [showSchoolContact, setShowSchoolContact] = useState(Boolean(initial?.school.phone || initial?.school.email));
  const [created, setCreated] = useState<{id: string; code: string; name: string} | null>(null);
  const [adminFor, setAdminFor] = useState<{id: string; name: string; code: string; status: string} | null>(null);
  useEffect(() => { if (v.province) void fetchCitySuggestions(token, v.province).then(r => setCities(r.cities)); else setCities([]); }, [token, v.province]);
  const set = (k: keyof SchoolIdentity) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => { setV({...v, [k]: e.target.value}); if (errors[k]) setErrors({...errors, [k]: undefined}); };
  function validate() {
    const e: Partial<Record<keyof SchoolIdentity, string>> = {};
    if (v.name.trim().length < 2) e.name = 'Le nom de l’école est obligatoire.';
    if (!v.province) e.province = 'Choisissez la province.';
    if (!phoneOk(v.contact_phone)) e.contact_phone = 'Numéro invalide : 9 chiffres après +243 (ex. : 81 234 5678).';
    if (!phoneOk(v.phone)) e.phone = 'Numéro invalide : 9 chiffres après +243.';
    if (v.contact_email && !EMAIL.test(v.contact_email.trim())) e.contact_email = 'Adresse e-mail invalide.';
    if (v.email && !EMAIL.test(v.email.trim())) e.email = 'Adresse e-mail invalide.';
    setErrors(e);
    const first = Object.keys(e)[0]; if (first) document.getElementById(`sf-${first}`)?.focus();
    return !first;
  }
  async function submit(ev: React.FormEvent) {
    ev.preventDefault(); if (busy || !validate()) return;
    setBusy(true); setError('');
    try {
      if (initial) { await updateSchool(token, initial.school.id, initial.school.version, v); toast.success('École mise à jour'); onCreated(initial.school.id); }
      else { const r = await createSchool(token, key, v); setCreated(r); }
    } catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }
  if (adminFor) return <AdminDialog token={token} school={adminFor} onClose={() => onCreated(adminFor.id)} onDone={() => onCreated(adminFor.id)}/>;
  if (created) return <Modal title="École créée" onClose={() => onCreated(created.id)}>
    <div className="sc-success"><span className="sc-success-icon" aria-hidden="true"><NavGlyph g="checkCircle" size={30}/></span>
      <b>{created.name}</b><p>Code EduSync attribué automatiquement :</p><span className="sc-code sc-code-lg">{created.code}</span>
      <p className="sc-hint">Étape suivante : créer l’administrateur initial. C’est lui qui configurera l’école (année scolaire, classes, frais).</p></div>
    <div className="es-modal-foot">
      <button type="button" className="es-btn es-btn-ghost" onClick={() => onCreated(created.id)}>Ouvrir la fiche</button>
      {has('platform.school_admin.bootstrap') && <OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={() => setAdminFor({...created, status: 'ACTIVE'})}>Créer l’administrateur initial</OnlineActionButton>}
    </div></Modal>;
  const field = (k: keyof SchoolIdentity, label: string, input: React.ReactNode, hint?: string) => <div className={`sc-field ${errors[k] ? 'sc-invalid' : ''}`}>
    <label htmlFor={`sf-${k}`}>{label}</label>{input}{errors[k] ? <small id={`sf-${k}-err`} role="alert">{errors[k]}</small> : hint ? <small className="sc-hint">{hint}</small> : null}</div>;
  const inputProps = (k: keyof SchoolIdentity) => ({id: `sf-${k}`, value: v[k], onChange: set(k), 'aria-invalid': !!errors[k], 'aria-describedby': errors[k] ? `sf-${k}-err` : undefined});
  return <Modal title={editing ? 'Modifier l’école' : 'Nouvelle école'} subtitle={editing ? `${initial!.school.code} · identité et contact principal` : 'Le code EduSync est attribué automatiquement.'} onClose={onClose} wide>
    <form className="sc-form" onSubmit={submit} noValidate>
      <fieldset><legend>École</legend>
        {field('name', 'Nom de l’école *', <input {...inputProps('name')} autoComplete="organization" maxLength={160} placeholder="Ex. : Complexe scolaire Riziki"/>)}
        <div className="sc-form-row">
          {field('province', 'Province *', <select {...inputProps('province')}><option value="">Choisir…</option>{RDC_PROVINCES.map(p => <option key={p} value={p}>{p}</option>)}</select>)}
          {field('city', 'Ville / localité', <><input {...inputProps('city')} list="sf-cities" maxLength={120} placeholder={v.province ? 'Choisir ou saisir' : 'Choisissez d’abord la province'}/>
            <datalist id="sf-cities">{cities.map(c => <option key={c} value={c}/>)}</datalist></>, 'Une localité absente de la liste peut être saisie.')}
        </div>
        {field('address', 'Adresse', <textarea {...inputProps('address')} rows={2} maxLength={300} placeholder="Avenue, numéro, quartier, commune, référence"/>)}
      </fieldset>
      <fieldset><legend>Promoteur / contact principal</legend>
        <div className="sc-form-row">
          {field('contact_name', 'Nom', <input {...inputProps('contact_name')} maxLength={160} autoComplete="name"/>)}
          {field('contact_function', 'Fonction', <input {...inputProps('contact_function')} maxLength={120} placeholder="Ex. : Promoteur, Préfet des études"/>)}
        </div>
        <div className="sc-form-row">
          {field('contact_phone', 'Téléphone du contact', <div className="sc-phone"><span aria-hidden="true">+243</span><input {...inputProps('contact_phone')} inputMode="tel" autoComplete="tel" maxLength={24} placeholder="81 234 5678"/></div>, 'Numéro RDC ; un numéro étranger s’écrit avec son indicatif (+…).')}
          {field('contact_email', 'E-mail du contact', <input {...inputProps('contact_email')} type="email" autoComplete="email" maxLength={320}/>)}
        </div>
      </fieldset>
      <fieldset className="sc-optional"><legend><button type="button" className="sc-link" aria-expanded={showSchoolContact} onClick={() => setShowSchoolContact(x => !x)}>
        {showSchoolContact ? '− ' : '+ '}Coordonnées de l’école (facultatif, en-têtes des documents)</button></legend>
        {showSchoolContact && <div className="sc-form-row">
          {field('phone', 'Téléphone de l’école', <div className="sc-phone"><span aria-hidden="true">+243</span><input {...inputProps('phone')} inputMode="tel" maxLength={24}/></div>)}
          {field('email', 'E-mail de l’école', <input {...inputProps('email')} type="email" maxLength={320}/>)}
        </div>}
      </fieldset>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? (editing ? 'Enregistrement…' : 'Création…') : editing ? 'Enregistrer' : 'Créer l’école'}</OnlineActionButton></div>
    </form>
  </Modal>;
}

// ---------------------------------------------------------------- administrator (initial / additional / replacement)
function OneTimeSecret({value, who}: {value: string; who: string}) {
  return <div className="sc-secret"><p>Mot de passe provisoire de <b>{who}</b> — affiché une seule fois :</p>
    <div className="sc-secret-box"><code>{value}</code><button type="button" className="es-btn es-btn-ghost" onClick={() => { void navigator.clipboard?.writeText(value).then(() => toast.success('Copié')); }}><NavGlyph g="doc" size={15}/>Copier</button></div>
    <p className="sc-hint">Transmettez-le à la personne par un canal sûr. À sa première connexion, elle devra choisir son propre mot de passe. Il n’est enregistré nulle part en clair.</p></div>;
}

export function AdminDialog({token, school, emailAvailable, replacing, onClose, onDone}: {token: string; school: {id: string; name: string; code: string}; emailAvailable?: boolean; replacing?: boolean; onClose: () => void; onDone: () => void}) {
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [delivery, setDelivery] = useState<'TEMPORARY' | 'INVITATION'>('TEMPORARY');
  const [mail, setMail] = useState<boolean>(Boolean(emailAvailable));
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [key] = useState(() => crypto.randomUUID());
  const [result, setResult] = useState<{temporary_password: string | null; account: string; invitation_sent?: boolean} | null>(null);
  useEffect(() => { if (emailAvailable === undefined) void fetchSchoolSheet(token, school.id).then(d => setMail(d.email_invitations_available)).catch(() => undefined); }, []);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (name.trim().length < 2 || !EMAIL.test(email.trim())) { setError('Nom et adresse e-mail valides obligatoires.'); return; }
    setBusy(true);
    try { setResult(await bootstrapAdmin(token, school.id, key, {full_name: name.trim(), email: email.trim().toLowerCase(), delivery})); }
    catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  const title = replacing ? 'Remplacer l’administrateur' : 'Administrateur de l’école';
  if (result) return <Modal title="Administrateur enregistré" subtitle={`${school.name} · ${school.code}`} onClose={onDone}>
    {result.temporary_password ? <OneTimeSecret value={result.temporary_password} who={name}/>
      : result.invitation_sent ? <p>Une invitation a été envoyée à <b>{email}</b>. Le lien permet de choisir le mot de passe ; il expire automatiquement.</p>
      : <p>Ce compte EduSync existait déjà : il est rattaché à l’école comme administrateur, sans changer son mot de passe.</p>}
    <div className="es-modal-foot"><OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={onDone}>Terminé</OnlineActionButton></div></Modal>;
  return <Modal title={title} subtitle={`${school.name} · ${school.code}`} onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      {replacing && <p className="sc-hint">Aucun administrateur n’est actif : le nouvel administrateur rétablira l’accès de l’école. Désactivez ensuite l’ancien accès si nécessaire.</p>}
      <div className="sc-field"><label htmlFor="ad-name">Nom complet *</label><input id="ad-name" value={name} onChange={e => setName(e.target.value)} autoComplete="name" maxLength={180}/></div>
      <div className="sc-field"><label htmlFor="ad-mail">Adresse e-mail *</label><input id="ad-mail" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" maxLength={320}/>
        <small className="sc-hint">Si cette adresse a déjà un compte EduSync, il est simplement rattaché à l’école.</small></div>
      {mail ? <fieldset className="sc-delivery"><legend>Mise en service du compte</legend>
        <label><input type="radio" name="ad-delivery" checked={delivery === 'INVITATION'} onChange={() => setDelivery('INVITATION')}/> Invitation par e-mail (la personne choisit son mot de passe)</label>
        <label><input type="radio" name="ad-delivery" checked={delivery === 'TEMPORARY'} onChange={() => setDelivery('TEMPORARY')}/> Mot de passe provisoire affiché une fois</label></fieldset>
        : <p className="sc-hint">Un mot de passe provisoire sera généré et affiché une seule fois ; il devra être changé à la première connexion.</p>}
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Enregistrement…' : 'Créer l’accès administrateur'}</OnlineActionButton></div>
    </form></Modal>;
}

function ResetAccessDialog({token, schoolId, admin, emailAvailable, onClose, onDone}: {token: string; schoolId: string; admin: AdminInfo; emailAvailable: boolean; onClose: () => void; onDone: () => void}) {
  const [reason, setReason] = useState(''); const [delivery, setDelivery] = useState<'TEMPORARY' | 'INVITATION'>('TEMPORARY');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [result, setResult] = useState<{temporary_password: string | null; sessions_closed: number; invitation_sent: boolean} | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (reason.trim().length < 5) { setError('Indiquez le motif (5 caractères au moins).'); return; }
    setBusy(true); setError('');
    try { setResult(await resetAdminAccess(token, schoolId, admin.membership_id, {reason: reason.trim(), delivery})); onDone(); } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  if (result) return <Modal title="Accès réinitialisé" subtitle={admin.full_name} onClose={onClose}>
    {result.temporary_password ? <OneTimeSecret value={result.temporary_password} who={admin.full_name}/> : <p>Un lien a été envoyé à <b>{admin.email}</b>.</p>}
    <p className="sc-hint">{result.sessions_closed} session(s) ouverte(s) fermée(s) : les appareils perdus ou compromis n’ont plus accès.</p>
    <div className="es-modal-foot"><OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={onClose}>Terminé</OnlineActionButton></div></Modal>;
  return <Modal title="Réinitialiser l’accès" subtitle={`${admin.full_name} · ${admin.email}`} onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      <p className="sc-hint">Pour un administrateur qui a perdu son téléphone ou son mot de passe, ou dont le compte est compromis : toutes ses sessions sont fermées et un nouvel accès est délivré. Un code de confirmation peut vous être demandé.</p>
      <div className="sc-field"><label htmlFor="ra-reason">Motif *</label><textarea id="ra-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)} maxLength={500} placeholder="Ex. : téléphone perdu, mot de passe oublié"/></div>
      {emailAvailable && <fieldset className="sc-delivery"><legend>Nouvel accès</legend>
        <label><input type="radio" name="ra-delivery" checked={delivery === 'TEMPORARY'} onChange={() => setDelivery('TEMPORARY')}/> Mot de passe provisoire affiché une fois</label>
        <label><input type="radio" name="ra-delivery" checked={delivery === 'INVITATION'} onChange={() => setDelivery('INVITATION')}/> Lien par e-mail</label></fieldset>}
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Réinitialisation…' : 'Réinitialiser'}</OnlineActionButton></div>
    </form></Modal>;
}

function DisableAccessDialog({token, admin, onClose, onDone}: {token: string; admin: AdminInfo; onClose: () => void; onDone: () => void}) {
  const [reason, setReason] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (reason.trim().length < 3) { setError('Indiquez le motif.'); return; }
    setBusy(true); setError('');
    try { await setMembershipActive(token, admin.membership_id, false, reason.trim()); toast.success('Accès désactivé'); onDone(); } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title="Désactiver l’accès" subtitle={`${admin.full_name} · ${admin.email}`} onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      <p className="sc-hint">La personne ne pourra plus ouvrir l’espace de cette école (départ, révocation). Son compte EduSync et l’historique sont conservés ; l’accès peut être réactivé.</p>
      <div className="sc-field"><label htmlFor="da-reason">Motif *</label><textarea id="da-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/></div>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton className="es-btn es-btn-danger" disabled={busy}>{busy ? 'Désactivation…' : 'Désactiver l’accès'}</OnlineActionButton></div>
    </form></Modal>;
}

export function StatusDialog({token, kind, school, onClose, onDone}: {token: string; kind: 'suspend' | 'reactivate'; school: {id: string; name: string; code: string}; onClose: () => void; onDone: () => void}) {
  const [reason, setReason] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (kind === 'suspend' && reason.trim().length < 3) { setError('Le motif de suspension est obligatoire.'); return; }
    setBusy(true); setError('');
    try { await setSchoolStatus(token, school.id, kind, reason.trim()); toast.success(kind === 'suspend' ? 'École suspendue' : 'École réactivée'); onDone(); } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title={kind === 'suspend' ? 'Suspendre l’école' : 'Réactiver l’école'} subtitle={`${school.name} · ${school.code}`} onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      {kind === 'suspend' ? <><p className="sc-hint">Tous les accès de l’école sont fermés immédiatement (sessions ouvertes comprises) jusqu’à la réactivation. Les données sont conservées. Un code de confirmation peut vous être demandé.</p>
        <div className="sc-field"><label htmlFor="st-reason">Motif *</label><textarea id="st-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/></div></>
        : <p className="sc-hint">L’école retrouve l’accès à EduSync selon ses comptes et son état de configuration. L’opération est tracée.</p>}
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <button className={`es-btn ${kind === 'suspend' ? 'es-btn-danger' : 'es-btn-primary'}`} disabled={busy}>{busy ? 'Traitement…' : kind === 'suspend' ? 'Confirmer la suspension' : 'Réactiver'}</button></div>
    </form></Modal>;
}
