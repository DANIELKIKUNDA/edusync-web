// Account links sent by e-mail (EMAIL_TRANSACTIONAL_INTEGRATION.md): forgotten password, new password from a recovery
// link, invitation acceptance. The single-use token arrives in the URL fragment (#reset=… / #invitation=…), is read once
// and removed from the address bar at once (never stored, never sent in a request line).
import React, {useEffect, useState} from 'react';
import {NavGlyph} from './platform/nav_icons';
import {acceptInvitation, forgotPassword, resetPassword} from './messaging_api';
import {nativeFetch} from './platform/connectivity';

export type AccountLink = {kind: 'reset' | 'invitation'; token: string};

/** Reads and clears #reset=… / #invitation=… once. */
export function takeAccountLink(): AccountLink | null {
  const raw = window.location.hash || '';
  const m = /^#(reset|invitation)=([^&]*)$/.exec(raw);
  if (!m) return null;
  // Remove the bearer token before any session restoration, network request, or route logging.
  history.replaceState(history.state, '', window.location.pathname + window.location.search);
  return {kind: m[1] as AccountLink['kind'], token: /^[A-Za-z0-9_-]{20,200}$/.test(m[2]) ? m[2] : ''};
}

type InvitationInfo = {full_name: string; school_name: string | null; scope: 'PLATFORM' | 'SCHOOL'};
function invitationEvent(stage: string, result: string) {
  // Reason codes only. Never log the link, token, name, e-mail or response body.
  console.info('edusync.invitation', {stage, result});
}
async function invitationRequest<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), 8000);
  const abort = () => ctl.abort();
  signal?.addEventListener('abort', abort, {once: true});
  try {
    const r = await nativeFetch('/api/v1/auth/invitations/' + path, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token}), signal: ctl.signal,
    });
    if (!r.ok) {
      const error = new Error(r.status === 400 || r.status === 404
        ? 'Lien invalide, expiré ou déjà utilisé. Contactez un Manager Système.'
        : 'Activation indisponible. Vérifiez votre connexion puis réessayez.') as Error & {status?: number};
      error.status = r.status;
      throw error;
    }
    return await r.json() as T;
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError'))
      throw new Error('Le serveur ne répond pas. Vérifiez votre connexion puis réessayez.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

function PasswordPair({onSubmit, busy, label}: {onSubmit: (pw: string) => void; busy: boolean; label: string}) {
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [shown, setShown] = useState(false); const [err, setErr] = useState('');
  return <form onSubmit={e => { e.preventDefault(); setErr('');
    if (pw.length < 10) { setErr('Au moins 10 caractères.'); return; }
    if (pw !== pw2) { setErr('Les deux mots de passe ne correspondent pas.'); return; }
    onSubmit(pw); }} noValidate>
    <div className={`lg-field ${err ? 'lg-invalid' : ''}`}><label htmlFor="al-pw">Nouveau mot de passe</label>
      <div className="lg-pass"><input id="al-pw" type={shown ? 'text' : 'password'} autoComplete="new-password" value={pw} onChange={e => setPw(e.target.value)}/>
        <button type="button" onClick={() => setShown(x => !x)} aria-label={shown ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} aria-pressed={shown}><NavGlyph g={shown ? 'eyeOff' : 'eye'} size={18}/></button></div>
      <small className="lg-hint">Au moins 10 caractères.</small></div>
    <div className={`lg-field ${err ? 'lg-invalid' : ''}`}><label htmlFor="al-pw2">Confirmez le mot de passe</label>
      <input id="al-pw2" type={shown ? 'text' : 'password'} autoComplete="new-password" value={pw2} onChange={e => setPw2(e.target.value)}/>
      {err && <small role="alert">{err}</small>}</div>
    <button className="lg-submit" disabled={busy}>{busy ? <><i className="lg-spin"/>Enregistrement…</> : label}</button>
  </form>;
}

export function ForgotPasswordCard({onBack}: {onBack: () => void}) {
  const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false); const [done, setDone] = useState(''); const [err, setErr] = useState('');
  return <div className="lg-card" role="group" aria-labelledby="fp-title">
    <div className="lg-head"><span className="lg-step">Mot de passe oublié</span><h1 id="fp-title">Recevoir un lien</h1>
      <p>Saisissez l’adresse e-mail de votre compte EduSync. Un lien valable 30 minutes vous sera envoyé.</p></div>
    {done ? <div className="lg-ok" role="status"><NavGlyph g="checkCircle" size={16}/>{done}</div> :
      <form onSubmit={async e => { e.preventDefault(); setErr('');
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) { setErr('Saisissez une adresse e-mail valide.'); return; }
        setBusy(true);
        try { setDone((await forgotPassword(email.trim())).detail); } catch (x) { setErr(x instanceof Error ? x.message : 'Envoi impossible pour le moment.'); } finally { setBusy(false); } }} noValidate>
        <div className={`lg-field ${err ? 'lg-invalid' : ''}`}><label htmlFor="fp-email">Adresse e-mail</label>
          <input id="fp-email" type="email" inputMode="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} placeholder="nom@ecole.cd" autoFocus/>
          {err && <small role="alert">{err}</small>}</div>
        <button className="lg-submit" disabled={busy}>{busy ? <><i className="lg-spin"/>Envoi…</> : 'Envoyer le lien'}</button>
      </form>}
    <p className="lg-note">Comptes de la plateforme EduSync : la réinitialisation passe par un Manager Système.</p>
    <button type="button" className="lg-quiet" onClick={onBack}>Retour à la connexion</button>
  </div>;
}

// The platform keeps e-mail + password + 6-digit code (owner, 2026-10-24): the invitation sets the password, then the
// normal sign-in (pre-filled address) leads to the second-factor enrolment and the dashboard.
export function AccountLinkCard({link, onDone}: {link: AccountLink; onDone: (message: string, email?: string) => void}) {
  const [busy, setBusy] = useState(false); const [checking, setChecking] = useState(link.kind === 'invitation');
  const [err, setErr] = useState(''); const [inv, setInv] = useState<InvitationInfo | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (link.kind !== 'invitation') return;
    if (!link.token) { setChecking(false); setErr('Lien d’invitation incomplet. Demandez un nouveau lien.'); return; }
    const ctl = new AbortController();
    setChecking(true); setErr(''); setInv(null);
    invitationEvent('inspect', 'started');
    invitationRequest<InvitationInfo>('inspect', link.token, ctl.signal)
      .then(info => { if (!ctl.signal.aborted) { setInv(info); invitationEvent('inspect', 'valid'); } })
      .catch(e => { if (!ctl.signal.aborted) { setErr(e instanceof Error ? e.message : 'Vérification impossible.'); invitationEvent('inspect', 'failed'); } })
      .finally(() => { if (!ctl.signal.aborted) setChecking(false); });
    return () => ctl.abort();
  }, [link.kind, link.token, attempt]);
  useEffect(() => {
    if (link.kind !== 'invitation') return;
    const retry = () => setAttempt(n => n + 1);
    window.addEventListener('online', retry);
    return () => window.removeEventListener('online', retry);
  }, [link.kind]);
  async function submit(pw: string) {
    setBusy(true); setErr('');
    try {
      if (link.kind === 'reset') { await resetPassword(link.token, pw); onDone('Mot de passe modifié. Connectez-vous avec le nouveau mot de passe.'); }
      else {
        invitationEvent('accept', 'started');
        const r = await acceptInvitation(link.token, pw);
        invitationEvent('accept', 'activated');
        onDone(r.scope === 'PLATFORM' || inv?.scope === 'PLATFORM'
          ? 'Compte activé. Connectez-vous avec ce mot de passe : EduSync vous demandera ensuite d’installer le code à 6 chiffres qui protège la plateforme.'
          : 'Compte activé. Connectez-vous avec votre adresse e-mail et ce mot de passe.', r.email);
      }
    } catch (x) { if (link.kind === 'invitation') invitationEvent('accept', 'failed'); setErr(x instanceof Error ? x.message : 'Lien invalide ou expiré : demandez-en un nouveau.'); } finally { setBusy(false); }
  }
  const title = link.kind === 'reset' ? 'Nouveau mot de passe' : 'Activer votre compte';
  return <div className="lg-card" role="group" aria-labelledby="al-title">
    <div className="lg-head"><span className="lg-step">{link.kind === 'reset' ? 'Réinitialisation' : 'Invitation'}</span><h1 id="al-title">{title}</h1>
      <p>{link.kind === 'reset' ? 'Choisissez un nouveau mot de passe. Toutes vos sessions ouvertes seront fermées.'
        : inv ? `Bienvenue ${inv.full_name}${inv.school_name ? ` — ${inv.school_name}` : ''}. ${inv.scope === 'PLATFORM' ? 'Choisissez votre mot de passe. À votre première connexion, vous installerez le code à 6 chiffres qui protège la plateforme.' : 'Choisissez votre mot de passe.'}`
        : checking ? 'Vérification du lien…' : 'Vérification interrompue.'}</p></div>
    {checking && <p role="status">Vérification en cours…</p>}
    {inv && <PasswordPair onSubmit={pw => void submit(pw)} busy={busy} label="Activer mon compte"/>}
    {link.kind === 'reset' && <PasswordPair onSubmit={pw => void submit(pw)} busy={busy} label="Enregistrer"/>}
    {err && <div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{err}</div>}
    {err && link.kind === 'invitation' && <button type="button" className="lg-submit" disabled={busy} onClick={() => setAttempt(n => n + 1)}>Réessayer</button>}
    <p className="lg-note"><NavGlyph g="lock" size={14}/>Lien à usage unique : il ne fonctionne qu’une fois.</p>
    <button type="button" className="lg-quiet" onClick={() => onDone('')}>Retour à la connexion</button>
  </div>;
}
