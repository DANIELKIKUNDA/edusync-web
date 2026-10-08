import React, {useEffect, useRef, useState} from 'react';
import {useForm} from 'react-hook-form';
import {z} from 'zod';
import {zodResolver} from '@hookform/resolvers/zod';
import {toast} from 'sonner';
import {changeMyPassword, changePlatformPassword, dismissNotification, listMySessions, listNotifications, listPlatformSessions, logoutAllDevices, revokeMySession, revokePlatformSession, type DeviceSession, type InternalNotification} from '../api';
import {FormField, formDefaults} from './forms';
import {friendlyError} from './errors';
import {NavGlyph} from './nav_icons';
import {initialsOf} from './shell';

export function Modal({title, subtitle, onClose, children, wide}: {title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; wide?: boolean}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('input,button,select,textarea')?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [onClose]);
  return <div className="es-modal-backdrop" onMouseDown={e => e.currentTarget === e.target && onClose()}>
    <div className={`es-modal ${wide ? 'es-modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
      <div className="es-modal-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        <button className="es-icon-btn" aria-label="Fermer" onClick={onClose}><NavGlyph g="close" size={18}/></button></div>
      {children}
    </div>
  </div>;
}

export function ProfileDialog({name, email, context, detail, onClose}: {name: string; email?: string; context?: string; detail?: string; onClose: () => void}) {
  return <Modal title="Mon profil" subtitle="Informations de votre compte EduSync." onClose={onClose}>
    <div className="es-profile">
      <span className="es-avatar es-avatar-xl" aria-hidden="true">{initialsOf(name)}</span>
      <dl>
        <dt>Nom</dt><dd>{name}</dd>
        {email && <><dt>Adresse e-mail</dt><dd>{email}</dd></>}
        {context && <><dt>Espace de travail</dt><dd>{context}</dd></>}
        {detail && <><dt>Année consultée</dt><dd>{detail}</dd></>}
      </dl>
      <p className="es-hint">Le nom et l’adresse e-mail sont gérés par l’administrateur des accès de votre école.</p>
    </div>
    <div className="es-modal-foot"><button className="es-btn" onClick={onClose}>Fermer</button></div>
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
  const [tab, setTab] = useState<'devices' | 'password'>('devices');
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
        ? <><span className="es-hint es-grow" role="status">Tous vos appareils, y compris celui-ci, seront déconnectés.</span><button className="es-btn es-btn-ghost" onClick={() => setConfirmAll(false)}>Annuler</button><button className="es-btn es-btn-danger" autoFocus disabled={busy === 'all'} onClick={() => void logoutAll()}>{busy === 'all' ? 'Déconnexion…' : 'Confirmer'}</button></>
        : <button className="es-btn es-btn-danger" onClick={() => setConfirmAll(true)}>Déconnecter tous les appareils</button>}</div>}
    </div>}
    {tab === 'password' && <form className="es-form" onSubmit={save} noValidate>
      <p className="es-hint">Changer votre mot de passe déconnecte immédiatement tous vos appareils.</p>
      <FormField label="Mot de passe actuel *" error={form.formState.errors.current?.message}><input type="password" autoComplete="current-password" {...form.register('current')}/></FormField>
      <FormField label="Nouveau mot de passe *" error={form.formState.errors.next?.message}><input type="password" autoComplete="new-password" {...form.register('next')}/></FormField>
      <FormField label="Confirmer le nouveau mot de passe *" error={form.formState.errors.confirm?.message}><input type="password" autoComplete="new-password" {...form.register('confirm')}/></FormField>
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <button className="es-btn es-btn-primary" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Modification…' : 'Modifier le mot de passe'}</button></div>
    </form>}
  </Modal>;
}

// The bell lives in notification_center.tsx (inbox with filters, pagination, read-all); re-exported for existing imports.
export {NotificationBell} from './notification_center';
