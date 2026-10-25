import {OnlineActionButton} from './online_action';
import React, {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {useForm} from 'react-hook-form';
import {z} from 'zod';
import {zodResolver} from '@hookform/resolvers/zod';
import {toast} from 'sonner';
import {changeMyPassword, changePlatformPassword, dismissNotification, listMySessions, listNotifications, listPlatformSessions, logoutAllDevices, MfaError, platformMfaStatus, platformStepUp, regenerateRecoveryCodes, revokeMySession, revokePlatformSession, type DeviceSession, type InternalNotification, type PlatformMfaStatus} from '../api';
import {FormField, formDefaults} from './forms';
import {friendlyError, UserFacingError} from './errors';
import {NavGlyph} from './nav_icons';
import {initialsOf} from './shell';
import {THEME_OPTIONS, type ThemePref} from './theme';
import {DeviceNotificationPreference} from './device_preferences';
import {CURRENT_BUILD, shortBuild} from './updates';

export function Modal({title, subtitle, onClose, children, wide}: {title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; wide?: boolean}) {
  const ref = useRef<HTMLDivElement>(null);
  // A caller may create an inline callback on every input change. Only the
  // dialog's lifetime owns focus; callback changes must never restore it.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>('input:not([disabled]),select:not([disabled]),textarea:not([disabled])')
      ?? ref.current?.querySelector<HTMLElement>('button:not([disabled])');
    first?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, []);
  return <div className="es-modal-backdrop" onMouseDown={e => e.currentTarget === e.target && onClose()}>
    <div className={`es-modal ${wide ? 'es-modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
      <div className="es-modal-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        <button className="es-icon-btn" aria-label="Fermer" onClick={onClose}><NavGlyph g="close" size={18}/></button></div>
      {children}
    </div>
  </div>;
}

export function ProfileDialog({name, email, context, detail, onClose, platform, avatarUrl, onPhotoUpload, onPhotoRemove}: {
  name: string; email?: string; context?: string; detail?: string; onClose: () => void; platform?: boolean;
  avatarUrl?: string; onPhotoUpload?: (file: File) => Promise<void>; onPhotoRemove?: () => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<'' | 'upload' | 'remove'>('');
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<string | undefined>();
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  async function pick(file: File | undefined) {
    if (!file || !onPhotoUpload) return;
    setError('');
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { setError('Choisissez une photo JPEG, PNG ou WebP.'); return; }
    if (file.size > 5 * 1024 * 1024) { setError('La photo dépasse 5 Mo.'); return; }
    setPreview(URL.createObjectURL(file)); setBusy('upload');
    try { await onPhotoUpload(file); toast.success('Photo de profil mise à jour'); }
    catch (e) { setError(e instanceof UserFacingError ? e.message : friendlyError(e)); setPreview(undefined); }
    finally { setBusy(''); if (input.current) input.current.value = ''; }
  }
  async function remove() {
    if (!onPhotoRemove) return;
    setError(''); setBusy('remove');
    try { await onPhotoRemove(); setPreview(undefined); toast.success('Photo retirée'); } catch (e) { setError(friendlyError(e)); } finally { setBusy(''); }
  }
  const shown = preview || avatarUrl;
  return <Modal title="Mon profil" subtitle="Informations de votre compte EduSync." onClose={onClose}>
    <div className="es-profile">
      <div className="es-profile-photo">
        <span className={`es-avatar es-avatar-xl ${shown ? 'es-avatar-photo' : ''}`} aria-hidden="true">{shown ? <img src={shown} alt=""/> : initialsOf(name)}
          {busy === 'upload' && <i className="es-avatar-busy"/>}</span>
        {onPhotoUpload && <div className="es-profile-photo-actions">
          <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e => void pick(e.target.files?.[0])}/>
          <button type="button" className="es-btn" disabled={!!busy} onClick={() => input.current?.click()}><NavGlyph g="image" size={16}/>{shown ? 'Changer la photo' : 'Ajouter une photo'}</button>
          {shown && onPhotoRemove && <button type="button" className="es-btn es-btn-ghost" disabled={!!busy} onClick={() => void remove()}>{busy === 'remove' ? 'Retrait…' : 'Retirer'}</button>}
          <small className="es-hint">JPEG, PNG ou WebP, 5 Mo maximum. La photo est recadrée en carré ; ses données de localisation sont supprimées.</small>
        </div>}
      </div>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <dl>
        <dt>Nom</dt><dd>{name}</dd>
        {email && <><dt>Adresse e-mail</dt><dd>{email}</dd></>}
        {context && <><dt>{platform ? 'Espace et rôle' : 'Espace de travail'}</dt><dd>{context}</dd></>}
        {detail && <><dt>Année consultée</dt><dd>{detail}</dd></>}
      </dl>
      <p className="es-hint">{platform
        ? 'Le nom et l’adresse e-mail des comptes de la plateforme sont gérés par l’équipe plateforme : un Manager Système peut les modifier depuis « Équipe plateforme ».'
        : 'Le nom et l’adresse e-mail sont gérés par l’administrateur des accès de votre école.'}</p>
    </div>
    <div className="es-modal-foot"><button className="es-btn" onClick={onClose}>Fermer</button></div>
  </Modal>;
}

/** Personal settings on this device, separate from school-wide configuration. */
export function PreferencesDialog({theme, onTheme, reducedMotion, onReducedMotion, token, pushScope, platform, canPush = true, onClose}: {
  theme?: ThemePref; onTheme?: (t: ThemePref) => void;
  reducedMotion: boolean; onReducedMotion: (value: boolean) => void;
  token: string; pushScope: string; platform: boolean; canPush?: boolean; onClose: () => void;
}) {
  return <Modal title="Préférences" subtitle="Réglages personnels sur cet appareil." onClose={onClose}>
    {platform && theme && onTheme ? <fieldset className="es-pref-group">
      <legend>Thème</legend>
      <div className="es-pref-options" role="radiogroup" aria-label="Thème">
        {THEME_OPTIONS.map(o => <label key={o.value} className={`es-pref-option ${theme === o.value ? 'es-on' : ''}`}>
          <input type="radio" name="es-theme" value={o.value} checked={theme === o.value} onChange={() => onTheme(o.value)}/>
          <span className="es-pref-icon" aria-hidden="true"><NavGlyph g={o.icon} size={20}/></span>
          <span className="es-pref-text"><b>{o.label}</b><small>{o.hint}</small></span>
        </label>)}
      </div>
    </fieldset> : <p className="es-hint">L’espace École conserve actuellement son thème clair.</p>}
    <fieldset className="es-pref-group">
      <legend>Accessibilité</legend>
      <label className={`es-pref-option ${reducedMotion ? 'es-on' : ''}`}>
        <input type="checkbox" checked={reducedMotion} onChange={e => onReducedMotion(e.target.checked)}/>
        <span className="es-pref-icon" aria-hidden="true"><NavGlyph g="eye" size={20}/></span>
        <span className="es-pref-text"><b>Réduire les animations</b><small>Limiter les mouvements et transitions de l’interface.</small></span>
      </label>
    </fieldset>
    {canPush ? <DeviceNotificationPreference token={token} scope={pushScope} platform={platform}/> : <p className="es-hint">Les notifications push ne sont pas disponibles avec les droits de ce compte.</p>}
    <p className="es-hint">L’affichage est conservé pour ce compte sur cet appareil. Langue : français.</p>
    <p className="es-hint es-version">Version d’EduSync : <b>{shortBuild(CURRENT_BUILD)}</b></p>
    <div className="es-modal-foot"><button type="button" className="es-btn es-btn-primary" onClick={onClose}>Terminé</button></div>
  </Modal>;
}

const passwordSchema = z.object({
  current: z.string().min(1, 'Le mot de passe actuel est obligatoire.'),
  next: z.string().min(10, 'Au moins 10 caractères sont requis.'),
  confirm: z.string().min(1, 'Confirmez le nouveau mot de passe.'),
}).refine(v => v.next === v.confirm, {message: 'Les deux nouveaux mots de passe ne correspondent pas.', path: ['confirm']});
type PasswordForm = z.infer<typeof passwordSchema>;

function relative(iso: string) {
  const d = new Date(iso); const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 2) return 'à l’instant';
  if (mins < 60) return `il y a ${mins} min`;
  if (mins < 60 * 24) return `il y a ${Math.round(mins / 60)} h`;
  return d.toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'});
}

export function SecurityDialog({token, onClose, onPasswordChanged, platform}: {token: string; onClose: () => void; onPasswordChanged: () => void; platform?: boolean}) {
  const [tab, setTab] = useState<'devices' | 'password' | 'mfa'>('devices');
  const [sessions, setSessions] = useState<DeviceSession[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmAll, setConfirmAll] = useState(false);
  const form = useForm<PasswordForm>({resolver: zodResolver(passwordSchema), defaultValues: {current: '', next: '', confirm: ''}, ...formDefaults});
  const api = platform ? {list: listPlatformSessions, revoke: revokePlatformSession, password: changePlatformPassword} : {list: listMySessions, revoke: revokeMySession, password: changeMyPassword};
  async function load() { try { setError(''); setSessions((await api.list(token)).items); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  const active = (sessions || []).filter(s => !s.revoked_at);
  async function revoke(s: DeviceSession) {
    try { setBusy(s.id); await api.revoke(token, s.id); toast.success('Appareil déconnecté'); if (s.current) { onPasswordChanged(); return; } await load(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(''); }
  }
  async function logoutAll() {
    try { setBusy('all'); await logoutAllDevices(); toast.success('Tous vos appareils ont été déconnectés.'); onPasswordChanged(); }
    catch (e) { setError(friendlyError(e)); setBusy(''); }
  }
  const save = form.handleSubmit(async v => {
    setError('');
    try { await api.password(token, {current_password: v.current, new_password: v.next}); toast.success('Mot de passe modifié. Reconnectez-vous.'); onPasswordChanged(); }
    catch (e) { setError(friendlyError(e)); }
  });
  return <Modal title="Sécurité et appareils" subtitle="Vos connexions actives et votre mot de passe." onClose={onClose} wide>
    <div className="es-tabs" role="tablist">
      <button role="tab" aria-selected={tab === 'devices'} className={tab === 'devices' ? 'es-on' : ''} onClick={() => setTab('devices')}><NavGlyph g="device" size={16}/>Appareils connectés</button>
      <button role="tab" aria-selected={tab === 'password'} className={tab === 'password' ? 'es-on' : ''} onClick={() => setTab('password')}><NavGlyph g="key" size={16}/>Mot de passe</button>
      {platform && <button role="tab" aria-selected={tab === 'mfa'} className={tab === 'mfa' ? 'es-on' : ''} onClick={() => setTab('mfa')}><NavGlyph g="shield" size={16}/>Validation en 2 étapes</button>}
    </div>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {tab === 'devices' && <div className="es-sessions">
      <p className="es-hint">Vous restez connecté sur vos appareils jusqu’à ce que vous vous déconnectiez. Déconnectez ici un appareil perdu ou partagé : l’accès est coupé immédiatement.</p>
      {sessions === null ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> : active.length === 0 ? <div className="es-empty">Aucune session active.</div> :
        <ul>{active.map((s, i) => <li key={s.id}>
          <NavGlyph g="device" size={20}/>
          <div><b>{s.label || 'Navigateur'}{s.current ? <em className="es-tag">Cet appareil</em> : s.current === undefined && i === 0 && <em className="es-tag">Activité la plus récente</em>}</b><small>{s.context ? `${s.context} · ` : ''}Ouverte le {new Date(s.created_at).toLocaleDateString('fr-FR')} · activité {relative(s.last_seen_at)}</small></div>
          <button className="es-btn es-btn-ghost" disabled={busy === s.id} onClick={() => void revoke(s)}>{busy === s.id ? 'Déconnexion…' : 'Déconnecter'}</button>
        </li>)}</ul>}
      {active.length > 0 && <div className="es-modal-foot">{confirmAll
        ? <><span className="es-hint es-grow" role="status">Tous vos appareils, y compris celui-ci, seront déconnectés.</span><button className="es-btn es-btn-ghost" onClick={() => setConfirmAll(false)}>Annuler</button><OnlineActionButton className="es-btn es-btn-danger" autoFocus disabled={busy === 'all'} onClick={() => void logoutAll()}>{busy === 'all' ? 'Déconnexion…' : 'Confirmer'}</OnlineActionButton></>
        : <OnlineActionButton className="es-btn es-btn-danger" onClick={() => setConfirmAll(true)}>Déconnecter tous les appareils</OnlineActionButton>}</div>}
    </div>}
    {tab === 'mfa' && platform && <MfaPanel token={token}/>}
    {tab === 'password' && <form className="es-form" onSubmit={save} noValidate>
      <p className="es-hint">Changer votre mot de passe déconnecte immédiatement tous vos appareils.</p>
      <FormField label="Mot de passe actuel *" error={form.formState.errors.current?.message}><input type="password" autoComplete="current-password" {...form.register('current')}/></FormField>
      <FormField label="Nouveau mot de passe *" error={form.formState.errors.next?.message}><input type="password" autoComplete="new-password" {...form.register('next')}/></FormField>
      <FormField label="Confirmer le nouveau mot de passe *" error={form.formState.errors.confirm?.message}><input type="password" autoComplete="new-password" {...form.register('confirm')}/></FormField>
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <OnlineActionButton className="es-btn es-btn-primary" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Modification…' : 'Modifier le mot de passe'}</OnlineActionButton></div>
    </form>}
  </Modal>;
}

/** Second factor of a platform account: status and new recovery codes. Never a way to switch it off (option B). */
function MfaPanel({token}: {token: string}) {
  const [st, setSt] = useState<PlatformMfaStatus | null>(null);
  const [code, setCode] = useState(''); const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function load() { try { setError(''); setSt(await platformMfaStatus(token)); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  async function regenerate(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!/^\d{6}$/.test(code)) { setError('Saisissez les 6 chiffres affichés par votre application.'); return; }
    try { setBusy(true); const r = await regenerateRecoveryCodes(token, code); setCodes(r.recovery_codes); setCode(''); toast.success('Nouveaux codes générés : les précédents ne fonctionnent plus.'); await load(); }
    catch (err) { setError(err instanceof MfaError ? err.message : friendlyError(err)); setCode(''); } finally { setBusy(false); }
  }
  const text = () => ['EduSync — codes de secours', 'Chaque code ne fonctionne qu’une seule fois.', '', ...(codes || []), ''].join('\n');
  if (!st) return error ? <div className="es-alert es-alert-bad" role="alert">{error}</div> : <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>;
  return <div className="es-form">
    <p className="es-hint"><b>{st.enrolled ? 'Activée' : 'Non configurée'}</b>{st.enrolled && st.confirmed_at ? ` depuis le ${new Date(st.confirmed_at).toLocaleDateString('fr-FR')}` : ''} · obligatoire pour les comptes de la plateforme EduSync. Un code de votre application est demandé à chaque nouvelle connexion ; vos appareils déjà approuvés restent connectés.</p>
    <p className="es-hint">Codes de secours restants : <b>{st.recovery_codes_remaining}</b>{st.recovery_codes_remaining <= 3 ? ' — pensez à en générer de nouveaux.' : ''}</p>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {codes ? <>
      <ul className="es-recovery" aria-label="Nouveaux codes de secours">{codes.map(c => <li key={c}><code>{c}</code></li>)}</ul>
      <div className="es-alert" role="note">Ces codes ne seront plus affichés. Rangez-les hors d’EduSync (gestionnaire de mots de passe, papier sous clé).</div>
      <div className="es-modal-foot"><button className="es-btn es-btn-ghost" onClick={() => { void navigator.clipboard?.writeText(text()).then(() => toast.success('Codes copiés')); }}>Copier</button>
        <OnlineActionButton className="es-btn es-btn-primary" onClick={() => setCodes(null)}>J’ai conservé ces codes</OnlineActionButton></div>
    </> : st.enrolled && <form onSubmit={regenerate} noValidate className="es-form">
      <FormField label="Code de votre application (6 chiffres) *"><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}/></FormField>
      <div className="es-modal-foot"><OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Génération…' : 'Générer de nouveaux codes de secours'}</OnlineActionButton></div>
    </form>}
    <p className="es-hint">Téléphone perdu ou changé ? Demandez à un autre Manager Système de réinitialiser votre validation en deux étapes depuis « Équipe plateforme » : vous la configurerez à nouveau à la connexion suivante. Elle ne peut pas être désactivée.</p>
  </div>;
}

/** Step-up: a sensitive action asks for a fresh code; the action is then sent again automatically. */
export function StepUpDialog({token, onDone}: {token: string; onDone: (ok: boolean) => void}) {
  const [code, setCode] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const sent = useRef('');
  async function confirm(value = code) {
    if (busy) return; setError('');
    if (!/^\d{6}$/.test(value)) { setError('Saisissez les 6 chiffres affichés par votre application.'); return; }
    try { setBusy(true); await platformStepUp(token, value); onDone(true); }
    catch (e) { setError(e instanceof MfaError ? e.message : friendlyError(e)); setCode(''); sent.current = ''; }
    finally { setBusy(false); }
  }
  // Rendered at the end of <body>: it must cover any dialog already open (a member sheet, a school sheet…).
  return createPortal(<div className="es-stepup-layer"><Modal title="Confirmez avec votre code" subtitle="Action sensible : saisissez le code à 6 chiffres de votre application d’authentification." onClose={() => onDone(false)}>
    <form className="es-form" onSubmit={e => { e.preventDefault(); void confirm(); }} noValidate>
      <FormField label="Code de vérification *" error={error || undefined}>
        <input className="es-stepup-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} value={code} disabled={busy}
          onChange={e => { const v = e.target.value.replace(/\D/g, '').slice(0, 6); setCode(v); if (v.length === 6 && sent.current !== v) { sent.current = v; void confirm(v); } }}/>
      </FormField>
      <p className="es-hint">Une fois confirmé, ce code reste valable quelques minutes sur cet appareil pour les autres actions sensibles.</p>
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={() => onDone(false)}>Annuler</button>
        <OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Vérification…' : 'Confirmer'}</OnlineActionButton></div>
    </form>
  </Modal></div>, document.body);
}

// The bell lives in notification_center.tsx (inbox with filters, pagination, read-all); re-exported for existing imports.
export {NotificationBell} from './notification_center';
