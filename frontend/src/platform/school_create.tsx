import React, {useState} from 'react';
import {toast} from 'sonner';
import {createSchoolFull} from '../api';
import {Modal} from './account';
import {friendlyError} from './errors';
import './school_create.css';

type F = {name: string; code: string; email: string; phone: string; address: string; city: string; province: string};
const EMPTY: F = {name: '', code: '', email: '', phone: '', address: '', city: '', province: ''};

function validate(v: F): Partial<Record<keyof F, string>> {
  const e: Partial<Record<keyof F, string>> = {};
  if (v.name.trim().length < 2) e.name = 'Le nom de l’école est obligatoire.';
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{1,31}$/.test(v.code.trim())) e.code = 'Code : 2 à 32 lettres, chiffres ou tirets (ex. : EXCELLENCIA).';
  if (v.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.email.trim())) e.email = 'Adresse e-mail invalide.';
  if (v.phone && !/^\+?[0-9 ().-]{6,24}$/.test(v.phone.trim())) e.phone = 'Numéro invalide (ex. : +243 81 000 0000).';
  return e;
}

/** School creation with identity, contacts and address. One idempotency key per dialog: a double click or a lost
 *  response never creates two schools. The logo is uploaded later by the school itself (validated, private). */
export function SchoolCreateDialog({token, onClose, onCreated}: {token: string; onClose: () => void; onCreated: (school: {id: string; name: string}) => void}) {
  const [v, setV] = useState<F>(EMPTY); const [errors, setErrors] = useState<Partial<Record<keyof F, string>>>({});
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [key] = useState(() => crypto.randomUUID());
  const set = (k: keyof F) => (e: React.ChangeEvent<HTMLInputElement>) => setV({...v, [k]: k === 'code' ? e.target.value.toUpperCase() : e.target.value});
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    const found = validate(v); setErrors(found);
    if (Object.keys(found).length) { document.getElementById(`sc-${Object.keys(found)[0]}`)?.focus(); return; }
    const opt = (s: string) => s.trim() || null;
    try {
      setBusy(true);
      const s = await createSchoolFull(token, key, {name: v.name.trim(), code: v.code.trim().toUpperCase(), email: opt(v.email), phone: opt(v.phone), address: opt(v.address), city: opt(v.city), province: opt(v.province)});
      toast.success(`École « ${s.name} » créée. Étape suivante : son administrateur initial.`); onCreated(s);
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  const field = (k: keyof F, label: string, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => <label className="sc-field">
    <span>{label}</span><input id={`sc-${k}`} value={v[k]} onChange={set(k)} aria-invalid={!!errors[k]} aria-describedby={errors[k] ? `sc-${k}-err` : undefined} {...extra}/>
    {errors[k] && <small id={`sc-${k}-err`} role="alert">{errors[k]}</small>}</label>;
  return <Modal title="Nouvelle école" subtitle="L’école est créée active. Son administrateur initial est l’étape suivante ; le logo est ajouté ensuite par l’école." onClose={onClose} wide>
    <form className="es-form sc-form" onSubmit={submit} noValidate>
      <fieldset><legend>Identité</legend><div className="sc-grid">
        {field('name', 'Nom de l’école *', {autoComplete: 'organization', maxLength: 160})}
        {field('code', 'Code établissement *', {autoCapitalize: 'characters', spellCheck: false, maxLength: 32, placeholder: 'EXCELLENCIA'})}
      </div></fieldset>
      <fieldset><legend>Contacts</legend><div className="sc-grid">
        {field('email', 'E-mail de l’école', {type: 'email', inputMode: 'email', maxLength: 320})}
        {field('phone', 'Téléphone', {type: 'tel', inputMode: 'tel', maxLength: 24, placeholder: '+243 …'})}
      </div></fieldset>
      <fieldset><legend>Adresse</legend><div className="sc-grid">
        {field('address', 'Adresse', {maxLength: 300, autoComplete: 'street-address'})}
        {field('city', 'Ville', {maxLength: 120, autoComplete: 'address-level2'})}
        {field('province', 'Province', {maxLength: 120, autoComplete: 'address-level1'})}
      </div></fieldset>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><button className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Création…' : 'Créer l’école'}</button></div>
    </form>
  </Modal>;
}
