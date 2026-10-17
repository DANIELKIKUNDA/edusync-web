// Account links sent by e-mail (EMAIL_TRANSACTIONAL_INTEGRATION.md): forgotten password, new password from a recovery
// link, invitation acceptance. The single-use token arrives in the URL fragment (#reset=… / #invitation=…), is read once
// and removed from the address bar at once (never stored, never sent in a request line).
import React, {useEffect, useState} from 'react';
import {NavGlyph} from './platform/nav_icons';
import {acceptInvitation, forgotPassword, invitationDetails, resetPassword} from './messaging_api';

export type AccountLink = {kind: 'reset' | 'invitation'; token: string};

/** Reads and clears #reset=… / #invitation=… once. */
export function takeAccountLink(): AccountLink | null {
  const m = /^#(reset|invitation)=([A-Za-z0-9_-]{20,200})$/.exec(window.location.hash || '');
  if (!m) return null;
  history.replaceState(history.state, '', window.location.pathname + window.location.search);
  return {kind: m[1] as AccountLink['kind'], token: m[2]};
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
    <p className="lg-note">Comptes plateforme (Atelier Pro) : la réinitialisation passe par un Manager Système.</p>
    <button type="button" className="lg-quiet" onClick={onBack}>Retour à la connexion</button>
  </div>;
}

export function AccountLinkCard({link, onDone}: {link: AccountLink; onDone: (message: string) => void}) {
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const [inv, setInv] = useState<{full_name: string; school_name: string | null} | null>(null); const [invalid, setInvalid] = useState(false);
  useEffect(() => { if (link.kind === 'invitation') invitationDetails(link.token).then(setInv).catch(() => setInvalid(true)); }, [link]);
  async function submit(pw: string) {
    setBusy(true); setErr('');
    try {
      if (link.kind === 'reset') { await resetPassword(link.token, pw); onDone('Mot de passe modifié. Connectez-vous avec le nouveau mot de passe.'); }
      else { await acceptInvitation(link.token, pw); onDone('Compte activé. Connectez-vous avec votre adresse e-mail et ce mot de passe.'); }
    } catch (x) { setErr(x instanceof Error ? x.message : 'Lien invalide ou expiré : demandez-en un nouveau.'); } finally { setBusy(false); }
  }
  const title = link.kind === 'reset' ? 'Nouveau mot de passe' : 'Activer votre compte';
  return <div className="lg-card" role="group" aria-labelledby="al-title">
    <div className="lg-head"><span className="lg-step">{link.kind === 'reset' ? 'Réinitialisation' : 'Invitation'}</span><h1 id="al-title">{title}</h1>
      <p>{link.kind === 'reset' ? 'Choisissez un nouveau mot de passe. Toutes vos sessions ouvertes seront fermées.'
        : inv ? `Bienvenue ${inv.full_name}${inv.school_name ? ` — ${inv.school_name}` : ''}. Choisissez votre mot de passe.` : 'Vérification du lien…'}</p></div>
    {invalid ? <div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>Lien invalide ou expiré : demandez une nouvelle invitation à votre école.</div>
      : (link.kind === 'reset' || inv) && <PasswordPair onSubmit={pw => void submit(pw)} busy={busy} label={link.kind === 'reset' ? 'Enregistrer' : 'Activer mon compte'}/>}
    {err && <div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{err}</div>}
    <p className="lg-note"><NavGlyph g="lock" size={14}/>Lien à usage unique : il ne fonctionne qu’une fois.</p>
    <button type="button" className="lg-quiet" onClick={() => onDone('')}>Retour à la connexion</button>
  </div>;
}
