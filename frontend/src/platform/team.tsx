import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {
  teamAssignRole, teamCapabilities, teamCloneRole, teamCreateRole, teamCreateUser, teamResetMfa, teamResetPassword, teamRevokeRole,
  teamRevokeSessions, teamRoleStatus, teamRoles, teamUpdateRole, teamUser, teamUserStatus, teamUsers,
  type PlatformCapability, type PlatformRole, type PlatformTeamUser, type PlatformTeamUserDetail,
} from '../api';
import {Modal} from './account';
import {promptText} from './dialogs';
import {friendlyError} from './errors';
import {auditActionLabel} from './labels';
import {NavGlyph} from './nav_icons';
import './team.css';

const ROLE_STATUS: Record<string, string> = {DRAFT: 'Brouillon', OWNER_APPROVED: 'Approuvé', ACTIVE: 'Actif', ARCHIVED: 'Archivé'};
const RISK: Record<string, string> = {LOW: 'Faible', MEDIUM: 'Modéré', HIGH: 'Élevé', CRITICAL: 'Critique'};

function when(iso: string | null) {
  if (!iso) return 'Jamais';
  const d = new Date(iso); const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 2) return 'À l’instant';
  if (mins < 60) return `Il y a ${mins} min`;
  if (mins < 60 * 24) return `Il y a ${Math.round(mins / 60)} h`;
  return d.toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'});
}

async function reason(title: string, message?: string) {
  return promptText({title, message, label: 'Motif (tracé dans l’audit)', placeholder: 'Ex. : arrivée dans l’équipe support', minLength: 5, confirmLabel: 'Confirmer'});
}

function strongPassword() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return Array.from(bytes, b => alphabet[b % alphabet.length]).join('');
}

export function TeamPage({token}: {token: string}) {
  const [tab, setTab] = useState<'users' | 'roles'>('users');
  const [users, setUsers] = useState<PlatformTeamUser[] | null>(null);
  const [roles, setRoles] = useState<PlatformRole[] | null>(null);
  const [caps, setCaps] = useState<PlatformCapability[]>([]);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');
  const [openUser, setOpenUser] = useState<string | null>(null);
  const [editRole, setEditRole] = useState<PlatformRole | 'new' | null>(null);
  const [createUser, setCreateUser] = useState(false);
  async function load(search = q) {
    try { setError(''); const [u, r, c] = await Promise.all([teamUsers(token, search), teamRoles(token), teamCapabilities(token)]); setUsers(u.items); setRoles(r.items); setCaps(c.items); }
    catch (e) { setError(friendlyError(e)); }
  }
  useEffect(() => { void load(''); }, [token]);
  const activeRoles = (roles || []).filter(r => r.status === 'ACTIVE');
  const roleLabel = (code: string) => roles?.find(r => r.code === code)?.label || code;

  async function roleAction(r: PlatformRole, action: 'activate' | 'archive' | 'clone') {
    try {
      if (action === 'clone') {
        const code = await promptText({title: `Cloner « ${r.label} »`, message: 'Le clone est créé en brouillon. Les capacités réservées ne sont jamais copiées.', label: 'Code du nouveau rôle (MAJUSCULES_ET_SOULIGNÉS)', minLength: 3, confirmLabel: 'Cloner'});
        if (!code) return;
        await teamCloneRole(token, r.id, {code: code.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_'), label: `${r.label} (copie)`});
        toast.success('Rôle cloné en brouillon');
      } else {
        const why = await reason(action === 'activate' ? `Activer « ${r.label} »` : `Archiver « ${r.label} »`,
          action === 'archive' ? `Les ${r.active_users} compte(s) qui détiennent ce rôle perdent immédiatement ses capacités.` : 'Le rôle pourra ensuite être attribué.');
        if (!why) return;
        await teamRoleStatus(token, r.id, action, why);
        toast.success(action === 'activate' ? 'Rôle activé' : 'Rôle archivé');
      }
      await load();
    } catch (e) { setError(friendlyError(e)); }
  }

  return <div className="tm">
    <div className="tm-bar">
      <div className="es-tabs tm-tabs" role="tablist" aria-label="Équipe plateforme">
        <button role="tab" aria-selected={tab === 'users'} className={tab === 'users' ? 'es-on' : ''} onClick={() => setTab('users')}><NavGlyph g="users" size={16}/>Comptes{users ? ` · ${users.length}` : ''}</button>
        <button role="tab" aria-selected={tab === 'roles'} className={tab === 'roles' ? 'es-on' : ''} onClick={() => setTab('roles')}><NavGlyph g="shield" size={16}/>Rôles{roles ? ` · ${roles.length}` : ''}</button>
      </div>
      {tab === 'users'
        ? <button className="es-btn es-btn-primary" onClick={() => setCreateUser(true)} disabled={!activeRoles.length}><NavGlyph g="plus" size={16}/>Ajouter un membre</button>
        : <button className="es-btn es-btn-primary" onClick={() => setEditRole('new')}><NavGlyph g="plus" size={16}/>Nouveau rôle</button>}
    </div>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}

    {tab === 'users' && <>
      <form className="tm-search" role="search" onSubmit={e => { e.preventDefault(); void load(q); }}>
        <NavGlyph g="search" size={16}/><input aria-label="Rechercher un membre" value={q} onChange={e => setQ(e.target.value)} placeholder="Nom ou adresse e-mail"/><button className="es-btn">Rechercher</button>
      </form>
      {users === null ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> : users.length === 0 ? <div className="es-empty">Aucun membre trouvé.</div> :
        <ul className="tm-list">{users.map(u => <li key={u.id}>
          <button className="tm-row" onClick={() => setOpenUser(u.id)} aria-label={`Ouvrir la fiche de ${u.full_name}`}>
            <span className="tm-avatar" aria-hidden="true">{u.full_name.split(/\s+/).map(x => x[0]).slice(0, 2).join('').toUpperCase()}</span>
            <span className="tm-who"><b>{u.full_name}{u.is_me && <em className="es-tag">Vous</em>}</b><small>{u.email}</small></span>
            <span className="tm-chips">{u.roles.length ? u.roles.map(c => <em key={c} className="tm-chip">{roleLabel(c)}</em>) : <em className="tm-chip tm-chip-muted">Aucun rôle actif</em>}{u.mfa_enrolled === false && u.roles.length > 0 && <em className="tm-chip tm-chip-warn" title="Validation en deux étapes pas encore configurée : elle sera demandée à sa prochaine connexion.">Sécurité à configurer</em>}</span>
            <span className={`tm-status ${u.platform_status === 'SUSPENDED' ? 'tm-bad' : 'tm-ok'}`}><i aria-hidden="true"/>{u.platform_status === 'SUSPENDED' ? 'Suspendu' : 'Actif'}</span>
            <span className="tm-meta"><small>Dernière activité</small>{when(u.last_activity)}</span>
            <NavGlyph g="chevronRight" size={18}/>
          </button></li>)}</ul>}
    </>}

    {tab === 'roles' && (roles === null ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> :
      <ul className="tm-roles">{roles.map(r => <li key={r.id} className={r.status === 'ARCHIVED' ? 'tm-archived' : ''}>
        <div className="tm-role-head">
          <div><b>{r.label}</b><small>{r.code}</small></div>
          <span className="tm-badges"><em className={`tm-chip ${r.kind === 'PLATFORM_STANDARD' ? 'tm-chip-std' : ''}`}>{r.kind === 'PLATFORM_STANDARD' ? 'Standard' : 'Personnalisé'}</em><em className={`tm-chip tm-st-${r.status.toLowerCase()}`}>{ROLE_STATUS[r.status] || r.status}</em></span>
        </div>
        {r.description && <p>{r.description}</p>}
        <div className="tm-role-caps">{r.capabilities.map(c => <em key={c} title={c}>{caps.find(x => x.code === c)?.label || c}</em>)}{!r.capabilities.length && <em className="tm-chip-muted">Aucune capacité</em>}</div>
        <div className="tm-role-foot">
          <small>{r.active_users} compte(s) · modifié {when(r.updated_at).toLowerCase()}</small>
          <span>
            {r.kind === 'PLATFORM_CUSTOM' && r.status !== 'ARCHIVED' && <button className="es-btn es-btn-ghost" onClick={() => setEditRole(r)}>Modifier</button>}
            {r.kind === 'PLATFORM_CUSTOM' && r.status === 'DRAFT' && <button className="es-btn" onClick={() => void roleAction(r, 'activate')}>Activer</button>}
            <button className="es-btn es-btn-ghost" onClick={() => void roleAction(r, 'clone')}>Cloner</button>
            {r.kind === 'PLATFORM_CUSTOM' && r.status !== 'ARCHIVED' && <button className="es-btn es-btn-danger" onClick={() => void roleAction(r, 'archive')}>Archiver</button>}
          </span>
        </div>
      </li>)}</ul>)}

    {editRole && <RoleEditor token={token} role={editRole === 'new' ? null : editRole} caps={caps} onClose={() => setEditRole(null)} onSaved={async () => { setEditRole(null); await load(); }}/>}
    {createUser && <CreateUserDialog token={token} roles={activeRoles} onClose={() => setCreateUser(false)} onSaved={async () => { setCreateUser(false); await load(); }}/>}
    {openUser && <UserSheet token={token} id={openUser} roles={activeRoles} caps={caps} onClose={() => setOpenUser(null)} onChanged={() => void load()}/>}
  </div>;
}

function CapabilityPicker({caps, value, onChange}: {caps: PlatformCapability[]; value: string[]; onChange: (v: string[]) => void}) {
  const groups = useMemo(() => { const m = new Map<string, PlatformCapability[]>(); caps.forEach(c => m.set(c.group_name, [...(m.get(c.group_name) || []), c])); return [...m.entries()]; }, [caps]);
  return <fieldset className="tm-caps"><legend>Capacités du rôle</legend>
    {groups.map(([g, list]) => <div key={g} className="tm-cap-group"><h4>{g}</h4>{list.map(c => {
      const disabled = !c.delegable;
      const why = c.reserved ? 'Réservée au Manager système : non délégable.' : !c.held ? 'Vous ne détenez pas cette capacité.' : '';
      return <label key={c.code} className={disabled ? 'tm-cap-off' : ''}>
        <input type="checkbox" disabled={disabled} checked={value.includes(c.code)} onChange={e => onChange(e.target.checked ? [...value, c.code] : value.filter(x => x !== c.code))} aria-describedby={why ? `why-${c.code}` : undefined}/>
        <span><b>{c.label}</b><small>{c.code} · risque {RISK[c.risk]?.toLowerCase() || c.risk}</small>{why && <small id={`why-${c.code}`} className="tm-why"><NavGlyph g="lock" size={12}/>{why}</small>}</span>
      </label>;
    })}</div>)}
  </fieldset>;
}

function RoleEditor({token, role, caps, onClose, onSaved}: {token: string; role: PlatformRole | null; caps: PlatformCapability[]; onClose: () => void; onSaved: () => void}) {
  const [code, setCode] = useState(''); const [label, setLabel] = useState(role?.label || ''); const [description, setDescription] = useState(role?.description || '');
  const [selected, setSelected] = useState<string[]>(role?.capabilities || []); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!role && !/^[A-Z][A-Z0-9_]{2,63}$/.test(code)) { setError('Code : majuscules, chiffres et « _ », 3 caractères minimum, commençant par une lettre.'); return; }
    if (label.trim().length < 3) { setError('Le libellé doit compter au moins 3 caractères.'); return; }
    try {
      setBusy(true);
      if (role) await teamUpdateRole(token, role.id, {label, description, capabilities: selected, version: role.version});
      else await teamCreateRole(token, {code, label, description, capabilities: selected});
      toast.success(role ? 'Rôle modifié' : 'Rôle créé en brouillon : activez-le pour l’attribuer'); onSaved();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <Modal title={role ? `Modifier « ${role.label} »` : 'Nouveau rôle plateforme'} subtitle="Un rôle personnalisé ne donne jamais accès aux données des écoles." onClose={onClose} wide>
    <form className="es-form tm-form" onSubmit={save} noValidate>
      {!role && <label className="tm-field"><span>Code *</span><input value={code} onChange={e => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_'))} placeholder="SUPPORT_NIVEAU_1" autoComplete="off"/></label>}
      <label className="tm-field"><span>Libellé *</span><input value={label} onChange={e => setLabel(e.target.value)} placeholder="Support niveau 1"/></label>
      <label className="tm-field"><span>Description</span><textarea rows={2} value={description} onChange={e => setDescription(e.target.value)} placeholder="À quoi sert ce rôle ?"/></label>
      <CapabilityPicker caps={caps} value={selected} onChange={setSelected}/>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><button className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Enregistrement…' : role ? 'Enregistrer' : 'Créer le brouillon'}</button></div>
    </form>
  </Modal>;
}

function CreateUserDialog({token, roles, onClose, onSaved}: {token: string; roles: PlatformRole[]; onClose: () => void; onSaved: () => void}) {
  const [email, setEmail] = useState(''); const [name, setName] = useState(''); const [password] = useState(strongPassword());
  const [picked, setPicked] = useState<string[]>([]); const [why, setWhy] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) { setError('Saisissez une adresse e-mail valide.'); return; }
    if (name.trim().length < 3) { setError('Indiquez le nom complet.'); return; }
    if (!picked.length) { setError('Choisissez au moins un rôle.'); return; }
    if (why.trim().length < 5) { setError('Le motif est obligatoire (5 caractères minimum).'); return; }
    try { setBusy(true); await teamCreateUser(token, {email: email.trim().toLowerCase(), full_name: name.trim(), password, role_codes: picked, reason: why.trim()}); toast.success('Membre ajouté. Transmettez-lui son mot de passe provisoire par un canal sûr.'); onSaved(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <Modal title="Ajouter un membre de l’équipe" subtitle="Compte Atelier Pro. Il pourra changer son mot de passe depuis « Sécurité et appareils »." onClose={onClose} wide>
    <form className="es-form tm-form" onSubmit={save} noValidate>
      <div className="tm-grid2">
        <label className="tm-field"><span>Nom complet *</span><input value={name} onChange={e => setName(e.target.value)} autoComplete="off"/></label>
        <label className="tm-field"><span>Adresse e-mail *</span><input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="off"/></label>
      </div>
      <div className="tm-field"><span>Mot de passe provisoire</span><div className="tm-secret"><code>{shown ? password : '•'.repeat(18)}</code>
        <button type="button" className="es-btn es-btn-ghost" onClick={() => setShown(x => !x)} aria-pressed={shown}>{shown ? 'Masquer' : 'Afficher'}</button>
        <button type="button" className="es-btn es-btn-ghost" onClick={() => { void navigator.clipboard?.writeText(password).then(() => toast.success('Copié')); }}>Copier</button></div>
        <small className="es-hint">Généré sur cet appareil, jamais affiché dans l’audit ni les journaux.</small></div>
      <fieldset className="tm-caps"><legend>Rôles *</legend>{roles.map(r => <label key={r.code}>
        <input type="checkbox" checked={picked.includes(r.code)} onChange={e => setPicked(e.target.checked ? [...picked, r.code] : picked.filter(x => x !== r.code))}/>
        <span><b>{r.label}</b><small>{r.kind === 'PLATFORM_STANDARD' ? 'Standard' : 'Personnalisé'} · {r.capabilities.length} capacité(s)</small></span></label>)}</fieldset>
      <label className="tm-field"><span>Motif *</span><input value={why} onChange={e => setWhy(e.target.value)} placeholder="Ex. : arrivée dans l’équipe support"/></label>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><button className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Création…' : 'Ajouter le membre'}</button></div>
    </form>
  </Modal>;
}

function UserSheet({token, id, roles, caps, onClose, onChanged}: {token: string; id: string; roles: PlatformRole[]; caps: PlatformCapability[]; onClose: () => void; onChanged: () => void}) {
  const [u, setU] = useState<PlatformTeamUserDetail | null>(null); const [error, setError] = useState(''); const [assign, setAssign] = useState('');
  const [mfaReset, setMfaReset] = useState(false);
  async function load() { try { setError(''); setU(await teamUser(token, id)); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [id]);
  async function run(fn: () => Promise<unknown>, ok: string) { try { await fn(); toast.success(ok); await load(); onChanged(); } catch (e) { setError(friendlyError(e)); } }
  const activeCodes = new Set((u?.roles || []).filter(r => r.active).map(r => r.code));
  const assignable = roles.filter(r => !activeCodes.has(r.code));
  return <Modal title={u?.full_name || 'Membre de l’équipe'} subtitle={u?.email} onClose={onClose} wide>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {!u ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> : <div className="tm-sheet">
      {u.is_me && <div className="es-alert">C’est votre compte : gérez votre mot de passe et vos appareils depuis « Sécurité et appareils ». Vos propres rôles ne se modifient pas ici.</div>}
      <section><h3>Statut</h3><p className="tm-line"><span className={`tm-status ${u.platform_status === 'SUSPENDED' ? 'tm-bad' : 'tm-ok'}`}><i aria-hidden="true"/>{u.platform_status === 'SUSPENDED' ? 'Suspendu' : 'Actif'}</span>{u.status_reason && <small>{u.status_reason}</small>}</p>
        {!u.is_me && <div className="tm-actions">
          {u.platform_status === 'SUSPENDED'
            ? <button className="es-btn" onClick={async () => { const w = await reason('Réactiver ce compte'); if (w) await run(() => teamUserStatus(token, id, 'reactivate', w), 'Compte réactivé'); }}>Réactiver</button>
            : <button className="es-btn es-btn-danger" onClick={async () => { const w = await reason('Suspendre ce compte', 'Toutes ses sessions Atelier Pro sont coupées immédiatement. Ses rôles sont conservés.'); if (w) await run(() => teamUserStatus(token, id, 'suspend', w), 'Compte suspendu'); }}>Suspendre</button>}
          <button className="es-btn es-btn-ghost" onClick={async () => { const w = await reason('Réinitialiser le mot de passe', 'Un nouveau mot de passe provisoire est généré ; toutes les sessions sont coupées.'); if (!w) return; const p = strongPassword(); await run(() => teamResetPassword(token, id, p, w), 'Mot de passe réinitialisé'); void navigator.clipboard?.writeText(p).then(() => toast.info('Mot de passe provisoire copié dans le presse-papiers.')); }}>Réinitialiser le mot de passe</button>
        </div>}
      </section>
      <section><h3>Validation en deux étapes</h3>
        <p className="tm-line"><span className={`tm-status ${u.mfa?.enrolled ? 'tm-ok' : 'tm-bad'}`}><i aria-hidden="true"/>{u.mfa?.enrolled ? 'Activée' : 'À configurer'}</span>
          <small>{u.mfa?.enrolled ? `Depuis le ${new Date(u.mfa.confirmed_at || '').toLocaleDateString('fr-FR')} · ${u.mfa.recovery_codes_remaining} code(s) de secours restant(s)` : 'Elle sera demandée à sa prochaine connexion : sans elle, aucun accès à l’Atelier Pro.'}</small></p>
        {!u.is_me && u.mfa?.enrolled && <div className="tm-actions">
          <button className="es-btn es-btn-danger" onClick={() => setMfaReset(true)}>Réinitialiser la validation en deux étapes</button>
        </div>}
      </section>
      <section><h3>Rôles</h3><ul className="tm-plain">{u.roles.filter(r => r.active).map(r => <li key={r.code}><span><b>{r.label}</b><small>{r.kind === 'PLATFORM_STANDARD' ? 'Standard' : 'Personnalisé'}{r.status !== 'ACTIVE' ? ` · rôle ${ROLE_STATUS[r.status]?.toLowerCase()}` : ''}</small></span>
        {!u.is_me && <button className="es-btn es-btn-ghost" onClick={async () => { const w = await reason(`Retirer « ${r.label} »`); if (w) await run(() => teamRevokeRole(token, id, r.code, w), 'Rôle retiré'); }}>Retirer</button>}</li>)}
        {!u.roles.some(r => r.active) && <li className="tm-chip-muted">Aucun rôle actif.</li>}</ul>
        {!u.is_me && assignable.length > 0 && <div className="tm-assign"><select aria-label="Rôle à attribuer" value={assign} onChange={e => setAssign(e.target.value)}><option value="">Attribuer un rôle…</option>{assignable.map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select>
          <button className="es-btn" disabled={!assign} onClick={async () => { const w = await reason('Attribuer ce rôle'); if (w) { await run(() => teamAssignRole(token, id, assign, w), 'Rôle attribué'); setAssign(''); } }}>Attribuer</button></div>}
      </section>
      <section><h3>Permissions effectives <small>({u.effective_permissions.length})</small></h3><div className="tm-role-caps">{u.effective_permissions.map(c => <em key={c} title={c}>{caps.find(x => x.code === c)?.label || c}</em>)}{!u.effective_permissions.length && <em className="tm-chip-muted">Aucune</em>}</div></section>
      <section><h3>Appareils connectés <small>({u.sessions.length})</small></h3><ul className="tm-plain">{u.sessions.map(s => <li key={s.id}><span><b>{s.label || 'Navigateur'}</b><small>Ouverte le {new Date(s.created_at).toLocaleDateString('fr-FR')} · activité {when(s.last_seen_at).toLowerCase()}</small></span>
        {!u.is_me && <button className="es-btn es-btn-ghost" onClick={async () => { const w = await reason('Déconnecter cet appareil'); if (w) await run(() => teamRevokeSessions(token, id, w, s.id), 'Appareil déconnecté'); }}>Déconnecter</button>}</li>)}
        {!u.sessions.length && <li className="tm-chip-muted">Aucune session Atelier Pro ouverte.</li>}</ul>
        {!u.is_me && u.sessions.length > 1 && <button className="es-btn es-btn-danger" onClick={async () => { const w = await reason('Déconnecter tous ses appareils'); if (w) await run(() => teamRevokeSessions(token, id, w), 'Tous les appareils déconnectés'); }}>Déconnecter tous ses appareils</button>}
      </section>
      {mfaReset && <MfaResetDialog name={u.full_name} onClose={() => setMfaReset(false)} onConfirm={async (why, withPassword) => {
        const p = withPassword ? strongPassword() : undefined;
        try { await teamResetMfa(token, id, why, p); }
        catch (e) { setError(friendlyError(e)); setMfaReset(false); return; }
        toast.success(p ? 'Validation en deux étapes et mot de passe réinitialisés' : 'Validation en deux étapes réinitialisée');
        // The temporary password is copied only once the server has applied it.
        if (p) void navigator.clipboard?.writeText(p).then(() => toast.info('Mot de passe provisoire copié : transmettez-le par un canal sûr.'));
        setMfaReset(false); await load(); onChanged();
      }}/>}
      <section><h3>Historique</h3><ol className="tm-history">{u.audit.map((a, i) => <li key={i}><b>{auditActionLabel(a.action)}</b><small>{new Date(a.occurred_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'short'})}{a.actor ? ` · ${a.actor}` : ''}{a.reason ? ` · ${a.reason}` : ''}</small></li>)}{!u.audit.length && <li className="tm-chip-muted">Aucun événement.</li>}</ol></section>
    </div>}
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
    <form className="es-form tm-form" onSubmit={submit} noValidate>
      <div className="es-alert es-alert-warn" role="note"><NavGlyph g="alert" size={16}/><span>Vérifiez d’abord l’identité de la personne par un autre canal (appel, rencontre). Ses sessions Atelier Pro seront coupées, elle sera prévenue dans EduSync, et elle configurera une nouvelle application à sa prochaine connexion.</span></div>
      <label className="tm-field"><span>Motif *</span><textarea rows={3} value={why} onChange={e => setWhy(e.target.value)} placeholder="Ex. : téléphone perdu, identité vérifiée par appel le…"/></label>
      <label className="mfa-reset-pw"><input type="checkbox" checked={withPassword} onChange={e => setWithPassword(e.target.checked)}/><span><b>Réinitialiser aussi le mot de passe</b><small>Recommandé si le téléphone a été volé ou si le mot de passe a pu être vu. Un mot de passe provisoire est généré et copié ; toutes ses sessions sont coupées.</small></span></label>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><button className="es-btn es-btn-danger" disabled={busy}>{busy ? 'Réinitialisation…' : 'Réinitialiser'}</button></div>
    </form>
  </Modal>;
}
