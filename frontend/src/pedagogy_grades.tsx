import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {toast} from 'sonner';
import {getGradeProgress, getGradeSheet, pasteGrades, putGradeCell, type GradeProgress, type GradePupil, type GradeSheet} from './api';
import {Modal} from './platform/account';
import {friendlyError} from './platform/errors';
import {useLive} from './platform/live';
import {NavGlyph} from './platform/nav_icons';
import {Button, Skeleton} from './platform/ui';

/* V2 lot 3b — grade entry (owner 2026-11-22: « les enseignants ne doivent pas se plaindre… même à la main c'est bien »).
   Faster than the paper register: type the mark, Enter → saved and next pupil (no « Enregistrer » button, no column
   jump); « a » = absent, « d » = dispensé; a pasted column fills the empty cells; each row shows its state (saved,
   waiting for the network, conflict). Parent project rules are enforced by the server (maximum, no exam column for a
   course without exam, calendar window, the teacher of the course only). */

type RowState = 'idle' | 'saving' | 'saved' | 'queued' | 'error' | 'conflict';
type Row = {text: string; saved: Pick<GradePupil, 'status' | 'value' | 'version'>; state: RowState; message?: string; theirs?: {status: GradePupil['status']; value: number | null; version: number}};
const shown = (s: Pick<GradePupil, 'status' | 'value'>) => s.status === 'NOTE' ? String(s.value) : s.status === 'ABSENT' ? 'a' : s.status === 'DISPENSE' ? 'd' : '';
const STATE_WHY: Record<string, string> = {CLOSED: 'La saisie de cette période est clôturée par la direction.', UPCOMING: 'Cette période n’a pas encore commencé.',
  DRAFT: 'Le calendrier n’est pas encore validé par la direction.', ONGOING: '', OPEN: ''};
const TIP_KEY = 'edusync.grades.tip.seen';

export function GradeEntry({token, classId, course, onBack}: {token: string; classId: string; course: string; onBack: () => void}) {
  const [sheet, setSheet] = useState<GradeSheet | null>(null);
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [error, setError] = useState('');
  const [paste, setPaste] = useState(false);
  const [tip, setTip] = useState(() => { try { return !localStorage.getItem(TIP_KEY); } catch { return true; } });
  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const load = useCallback((period?: string) => {
    setError('');
    getGradeSheet(token, classId, course, period).then(s => {
      setSheet(s);
      setRows(Object.fromEntries(s.pupils.map(p => [p.student_id, {text: shown(p), saved: {status: p.status, value: p.value, version: p.version}, state: 'idle' as RowState}])));
    }).catch(e => setError(friendlyError(e)));
  }, [token, classId, course]);
  useEffect(() => { load(); }, [load]);
  const max = sheet?.period.max ?? 0;
  const progress = useMemo(() => sheet ? sheet.pupils.filter(p => { const r = rows[p.student_id]; return r && (r.saved.status || (r.state === 'queued' && r.text)); }).length : 0, [rows, sheet]);

  async function commit(p: GradePupil, text: string) {
    const r = rows[p.student_id]; if (!sheet || !r) return;
    const clean = text.trim().toLowerCase();
    if (clean === shown(r.saved) && r.state !== 'error') return;
    setRows(x => ({...x, [p.student_id]: {...x[p.student_id], text: clean, state: 'saving', message: undefined}}));
    try {
      const out = await putGradeCell(token, {class_id: classId, course_code: course, period: sheet.period.code, student_id: p.student_id, input: clean, expected_version: r.saved.version});
      if ('conflict' in out) {
        setRows(x => ({...x, [p.student_id]: {...x[p.student_id], state: 'conflict', theirs: out.current, message: `Modifiée ailleurs : ${shown(out.current) || 'vide'}`}}));
      } else if (out.offline_queued) {
        setRows(x => ({...x, [p.student_id]: {...x[p.student_id], state: 'queued', message: 'Hors connexion : sera envoyée au retour du réseau'}}));
      } else {
        setRows(x => ({...x, [p.student_id]: {text: shown(out), saved: {status: out.status, value: out.value, version: out.version}, state: 'saved'}}));
      }
    } catch (e) {
      setRows(x => ({...x, [p.student_id]: {...x[p.student_id], state: 'error', message: friendlyError(e)}}));
    }
  }
  function next(i: number) { const el = inputs.current[i + 1]; if (el) { el.focus(); el.select(); } else inputs.current[i]?.blur(); }
  function keep(p: GradePupil, mine: boolean) {
    const r = rows[p.student_id]; if (!r?.theirs) return;
    const theirs = r.theirs;
    if (mine) { setRows(x => ({...x, [p.student_id]: {...r, saved: {...r.saved, version: theirs.version}, state: 'idle', theirs: undefined, message: undefined}})); void commitWith(p, r.text, theirs.version); }
    else setRows(x => ({...x, [p.student_id]: {text: shown(theirs), saved: theirs, state: 'saved', theirs: undefined}}));
  }
  async function commitWith(p: GradePupil, text: string, version: number) {
    setRows(x => ({...x, [p.student_id]: {...x[p.student_id], saved: {...x[p.student_id].saved, version}}}));
    const out = await putGradeCell(token, {class_id: classId, course_code: course, period: sheet!.period.code, student_id: p.student_id, input: text, expected_version: version}).catch(e => { toast.error(friendlyError(e)); return null; });
    if (out && !('conflict' in out) && !out.offline_queued) setRows(x => ({...x, [p.student_id]: {text: shown(out), saved: {status: out.status, value: out.value, version: out.version}, state: 'saved'}}));
  }

  if (error) return <div className="pgr"><button type="button" className="pgr-back" onClick={onBack}><NavGlyph g="chevronLeft" size={18}/>Mes classes</button>
    <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Fiche indisponible</b><small>{error}</small></div></div></div>;
  if (!sheet) return <Skeleton lines={8}/>;
  const why = !sheet.can_enter ? (STATE_WHY[sheet.period.state] || 'Consultation seule : seul l’enseignant de ce cours saisit ses cotes.') : '';
  return <div className="pgr">
    <header className="pgr-head">
      <button type="button" className="pgr-back" onClick={onBack}><NavGlyph g="chevronLeft" size={18}/>Mes classes</button>
      <div className="pgr-title"><b>{sheet.course.label}</b><small>{sheet.class.label}</small></div>
      <div className="pgr-periods" role="tablist" aria-label="Période">{sheet.periods.map(c => <button key={c.code} type="button" role="tab" aria-selected={c.code === sheet.period.code}
        className={c.code === sheet.period.code ? 'on' : ''} onClick={() => load(c.code)}>{c.code}<small>{c.allowed ? 'ouverte' : c.state === 'CLOSED' ? 'clôturée' : c.state === 'UPCOMING' ? 'à venir' : '—'}</small></button>)}</div>
      <div className="pgr-progress" aria-label="Avancement"><span><b>{progress}</b>/{sheet.pupils.length} élèves · sur <b>{max}</b></span><i><span style={{width: `${sheet.pupils.length ? progress / sheet.pupils.length * 100 : 0}%`}}/></i></div>
    </header>
    {why && <div className="pc-note"><NavGlyph g="info" size={16}/><span>{why}</span></div>}
    {sheet.can_enter && tip && <div className="pgr-tip"><NavGlyph g="sparkles" size={16}/><span>Tapez la cote puis <b>Entrée</b> (ou « Suivant ») : elle est enregistrée et on passe à l’élève suivant. <b>a</b> = absent, <b>d</b> = dispensé.</span>
      <button type="button" aria-label="Compris" onClick={() => { setTip(false); try { localStorage.setItem(TIP_KEY, '1'); } catch { /* private mode */ } }}>Compris</button></div>}
    <ol className="pgr-list">{sheet.pupils.map((p, i) => {
      const r = rows[p.student_id] ?? {text: '', saved: {status: null, value: null, version: null}, state: 'idle' as RowState};
      const n = /^\d+$/.test(r.text) ? Number(r.text) : null;
      const failing = n !== null && n * 2 < max;
      return <li key={p.student_id} className={`pgr-row pgr-${r.state}`}>
        <span className="pgr-n" aria-hidden="true">{i + 1}</span>
        <span className="pgr-name">{p.name}{r.message && <small role={r.state === 'error' ? 'alert' : undefined}>{r.message}</small>}</span>
        {sheet.can_enter ? <>
          <input ref={el => { inputs.current[i] = el; }} className={failing ? 'pgr-fail' : ''} value={r.text} inputMode="numeric" enterKeyHint={i === sheet.pupils.length - 1 ? 'done' : 'next'}
            autoComplete="off" maxLength={3} aria-label={`Cote de ${p.name} sur ${max}`}
            onChange={e => setRows(x => ({...x, [p.student_id]: {...r, text: e.target.value.replace(/[^0-9aAdD]/g, '').slice(0, 3), state: r.state === 'error' ? 'idle' : r.state}}))}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); next(i); } }}   /* moving on blurs the cell: the blur saves it (once) */
            onBlur={e => void commit(p, e.target.value)}/>
          <button type="button" className={`pgr-abs ${r.text === 'a' ? 'on' : ''}`} aria-pressed={r.text === 'a'} aria-label={`${p.name} absent`}
            onClick={() => { const t = r.text === 'a' ? '' : 'a'; setRows(x => ({...x, [p.student_id]: {...r, text: t}})); void commit(p, t); }}>Abs.</button>
          <span className="pgr-state" aria-hidden="true">{r.state === 'saving' ? '…' : r.state === 'saved' ? <NavGlyph g="check" size={16}/> : r.state === 'queued' ? <NavGlyph g="cloudUp" size={16}/> : r.state === 'error' || r.state === 'conflict' ? <NavGlyph g="alert" size={16}/> : null}</span>
        </> : <span className={`pgr-value ${p.failing ? 'pgr-fail' : ''}`}>{shown(p) === 'a' ? 'Absent' : shown(p) === 'd' ? 'Dispensé' : shown(p) || '—'}</span>}
        {r.state === 'conflict' && <div className="pgr-conflict"><Button size="sm" variant="primary" onClick={() => keep(p, true)}>Garder la mienne ({r.text || 'vide'})</Button>
          <Button size="sm" onClick={() => keep(p, false)}>Prendre {shown(r.theirs!) || 'vide'}</Button></div>}
      </li>;
    })}</ol>
    {sheet.can_enter && <div className="pgr-foot"><Button icon="doc" onClick={() => setPaste(true)}>Coller une liste de cotes</Button></div>}
    {paste && <PasteDialog token={token} sheet={sheet} classId={classId} course={course} onClose={() => setPaste(false)} onDone={() => { setPaste(false); load(sheet.period.code); }}/>}
  </div>;
}

function PasteDialog({token, sheet, classId, course, onClose, onDone}: {token: string; sheet: GradeSheet; classId: string; course: string; onClose: () => void; onDone: () => void}) {
  const [text, setText] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const lines = text.replace(/\r/g, '').split('\n'); while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  async function go() {
    setBusy(true); setError('');
    try { const r = await pasteGrades(token, {class_id: classId, course_code: course, period: sheet.period.code, text});
      toast.success(`${r.pasted.filled} cote${r.pasted.filled > 1 ? 's' : ''} ajoutée${r.pasted.filled > 1 ? 's' : ''}${r.pasted.kept ? ` · ${r.pasted.kept} déjà saisie(s), gardée(s)` : ''}`); onDone(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <Modal title="Coller une liste de cotes" subtitle={`${sheet.course.label} · ${sheet.class.label} · ${sheet.period.label} (sur ${sheet.period.max})`} onClose={onClose}>
    <div className="es-form">
      <p className="es-hint">Copiez la colonne de cotes depuis Excel, WhatsApp ou vos notes : <b>une cote par ligne, dans l’ordre de la liste de la classe</b> ({sheet.pupils.length} élèves). « a » = absent. Seules les cases encore vides sont remplies : aucune cote déjà saisie n’est remplacée.</p>
      <textarea rows={10} value={text} onChange={e => setText(e.target.value)} placeholder={'14\n9\na\n17'} aria-label="Cotes à coller"/>
      <p className={`pgr-paste-count ${lines.length > sheet.pupils.length ? 'bad' : ''}`}>{lines.length} ligne{lines.length > 1 ? 's' : ''} pour {sheet.pupils.length} élèves</p>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <button type="button" className="es-btn es-btn-primary" disabled={busy || !lines.length || lines.length > sheet.pupils.length} onClick={() => void go()}>{busy ? 'Remplissage…' : 'Remplir les cases vides'}</button></div>
    </div>
  </Modal>;
}

// ------------------------------------------------------------------------------------------------ directors' follow-up
export function GradeProgressTab({token}: {token: string}) {
  const [data, setData] = useState<GradeProgress | null>(null); const [error, setError] = useState('');
  const load = useCallback(() => { getGradeProgress(token).then(setData).catch(e => setError(friendlyError(e))); }, [token]);
  useEffect(load, [load]);
  useLive(['pedagogy'], load);                 // what the teachers enter appears here without reloading
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Suivi indisponible</b><small>{error}</small></div></div>;
  if (!data) return <Skeleton lines={6}/>;
  const sections = [...new Set(data.items.map(i => i.section_label))];
  const total = data.items.reduce((n, i) => n + i.courses, 0); const complete = data.items.reduce((n, i) => n + i.complete, 0);
  return <>
    <div className="pg-summary" aria-label="Résumé">
      <div className={complete === total && total ? 'pg-ok' : ''}><b>{complete}/{total}</b><small>cours complets pour la période en cours</small></div>
      <div><b>{data.items.filter(i => i.complete === i.courses && i.courses).length}/{data.items.length}</b><small>classes complètes</small></div>
    </div>
    <p className="pc-intro">Mis à jour en direct : chaque cote saisie par un enseignant apparaît ici sans recharger.</p>
    {sections.map(sec => <section key={sec} className="pg-section"><h3>{sec}</h3>
      <ul className="pgp-list">{data.items.filter(i => i.section_label === sec).map(i => <li key={i.class_id}>
        <div><b>{i.label}</b><small>{i.period ? `Période ${i.period}` : 'Aucune période ouverte'} · {i.pupils} élèves</small></div>
        <div className="pgp-bar" aria-label={`${i.complete} cours complets sur ${i.courses}`}><i><span style={{width: `${i.courses ? i.complete / i.courses * 100 : 0}%`}}/></i>
          <small><b>{i.complete}</b>/{i.courses} cours complets{i.started > i.complete ? ` · ${i.started - i.complete} en cours` : ''}</small></div>
      </li>)}</ul></section>)}
  </>;
}
