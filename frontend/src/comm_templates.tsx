// Modèles de messages (2026-10-25). The server stores reusable templates (communications.templates.manage) with
// variables {ecole} {eleve} {classe} {responsable} {montant} {devise} {reste} {date} {recu}, but no screen exposed them.
// The cashier's communication role is precisely this (owner: « industrialise la communication en fonction de ce que le
// système prévoit pour lui »): prepare payment reminders and receipt messages that the roles allowed to send will use.
import React, {useEffect, useMemo, useRef, useState} from 'react';
import {toast} from 'sonner';
import {commTemplates, previewCommTemplate, saveCommTemplate, type CommTemplate} from './api';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';

const CHANNEL: Record<string, string> = {SMS: 'SMS', IN_APP: 'Notification', EMAIL: 'E-mail', PUSH: 'Push'};
const SAMPLE: Record<string, string> = {ecole: 'Complexe scolaire', eleve: 'KALALA Joseph', classe: '2e CG A', responsable: 'M. Mbuyi', montant: '15 000', devise: 'FC', reste: '30 000', date: '25/10/2026', recu: 'REC-2026-000014'};
const STARTERS = [
  {code: 'RELANCE_FRAIS', label: 'Relance de paiement', body: 'Bonjour {responsable}, {eleve} ({classe}) reste redevable de {reste} {devise} à {ecole}. Merci de régulariser avant le {date}.'},
  {code: 'RECU_PAIEMENT', label: 'Confirmation de paiement', body: '{ecole} : paiement de {montant} {devise} reçu pour {eleve}, reçu {recu}. Reste à payer : {reste} {devise}. Merci.'},
];
const slug = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 96);

export function CommTemplates({token, can}: {token: string; can: (p: string) => boolean}) {
  const manage = can('communications.templates.manage');
  const [items, setItems] = useState<CommTemplate[] | null>(null); const [vars, setVars] = useState<string[]>([]); const [err, setErr] = useState('');
  const [edit, setEdit] = useState<Partial<CommTemplate> | null>(null);
  const load = () => commTemplates(token).then(r => { setItems(r.items); setVars(r.variables); }).catch(e => setErr(friendlyError(e)));
  useEffect(() => { void load(); }, [token]);
  return <section className="commCard ctpl">
    <div className="ctpl-head"><div><h3>Modèles de messages</h3><p>Textes prêts à l’emploi pour les relances de paiement et les confirmations de reçu. Les variables entre accolades sont remplies automatiquement à l’envoi.</p></div>
      {manage && <button type="button" className="primaryBtn" onClick={() => setEdit({channel: 'SMS', body: '', label: '', code: ''})}><NavGlyph g="plus" size={16}/> Nouveau modèle</button>}</div>
    {err && <div className="error" role="alert">{err}</div>}
    {items && items.length === 0 && <div className="ctpl-empty"><b>Aucun modèle pour l’instant.</b>{manage && <><span>Commencez avec un modèle courant :</span><div className="ctpl-starters">{STARTERS.map(s => <button type="button" key={s.code} onClick={() => setEdit({...s, channel: 'SMS'})}>{s.label}</button>)}</div></>}</div>}
    <div className="ctpl-list">{(items ?? []).map(t => <button type="button" key={t.id} className="ctpl-item" onClick={() => setEdit(t)} disabled={!manage} aria-label={`Modèle ${t.label}`}>
      <span><b>{t.label}</b><small>{CHANNEL[t.channel] ?? t.channel} · {t.code} · version {t.version}</small></span><p>{t.body}</p></button>)}</div>
    {!items && !err && <p className="ctpl-empty">Chargement…</p>}
    {edit && <TemplateEditor token={token} vars={vars} value={edit} onClose={() => setEdit(null)} onSaved={async () => { setEdit(null); await load(); }}/>}
  </section>;
}

function TemplateEditor({token, vars, value, onClose, onSaved}: {token: string; vars: string[]; value: Partial<CommTemplate>; onClose: () => void; onSaved: () => Promise<void>}) {
  const [label, setLabel] = useState(value.label ?? ''); const [code, setCode] = useState(value.code ?? ''); const [channel, setChannel] = useState(value.channel ?? 'SMS');
  const [body, setBody] = useState(value.body ?? ''); const [busy, setBusy] = useState(false); const [err, setErr] = useState(''); const [prev, setPrev] = useState<{text: string; sms_units: number} | null>(null);
  const area = useRef<HTMLTextAreaElement>(null); const isNew = !value.id;
  const unknown = useMemo(() => [...body.matchAll(/\{([^}]*)\}/g)].map(m => m[1]).filter(v => !vars.includes(v)), [body, vars]);
  useEffect(() => { if (!body.trim() || unknown.length) { setPrev(null); return; } const t = setTimeout(() => previewCommTemplate(token, body, SAMPLE).then(setPrev).catch(() => setPrev(null)), 300); return () => clearTimeout(t); }, [body, unknown.length, token]);
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [onClose]);
  function insert(v: string) { const el = area.current; const at = el?.selectionStart ?? body.length; const next = `${body.slice(0, at)}{${v}}${body.slice(el?.selectionEnd ?? at)}`; setBody(next); requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + v.length + 2, at + v.length + 2); }); }
  const finalCode = code || slug(label);
  async function save() {
    if (label.trim().length < 2) { setErr('Donnez un nom au modèle (2 caractères au moins).'); return; }
    if (!/^[A-Z0-9_]{2,96}$/.test(finalCode)) { setErr('Code : lettres majuscules, chiffres et _ uniquement.'); return; }
    if (!body.trim()) { setErr('Le texte du message est vide.'); return; }
    if (unknown.length) { setErr(`Variable inconnue : {${unknown[0]}}. Utilisez les boutons ci-dessous.`); return; }
    try { setBusy(true); setErr(''); await saveCommTemplate(token, {code: finalCode, label: label.trim(), channel, body: body.trim()}); toast.success(isNew ? 'Modèle créé' : 'Modèle mis à jour'); await onSaved(); }
    catch (e) { setErr(friendlyError(e)); } finally { setBusy(false); }
  }
  return <div className="modalBackdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="modalCard ctpl-editor" role="dialog" aria-modal="true" aria-label={isNew ? 'Nouveau modèle' : `Modifier ${value.label}`}>
    <div className="modalHead"><div><h3>{isNew ? 'Nouveau modèle de message' : `Modifier « ${value.label} »`}</h3><p>Le texte est vérifié avant l’enregistrement ; l’aperçu utilise des données d’exemple.</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    {err && <div className="error" role="alert">{err}</div>}
    <div className="formGrid"><label>Nom du modèle<input value={label} maxLength={180} onChange={e => setLabel(e.target.value)} placeholder="Relance de paiement" autoFocus/></label>
      <label>Canal<select value={channel} onChange={e => setChannel(e.target.value)}>{Object.entries(CHANNEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      {isNew && <label className="span2">Code (automatique)<input value={finalCode} onChange={e => setCode(slug(e.target.value))} maxLength={96}/></label>}
      <label className="span2">Texte du message<textarea ref={area} rows={5} maxLength={1000} value={body} onChange={e => setBody(e.target.value)} aria-invalid={unknown.length > 0}/></label></div>
    <div className="ctpl-vars" aria-label="Variables">{vars.map(v => <button type="button" key={v} onClick={() => insert(v)}>{`{${v}}`}</button>)}</div>
    {prev && <div className="ctpl-preview"><small>Aperçu{channel === 'SMS' ? ` · ${prev.sms_units} SMS` : ''}</small><p>{prev.text}</p></div>}
    <div className="modalActions"><button type="button" className="ghost" onClick={onClose}>Annuler</button><button type="button" disabled={busy} onClick={() => void save()}>{busy ? 'Enregistrement…' : 'Enregistrer le modèle'}</button></div>
  </div></div>;
}
