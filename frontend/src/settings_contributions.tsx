// Contributions en nature (settings audit 2026-11-06): the list first, each contribution can be corrected or deactivated
// (the API already allowed it, the screen did not), the internal code is never shown, and every error is visible.
import React, {useState} from 'react';
import {toast} from 'sonner';
import {createSettingsContribution, updateSettingsContribution, type SettingsContribution} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {NavGlyph} from './platform/nav_icons';
import {autoCode, CONTRIBUTION_PRESETS} from './settings_wizards';

const qtyOk = (v: string) => /^\d+([.,]\d{1,3})?$/.test(v.trim());
const norm = (v: string) => v.trim().replace(',', '.');
const fmt = (v?: string | number) => Number(v ?? 0).toLocaleString('fr-FR', {maximumFractionDigits: 3});
/** « 3 pièces », « 2 rouleaux », « 1 rame » (simple French plural of the unit). */
export function unitLabel(n: number, unit: string): string { const u = unit.trim(); if (n < 2 || /[sxz]$/i.test(u) || u.includes(' ')) return u; return /(eau|eu|au)$/i.test(u) ? `${u}x` : `${u}s`; }

type Draft = {label: string; unit: string; quantity: string};
function check(d: Draft, others: SettingsContribution[]): string {
  if (d.label.trim().length < 2) return 'Indiquez le nom de la contribution, par exemple « Rame de papier ».';
  if (others.some(x => x.label.trim().toLowerCase() === d.label.trim().toLowerCase())) return 'Une contribution porte déjà ce nom.';
  if (!d.unit.trim()) return 'Indiquez l’unité (pièce, rame, rouleau…).';
  if (!qtyOk(d.quantity || '0')) return 'Quantité exigée : un nombre (0 si elle est facultative).';
  return '';
}

export function ContributionsSettings({token, items, can, onDone}: {token: string; items: SettingsContribution[]; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const manage = can('settings.contributions.manage');
  const [adding, setAdding] = useState<Draft | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function create(e: React.FormEvent) {
    e.preventDefault(); if (!adding) return; const msg = check(adding, items); setError(msg); if (msg) return;
    try {
      setBusy(true);
      await createSettingsContribution(token, {code: autoCode(adding.label, items.map(x => x.code)), label: adding.label.trim(), unit: adding.unit.trim(), required_quantity: Number(norm(adding.quantity || '0'))});
      toast.success(`${adding.label.trim()} ajouté`); setAdding(null); await onDone();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  const active = items.filter(x => x.enabled);
  return <section className="panel contributionsPage">
    <div className="panelHead"><div><h3>Contributions en nature</h3><p>Fournitures ou biens attendus de chaque élève (savon, rame de papier…). Les dépôts réels sont enregistrés dans Effectifs &amp; dépôts.</p></div>
      {manage && !adding && <button type="button" className="primaryBtn" onClick={() => { setError(''); setAdding({label: '', unit: 'pièce', quantity: '1'}); }}>Nouvelle contribution</button>}</div>
    {error && !adding && <div className="error" role="alert">{error}</div>}
    {manage && !adding && CONTRIBUTION_PRESETS.some(p => !items.some(x => x.label.toLowerCase() === p.label.toLowerCase())) && <div className="sw-chips sw-presets">
      {CONTRIBUTION_PRESETS.filter(p => !items.some(x => x.label.toLowerCase() === p.label.toLowerCase())).map(p =>
        <button key={p.label} type="button" className="sw-chip" onClick={() => { setError(''); setAdding({label: p.label, unit: p.unit, quantity: String(p.qty)}); }}>+ {p.label}</button>)}</div>}
    {adding && <form className="contribEditor" onSubmit={create} noValidate>
      {error && <div className="error" role="alert">{error}</div>}
      <fieldset disabled={busy}><div className="contribGrid">
        <FormField label="Contribution *"><input value={adding.label} maxLength={140} autoFocus placeholder="Ex. Rame de papier" onChange={e => setAdding({...adding, label: e.target.value})}/></FormField>
        <FormField label="Unité *"><input value={adding.unit} maxLength={48} placeholder="pièce, rame…" onChange={e => setAdding({...adding, unit: e.target.value})}/></FormField>
        <FormField label="Quantité exigée par élève" hint="0 = facultative."><input inputMode="decimal" value={adding.quantity} onChange={e => setAdding({...adding, quantity: e.target.value})}/></FormField>
      </div>
      <div className="formActions"><button type="button" className="ghost" onClick={() => { setAdding(null); setError(''); }}>Annuler</button><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Ajouter'}</button></div></fieldset>
    </form>}
    {items.length === 0 && !adding && <div className="emptyGuide"><b>Aucune contribution</b><p>Ajoutez ce que l’école demande à chaque élève : savon, rame de papier, papier hygiénique…</p></div>}
    {items.length > 0 && <p className="contribSummary">{active.length} contribution{active.length > 1 ? 's' : ''} active{active.length > 1 ? 's' : ''}{items.length > active.length ? ` · ${items.length - active.length} désactivée${items.length - active.length > 1 ? 's' : ''}` : ''}</p>}
    <ul className="contribList">{items.map(x => <ContributionRow key={x.id} token={token} c={x} others={items.filter(o => o.id !== x.id)} can={can} onDone={onDone}/>)}</ul>
  </section>;
}

function ContributionRow({token, c, others, can, onDone}: {token: string; c: SettingsContribution; others: SettingsContribution[]; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const [edit, setEdit] = useState<Draft | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const manage = can('settings.contributions.manage'); const canToggle = c.enabled ? can('settings.contributions.activate') || manage : manage;
  async function save(d: Draft, enabled: boolean) {
    const msg = check(d, others); setError(msg); if (msg) return;
    try {
      setBusy(true);
      await updateSettingsContribution(token, c, {label: d.label.trim(), unit: d.unit.trim(), enabled, required_quantity: norm(d.quantity || '0')});
      toast.success(enabled === c.enabled ? `${d.label.trim()} mis à jour` : enabled ? `${c.label} réactivé` : `${c.label} désactivé : il n’est plus demandé aux nouveaux élèves`);
      setEdit(null); await onDone();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  const current: Draft = {label: c.label, unit: c.unit, quantity: String(Number(c.required_quantity ?? 0))};
  const required = Number(c.required_quantity ?? 0);
  return <li className={`contribRow ${c.enabled ? '' : 'off'}`}>
    <span className="contribIcon" aria-hidden="true"><NavGlyph g="box" size={18}/></span>
    <div className="contribText"><b>{c.label}</b><small>{required > 0 ? `${fmt(required)} ${unitLabel(required, c.unit)} par élève` : `Facultatif · unité : ${c.unit}`}</small></div>
    <em className={`pill ${c.enabled ? 'ready' : ''}`}>{c.enabled ? 'Active' : 'Désactivée'}</em>
    {(manage || canToggle) && !edit && <div className="contribActions">
      {manage && c.enabled && <button type="button" className="ghost" onClick={() => { setError(''); setEdit(current); }}>Modifier</button>}
      {canToggle && <button type="button" className="ghost" disabled={busy} onClick={() => void save(current, !c.enabled)}>{c.enabled ? 'Désactiver' : 'Réactiver'}</button>}
    </div>}
    {error && !edit && <div className="error contribError" role="alert">{error}</div>}
    {edit && <form className="contribEditor contribInline" onSubmit={e => { e.preventDefault(); void save(edit, c.enabled); }} noValidate>
      {error && <div className="error" role="alert">{error}</div>}
      <fieldset disabled={busy}><div className="contribGrid">
        <FormField label="Contribution *"><input value={edit.label} maxLength={140} onChange={e => setEdit({...edit, label: e.target.value})}/></FormField>
        <FormField label="Unité *"><input value={edit.unit} maxLength={48} onChange={e => setEdit({...edit, unit: e.target.value})}/></FormField>
        <FormField label="Quantité exigée par élève"><input inputMode="decimal" value={edit.quantity} onChange={e => setEdit({...edit, quantity: e.target.value})}/></FormField>
      </div>
      <div className="formActions"><button type="button" className="ghost" onClick={() => { setEdit(null); setError(''); }}>Annuler</button><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div></fieldset>
    </form>}
  </li>;
}
