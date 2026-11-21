// Regrouper les frères et sœurs (owner, 2026-11-21). Pupils taken over from the old software arrived each in a family
// of their own. EduSync proposes the families that share the same responsible AND the same phone; the school checks
// each group, picks the main family and confirms. Children and guardians join it; the others are kept as history.
// No amount is changed: charges, payments and decisions follow the child. A manual merge exists in the family sheet.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {familyMergeSuggestions, listFamilies, mergeFamilies, type MergeFamily, type MergeGroup, type SchoolFamily} from './api';
import {friendlyError} from './platform/errors';
import {confirmAction} from './platform/dialogs';

const DEFAULT_REASON = 'Frères et sœurs : même responsable et même téléphone';
const IGNORED_KEY = 'edusync.familyMerge.ignored';
const groupKey = (g: MergeGroup) => g.families.map(f => f.id).sort().join(',');
function readIgnored(): string[] { try { return JSON.parse(localStorage.getItem(IGNORED_KEY) || '[]'); } catch { return []; } }
function writeIgnored(v: string[]) { try { localStorage.setItem(IGNORED_KEY, JSON.stringify(v)); } catch { /* facultatif */ } }
const mainOf = (fams: MergeFamily[]) => [...fams].sort((a, b) => b.children.length - a.children.length || (a.contact_status === 'COMPLETE' ? -1 : 1))[0]?.id ?? '';

export function FamilyMergeSuggestions({token, onDone}: {token: string; onDone: () => Promise<void> | void}) {
  const [open, setOpen] = useState(false); const [groups, setGroups] = useState<MergeGroup[] | null>(null);
  const [ignored, setIgnored] = useState<string[]>(readIgnored); const [reason, setReason] = useState(DEFAULT_REASON);
  const [error, setError] = useState(''); const [shown, setShown] = useState(10);
  async function load() { try { setError(''); setGroups((await familyMergeSuggestions(token)).groups); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { if (open && groups === null) void load(); }, [open]);
  const visible = (groups ?? []).filter(g => !ignored.includes(groupKey(g)));
  function ignore(g: MergeGroup) { const next = [...ignored, groupKey(g)]; setIgnored(next); writeIgnored(next); }
  async function merged(g: MergeGroup) { setGroups(gs => (gs ?? []).filter(x => x !== g)); await onDone(); }
  if (!open) return <button type="button" className="softBtn familyMergeOpen" onClick={() => setOpen(true)}>Regrouper les frères et sœurs</button>;
  return <article className="schoolCard familyMerge" data-family-merge>
    <header><div><h3>Regrouper les frères et sœurs</h3>
      <p>EduSync propose les familles qui ont <b>le même responsable et le même téléphone</b>. Vérifiez chaque groupe, choisissez la famille principale, puis regroupez. Aucun montant n’est modifié : les frais, paiements et décisions restent attachés à chaque enfant.</p></div>
      <button type="button" className="ghost" onClick={() => setOpen(false)}>Fermer</button></header>
    <label className="familyMergeReason"><span>Motif (journal d’audit)</span><input value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/></label>
    {error && <p className="error">{error}</p>}
    {groups === null && !error && <p>Recherche des familles à regrouper…</p>}
    {groups !== null && !visible.length && <p className="familyMergeEmpty">Aucun regroupement proposé. Pour des frères et sœurs avec un téléphone différent, ouvrez la fiche d’une famille : « Ajouter une autre famille ».</p>}
    {!!visible.length && <p className="familyMergeCount">{visible.length} groupe(s) proposé(s) · {visible.reduce((n, g) => n + g.children, 0)} enfant(s)</p>}
    <div className="familyMergeGroups">{visible.slice(0, shown).map(g => <MergeGroupCard key={groupKey(g)} token={token} group={g} reason={reason} onMerged={() => merged(g)} onIgnore={() => ignore(g)}/>)}</div>
    {visible.length > shown && <button type="button" className="ghost" onClick={() => setShown(n => n + 10)}>Afficher 10 groupes de plus</button>}
    {ignored.length > 0 && <button type="button" className="textBtn" onClick={() => { setIgnored([]); writeIgnored([]); }}>Revoir les {ignored.length} groupe(s) écarté(s)</button>}
  </article>;
}

function MergeGroupCard({token, group, reason, onMerged, onIgnore}: {token: string; group: MergeGroup; reason: string; onMerged: () => void; onIgnore: () => void}) {
  const [main, setMain] = useState(mainOf(group.families)); const [kept, setKept] = useState<string[]>(group.families.map(f => f.id));
  const [busy, setBusy] = useState(false);
  const others = kept.filter(id => id !== main);
  async function run() {
    if (reason.trim().length < 3) { toast.error('Le motif est obligatoire.'); return; }
    if (!others.length) { toast.error('Gardez au moins deux familles cochées.'); return; }
    const target = group.families.find(f => f.id === main)!;
    const n = group.families.filter(f => others.includes(f.id)).reduce((s, f) => s + f.children.length, 0);
    if (!await confirmAction({title: 'Regrouper ces familles ?', message: `${n} enfant(s) rejoindront la famille ${target.code} (${target.display_name}). Les autres familles sont conservées dans l’historique. Aucun montant n’est modifié.`, confirmLabel: 'Regrouper'})) return;
    try { setBusy(true); const r = await mergeFamilies(token, {target_family_id: main, source_family_ids: others, reason: reason.trim()});
      toast.success(`${r.children_moved.length} enfant(s) regroupé(s) dans la famille ${r.family_code}`); onMerged(); }
    catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  return <section className="familyMergeGroup">
    <h4>{group.guardian} <small>· {group.phone}</small></h4>
    <ul>{group.families.map(f => <li key={f.id} className={kept.includes(f.id) ? '' : 'off'}>
      <label className="familyMergeMain"><input type="radio" name={`main-${groupKey(group)}`} checked={main === f.id} disabled={!kept.includes(f.id)} onChange={() => setMain(f.id)}/> Principale</label>
      <div><b>{f.code}</b> · {f.display_name}
        <small>{f.children.map(c => `${c.full_name}${c.class_label ? ` (${c.class_label})` : ''}`).join(' · ') || 'Aucun enfant'}</small></div>
      <label className="familyMergeKeep"><input type="checkbox" checked={kept.includes(f.id)} disabled={main === f.id}
        onChange={e => setKept(k => e.target.checked ? [...k, f.id] : k.filter(x => x !== f.id))}/> Inclure</label>
    </li>)}</ul>
    <div className="formActions"><button type="button" className="primaryBtn" disabled={busy || !others.length} onClick={run}>{busy ? 'Regroupement…' : `Regrouper (${others.length + 1} familles)`}</button>
      <button type="button" className="ghost" disabled={busy} onClick={onIgnore}>Pas la même famille</button></div>
  </section>;
}

// Manual merge from a family sheet: brothers and sisters whose families have a different phone.
export function AddFamilyToThis({token, family, onDone}: {token: string; family: {id: string; code: string; display_name: string}; onDone: () => Promise<void> | void}) {
  const [open, setOpen] = useState(false); const [q, setQ] = useState(''); const [found, setFound] = useState<SchoolFamily[]>([]);
  const [busy, setBusy] = useState(false); const [reason, setReason] = useState('Frères et sœurs');
  useEffect(() => { if (!open || q.trim().length < 2) { setFound([]); return; }
    const t = setTimeout(() => { listFamilies(token, q.trim(), {limit: 8}).then(r => setFound(r.items.filter(f => f.id !== family.id))).catch(() => setFound([])); }, 300);
    return () => clearTimeout(t); }, [q, open]);
  async function add(other: SchoolFamily) {
    if (reason.trim().length < 3) { toast.error('Le motif est obligatoire.'); return; }
    if (!await confirmAction({title: `Ajouter la famille ${other.code} ?`, message: `Ses ${other.child_count} enfant(s) et ses responsables rejoindront la famille ${family.code} (${family.display_name}). La famille ${other.code} est conservée dans l’historique. Aucun montant n’est modifié.`, confirmLabel: 'Regrouper'})) return;
    try { setBusy(true); const r = await mergeFamilies(token, {target_family_id: family.id, source_family_ids: [other.id], reason: reason.trim()});
      toast.success(`${r.children_moved.length} enfant(s) ajouté(s) à la famille ${r.family_code}`); setOpen(false); setQ(''); await onDone(); }
    catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  if (!open) return <button type="button" className="softBtn" onClick={() => setOpen(true)}>Ajouter une autre famille (frères et sœurs)</button>;
  return <div className="familyMergeManual">
    <label><span>Rechercher la famille d’un frère ou d’une sœur</span><input autoFocus value={q} placeholder="Nom de l’enfant, du responsable, téléphone ou code" onChange={e => setQ(e.target.value)}/></label>
    <label><span>Motif</span><input value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/></label>
    <ul>{found.map(f => <li key={f.id}><div><b>{f.code}</b> · {f.display_name}<small>{f.child_count} enfant(s)</small></div>
      <button type="button" className="primaryBtn" disabled={busy} onClick={() => add(f)}>Ajouter</button></li>)}</ul>
    <button type="button" className="ghost" onClick={() => setOpen(false)}>Annuler</button>
  </div>;
}
