import React, {useCallback, useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {adoptOfficialProgrammes, discardProgrammeDraft, getProgramme, getProgrammes, moveProgrammeLine, openProgrammeDraft, removeProgrammeLine,
  saveProgrammeLine, searchCourses, validateProgramme, type ProgLine, type ProgrammeItem, type ProgrammeList, type ProgrammeView} from './api';
import {Modal} from './platform/account';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {Button, EmptyState, Skeleton} from './platform/ui';

/* V2 lot 2 — programmes de l'école (owner 2026-11-22). One click adopts the official programmes; a change goes through a
   new version (draft → validated; the old one is archived). For each course the school types ONE number per term (the
   points of a period): EduSync shows the second period and the exam (twice the period) — the owner's rule by design. */

const TERM_SHORT = {TRIMESTRIEL: ['1er trim.', '2e trim.', '3e trim.'], SEMESTRIEL: ['1er sem.', '2e sem.']} as const;
const msg = friendlyError;

export function ProgrammesTab({token, onChanged}: {token: string; onChanged?: () => void}) {
  const [data, setData] = useState<ProgrammeList | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [open, setOpen] = useState<null | {id?: string; ref?: string}>(null);
  const load = useCallback(() => { setError(''); getProgrammes(token).then(setData).catch(e => setError(msg(e))); }, [token]);
  useEffect(load, [load]);
  async function adopt() {
    setBusy('adopt');
    try { const r = await adoptOfficialProgrammes(token); toast.success(`${r.adopted} programme${r.adopted > 1 ? 's' : ''} officiel${r.adopted > 1 ? 's' : ''} en service`); load(); onChanged?.(); }
    catch (e) { toast.error(msg(e)); } finally { setBusy(''); }
  }
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Programmes indisponibles</b><small>{error}</small></div><Button onClick={load}>Réessayer</Button></div>;
  if (!data) return <Skeleton lines={6}/>;
  if (data.items.length === 0) return <EmptyState icon="layers" title="Aucune classe reliée" text="Reliez d’abord les classes de l’école aux classes officielles (onglet « Classes »)."/>;
  const s = data.summary; const canAdopt = s.adoptable > 0 && data.items.some(i => i.can_manage);
  return <>
    <div className="pg-summary" aria-label="Résumé">
      <div className={s.in_use === s.classes ? 'pg-ok' : ''}><b>{s.in_use}/{s.classes}</b><small>programmes en service</small></div>
      <div className={s.adoptable ? 'pg-warn' : ''}><b>{s.adoptable}</b><small>à adopter</small></div>
      <div className={s.drafts ? 'pg-warn' : ''}><b>{s.drafts}</b><small>brouillons en cours</small></div>
      <div className={s.without_official ? 'pg-warn' : ''}><b>{s.without_official}</b><small>à construire (sans programme officiel)</small></div>
    </div>
    {canAdopt && <div className="pg-callout"><NavGlyph g="sparkles" size={18}/><div><b>Utilisez les programmes officiels du MINEDUC</b>
      <small>{s.adoptable} classe{s.adoptable > 1 ? 's' : ''} : cours, ordre du bulletin et points, prêts en un clic. Vous pourrez les ajuster ensuite.</small></div>
      <Button variant="primary" disabled={!!busy} onClick={() => void adopt()}>{busy === 'adopt' ? 'Mise en service…' : `Utiliser les ${s.adoptable} programmes officiels`}</Button></div>}
    <ul className="pp-list">{data.items.map(i => <ProgrammeRow key={i.ref_class_code} item={i} onOpen={(id, ref) => setOpen({id, ref})}/>)}</ul>
    {open && <ProgrammeEditor token={token} id={open.id} refClass={open.ref} onClose={() => { setOpen(null); load(); onChanged?.(); }}/>}
  </>;
}

function ProgrammeRow({item, onOpen}: {item: ProgrammeItem; onOpen: (id?: string, ref?: string) => void}) {
  const status = item.draft ? {label: 'Brouillon en cours', tone: 'warn'} : item.in_use ? {label: 'En service', tone: 'ok'}
    : item.has_official ? {label: 'À adopter', tone: 'info'} : {label: 'À construire', tone: 'warn'};
  return <li>
    <div className="pp-main"><span className="pg-code">{item.ref_class_code}</span><b>{item.label}</b>
      <small>{item.classes.length > 3 ? `${item.classes.slice(0, 3).join(', ')} et ${item.classes.length - 3} autres` : item.classes.join(', ')}</small></div>
    <span className={`pc-chip pc-${status.tone}`}>{status.label}{item.in_use && !item.draft ? ` · ${item.in_use.lines} cours` : ''}</span>
    <div className="pp-act">
      {item.draft ? <Button size="sm" variant="primary" onClick={() => onOpen(item.draft!.id)}>Continuer</Button>
        : item.in_use ? <Button size="sm" onClick={() => onOpen(item.in_use!.id)}>Voir</Button>
        : item.can_manage ? <Button size="sm" onClick={() => onOpen(undefined, item.ref_class_code)}>{item.has_official ? 'Ajuster avant' : 'Construire'}</Button> : null}
    </div>
  </li>;
}

function ProgrammeEditor({token, id, refClass, onClose}: {token: string; id?: string; refClass?: string; onClose: () => void}) {
  const [view, setView] = useState<ProgrammeView | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  useEffect(() => { (id ? getProgramme(token, id) : openProgrammeDraft(token, refClass!)).then(setView).catch(e => setError(msg(e))); }, [token, id, refClass]);
  async function act(key: string, fn: () => Promise<ProgrammeView>, ok?: string) {
    setBusy(key); setError('');
    try { setView(await fn()); if (ok) toast.success(ok); return true; } catch (e) { setError(msg(e)); return false; } finally { setBusy(''); }
  }
  const draft = view?.status === 'DRAFT'; const editable = !!view && draft && view.can_manage;
  const labels = view ? TERM_SHORT[view.structure] : [];
  return <Modal wide title={view ? `${view.ref_class_code} · ${view.label}` : 'Programme'}
    subtitle={view ? (draft ? 'Brouillon : vos changements ne sont appliqués qu’après validation' : view.status === 'VALIDATED' ? 'En service' : 'Archivé') : undefined} onClose={onClose}>
    {!view && !error && <Skeleton lines={8}/>}
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {view && <div className="pp-editor">
      {view.status === 'VALIDATED' && view.can_manage && <div className="pg-callout"><NavGlyph g="info" size={18}/><div><b>Ce programme est en service.</b>
        <small>Pour le changer, créez une nouvelle version : l’actuelle reste en service jusqu’à la validation de la nouvelle.</small></div>
        <Button variant="primary" disabled={!!busy} onClick={() => void act('draft', () => openProgrammeDraft(token, view.ref_class_code))}>Créer une nouvelle version</Button></div>}
      {editable && <p className="pp-help"><NavGlyph g="sparkles" size={15}/><span>Pour chaque cours, tapez <b>les points d’une période</b>. EduSync calcule la 2<sup>e</sup> période et <b>l’examen, qui vaut le double</b>.</span></p>}
      {editable && !view.has_official && view.lines.length === 0 && <p className="pp-help">Cette classe n’a pas de programme officiel : ajoutez ses cours ci-dessous.</p>}
      <ol className="pp-lines">{view.lines.map((l, i) => <LineRow key={l.course_code} line={l} labels={[...labels]} editable={editable} first={i === 0} last={i === view.lines.length - 1} busy={!!busy}
        onSave={body => act(l.course_code, () => saveProgrammeLine(token, view.id, l.course_code, body), 'Cours enregistré')}
        onRemove={() => act(l.course_code, () => removeProgrammeLine(token, view.id, l.course_code), `${l.label} retiré`)}
        onMove={dir => act(l.course_code, () => moveProgrammeLine(token, view.id, l.course_code, dir))}/>)}</ol>
      {view.lines.length > 0 && <div className="pp-totals">
        <b>Maxima généraux</b>
        {labels.map((t, k) => { const p = view.totals[(['max_p1', 'max_p3', 'max_p5'] as const)[k]]; const e = view.totals[(['max_ex1', 'max_ex2', 'max_ex3'] as const)[k]];
          return <span key={t}>{t} : <b>{p}</b> par période · examen <b>{e}</b></span>; })}
      </div>}
      {view.removed_official.length > 0 && <p className="pp-removed">Cours officiels retirés : {view.removed_official.map(r => r.label).join(', ')}.</p>}
      {editable && <AddCourse token={token} labels={[...labels]} existing={new Set(view.lines.map(l => l.course_code))} busy={!!busy}
        onAdd={(code, body) => act(code, () => saveProgrammeLine(token, view.id, code, body), 'Cours ajouté')}/>}
      {editable && <footer className="pp-foot">
        {confirmDiscard ? <><span>Abandonner ce brouillon ?</span>
          <Button variant="danger" disabled={!!busy} onClick={() => void discardProgrammeDraft(token, view.id).then(() => { toast.success('Brouillon abandonné'); onClose(); }).catch(e => setError(msg(e)))}>Oui, abandonner</Button>
          <Button variant="quiet" onClick={() => setConfirmDiscard(false)}>Non</Button></>
          : <><Button variant="quiet" onClick={() => setConfirmDiscard(true)}>Abandonner le brouillon</Button>
            <Button variant="primary" icon="checkCircle" disabled={!!busy || view.lines.length === 0}
              onClick={() => void act('validate', () => validateProgramme(token, view.id), 'Programme validé et mis en service')}>{busy === 'validate' ? 'Validation…' : 'Valider ce programme'}</Button></>}
      </footer>}
    </div>}
  </Modal>;
}

function LineRow({line, labels, editable, first, last, busy, onSave, onRemove, onMove}: {line: ProgLine; labels: string[]; editable: boolean; first: boolean; last: boolean; busy: boolean;
  onSave: (b: {term_points: number[]; has_exam: boolean; mandatory: boolean}) => Promise<boolean>; onRemove: () => void; onMove: (d: 'up' | 'down') => void}) {
  const [pts, setPts] = useState(line.term_points.map(String));
  const [exam, setExam] = useState(line.has_exam);
  useEffect(() => { setPts(line.term_points.map(String)); setExam(line.has_exam); }, [line]);
  const dirty = pts.some((p, i) => Number(p) !== line.term_points[i]) || exam !== line.has_exam;
  const removable = line.source === 'ECOLE' || !line.mandatory;
  return <li className={dirty ? 'pp-dirty' : ''}>
    <div className="pp-course">
      <b>{line.label}</b>
      <span className="pp-badges">{line.source === 'ECOLE' && <em className="pp-b-add">Ajout de l’école</em>}{line.modified && <em className="pp-b-mod">Modifié</em>}
        {!line.mandatory && <em>Facultatif</em>}{!line.has_exam && <em>Sans examen</em>}</span>
    </div>
    {editable ? <div className="pp-inputs">
      {labels.map((t, k) => <label key={t}><span>{t}</span><input type="number" inputMode="numeric" min={0} max={500} value={pts[k] ?? ''}
        onChange={e => setPts(x => x.map((y, j) => j === k ? e.target.value.replace(/\D/g, '').slice(0, 3) : y))} aria-label={`${line.label} — points d’une période, ${t}`}/>
        <small>{exam ? `examen ${2 * Number(pts[k] || 0)}` : 'pas d’examen'}</small></label>)}
      <label className="pp-check"><input type="checkbox" checked={exam} onChange={e => setExam(e.target.checked)}/>Avec examen</label>
    </div> : <div className="pp-read">{labels.map((t, k) => <span key={t}>{t} <b>{line.term_points[k]}</b>{line.has_exam ? <> · ex. <b>{2 * line.term_points[k]}</b></> : null}</span>)}</div>}
    {editable && <div className="pp-tools">
      {dirty && <Button size="sm" variant="primary" disabled={busy} onClick={() => void onSave({term_points: pts.map(p => Number(p || 0)), has_exam: exam, mandatory: line.mandatory})}>Enregistrer</Button>}
      <button type="button" className="pp-icon pp-up" aria-label={`Monter ${line.label}`} disabled={busy || first} onClick={() => onMove('up')}><NavGlyph g="chevronDown" size={18}/></button>
      <button type="button" className="pp-icon pp-down" aria-label={`Descendre ${line.label}`} disabled={busy || last} onClick={() => onMove('down')}><NavGlyph g="chevronDown" size={18}/></button>
      <button type="button" className="pp-icon pp-del" aria-label={removable ? `Retirer ${line.label}` : `${line.label} : cours obligatoire`} title={removable ? 'Retirer' : 'Cours obligatoire du programme officiel'}
        disabled={busy || !removable} onClick={onRemove}><NavGlyph g="trash" size={17}/></button>
    </div>}
  </li>;
}

function AddCourse({token, labels, existing, busy, onAdd}: {token: string; labels: string[]; existing: Set<string>; busy: boolean;
  onAdd: (code: string, b: {term_points: number[]; has_exam: boolean; mandatory: boolean}) => Promise<boolean>}) {
  const [q, setQ] = useState(''); const [results, setResults] = useState<{code: string; label: string}[]>([]);
  const [picked, setPicked] = useState<{code: string; label: string} | null>(null);
  const [pts, setPts] = useState<string[]>(labels.map(() => '10')); const [exam, setExam] = useState(true);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (q.trim().length < 2) { setResults([]); return; }
    timer.current = window.setTimeout(() => { searchCourses(token, q).then(r => setResults(r.filter(c => !existing.has(c.code)))).catch(() => setResults([])); }, 250);
  }, [q, token, existing]);
  if (!picked) return <div className="pp-add">
    <label className="pg-search"><NavGlyph g="plus" size={16}/><span className="sr-only">Ajouter un cours</span>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ajouter un cours : tapez son nom (ex. Informatique)"/></label>
    {results.length > 0 && <ul className="pp-results">{results.slice(0, 8).map(c => <li key={c.code}><button type="button" onClick={() => { setPicked(c); setQ(''); }}>{c.label}</button></li>)}</ul>}
  </div>;
  return <div className="pp-add pp-add-form">
    <b>{picked.label}</b>
    <div className="pp-inputs">
      {labels.map((t, k) => <label key={t}><span>{t}</span><input type="number" inputMode="numeric" min={0} max={500} value={pts[k]}
        onChange={e => setPts(x => x.map((y, j) => j === k ? e.target.value.replace(/\D/g, '').slice(0, 3) : y))}/><small>{exam ? `examen ${2 * Number(pts[k] || 0)}` : 'pas d’examen'}</small></label>)}
      <label className="pp-check"><input type="checkbox" checked={exam} onChange={e => setExam(e.target.checked)}/>Avec examen</label>
    </div>
    <div className="pp-tools"><Button variant="primary" disabled={busy} onClick={() => void onAdd(picked.code, {term_points: pts.map(p => Number(p || 0)), has_exam: exam, mandatory: true})
      .then(ok => { if (ok) setPicked(null); })}>Ajouter ce cours</Button><Button variant="quiet" onClick={() => setPicked(null)}>Annuler</Button></div>
  </div>;
}
