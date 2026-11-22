import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {toast} from 'sonner';
import {downloadGradeSheetPdf, getGradeProgress, getGradeSheet, getGradesMissing, pasteGrades, putGradeCell, remindTeachers,
  type GradeProgress, type GradePupil, type GradeSheet, type MissingTeacher} from './api';
import {cachedSheet, rememberSheet} from './pedagogy_cache';
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
  const [copyOf, setCopyOf] = useState('');                 // offline: date of the copy kept on the phone
  const [q, setQ] = useState(''); const [onlyEmpty, setOnlyEmpty] = useState(false);
  const search = useRef<HTMLInputElement | null>(null);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const show = (s: GradeSheet) => { setSheet(s);
    setRows(Object.fromEntries(s.pupils.map(p => [p.student_id, {text: shown(p), saved: {status: p.status, value: p.value, version: p.version}, state: 'idle' as RowState}]))); };
  const load = useCallback((period?: string) => {
    setError('');
    getGradeSheet(token, classId, course, period).then(s => { setCopyOf(''); show(s); if (!period) rememberSheet(classId, course, s); })
      .catch(e => { const c = !period ? cachedSheet(classId, course) : null; if (c) { setCopyOf(c.savedAt); show(c.sheet); } else setError(friendlyError(e)); });
  }, [token, classId, course]);
  // what is typed also refreshes the copy kept on the phone (reopened offline, the sheet shows it)
  useEffect(() => { if (!sheet || copyOf) return;
    rememberSheet(classId, course, {...sheet, pupils: sheet.pupils.map(p => { const r = rows[p.student_id]; return r ? {...p, ...r.saved} : p; })}); }, [rows]);
  useEffect(() => { load(); }, [load]);
  const max = sheet?.period.max ?? 0;
  const present = useMemo(() => sheet ? sheet.pupils.filter(p => !p.departed) : [], [sheet]);
  const progress = useMemo(() => present.filter(p => { const r = rows[p.student_id]; return r && (r.saved.status || (r.state === 'queued' && r.text)); }).length, [rows, present]);

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
  function next(i: number) {
    if (q.trim()) { inputs.current[i]?.blur(); setQ(''); window.setTimeout(() => search.current?.focus(), 0); return; }   // pile of copies: back to the search
    const el = inputs.current[i + 1]; if (el) { el.focus(); el.select(); } else inputs.current[i]?.blur(); }
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
  const marks = present.map(p => rows[p.student_id]).filter(r => r && /^\d+$/.test(r.text)).map(r => Number(r!.text));
  const avg = marks.length ? marks.reduce((a, b) => a + b, 0) / marks.length : null;
  const failing = marks.filter(v => v * 2 < max).length;
  const empty = present.filter(p => !(rows[p.student_id]?.text)).length;
  const needle = q.trim().toLowerCase();
  const visible = (p: GradePupil) => (!needle || p.name.toLowerCase().includes(needle)) && (!onlyEmpty || !(rows[p.student_id]?.text) || p.departed);
  const file = `fiche-${sheet.class.label}-${sheet.course.label}-${sheet.period.code}.pdf`.replace(/\s+/g, '-');
  return <div className="pgr">
    <header className="pgr-head">
      <button type="button" className="pgr-back" onClick={onBack}><NavGlyph g="chevronLeft" size={18}/>Mes classes</button>
      <div className="pgr-title"><b>{sheet.course.label}</b><small>{sheet.class.label}</small></div>
      <div className="pgr-periods" role="tablist" aria-label="Période">{sheet.periods.map(c => <button key={c.code} type="button" role="tab" aria-selected={c.code === sheet.period.code}
        className={c.code === sheet.period.code ? 'on' : ''} onClick={() => load(c.code)}>{c.code}<small>{c.allowed ? 'ouverte' : c.state === 'CLOSED' ? 'clôturée' : c.state === 'UPCOMING' ? 'à venir' : '—'}</small></button>)}</div>
      <div className="pgr-progress" aria-label="Avancement"><span><b>{progress}</b>/{present.length} élèves · sur <b>{max}</b></span><i><span style={{width: `${present.length ? progress / present.length * 100 : 0}%`}}/></i></div>
    </header>
    {copyOf && <div className="pc-note"><NavGlyph g="wifiOff" size={16}/><span>Hors connexion : fiche enregistrée sur ce téléphone le {new Date(copyOf).toLocaleString('fr-FR', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'})}. Vos cotes partiront au retour du réseau.</span></div>}
    {why && <div className="pc-note"><NavGlyph g="info" size={16}/><span>{why}</span></div>}
    {sheet.can_enter && <div className="pgr-find">
      <label className="pg-search"><NavGlyph g="search" size={16}/><span className="sr-only">Trouver un élève</span>
        <input ref={search} value={q} onChange={e => setQ(e.target.value)} placeholder="Trouver un élève (copies dans le désordre)" inputMode="search"
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); const i = sheet.pupils.findIndex(p => !p.departed && visible(p)); inputs.current[i]?.focus(); inputs.current[i]?.select(); } }}/></label>
      {empty > 0 && <button type="button" className="pcd-follow" aria-pressed={onlyEmpty} onClick={() => setOnlyEmpty(x => !x)}>Sans cote ({empty})</button>}
    </div>}
    {sheet.can_enter && tip && <div className="pgr-tip"><NavGlyph g="sparkles" size={16}/><span>Tapez la cote puis <b>Entrée</b> (ou « Suivant ») : elle est enregistrée et on passe à l’élève suivant.
      <b>a</b> (ou le bouton « Abs. ») = absent à cette évaluation, <b>d</b> = dispensé (excusé par la direction).</span>
      <button type="button" aria-label="Compris" onClick={() => { setTip(false); try { localStorage.setItem(TIP_KEY, '1'); } catch { /* private mode */ } }}>Compris</button></div>}
    <ol className="pgr-list">{sheet.pupils.map((p, i) => {
      const r = rows[p.student_id] ?? {text: '', saved: {status: null, value: null, version: null}, state: 'idle' as RowState};
      const n = /^\d+$/.test(r.text) ? Number(r.text) : null;
      const failing = n !== null && n * 2 < max;
      if (!visible(p)) return null;
      if (p.departed) return <li key={p.student_id} className="pgr-row pgr-gone">
        <span className="pgr-n" aria-hidden="true">—</span>
        <span className="pgr-name">{p.name}<small>{p.pupil_status === 'TRANSFERRED' ? 'Transféré' : 'Abandon'}{p.left_on ? ` le ${new Date(p.left_on + 'T12:00:00').toLocaleDateString('fr-FR', {day: 'numeric', month: 'short'})}` : ''} · plus noté</small></span>
        <span className="pgr-value">{shown(p) === 'a' ? 'Absent' : shown(p) === 'd' ? 'Dispensé' : shown(p) || '—'}</span>
      </li>;
      return <li key={p.student_id} className={`pgr-row pgr-${r.state}`}>
        <span className="pgr-n" aria-hidden="true">{i + 1}</span>
        <span className="pgr-name">{p.name}{p.pupil_status === 'SUSPENDED' && <em className="pgr-susp">Suspendu</em>}{r.message && <small role={r.state === 'error' ? 'alert' : undefined}>{r.message}</small>}</span>
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
    {marks.length > 0 && <div className="pgr-sum" aria-label="Résumé de la classe">
      <div><b>{avg!.toFixed(1).replace('.', ',')}</b><small>moyenne sur {max}</small></div>
      <div className={failing ? 'bad' : ''}><b>{failing}</b><small>sous la moitié</small></div>
      <div><b>{Math.max(...marks)} · {Math.min(...marks)}</b><small>meilleure · plus faible</small></div>
      <div className={empty ? 'warn' : ''}><b>{empty}</b><small>sans cote</small></div>
    </div>}
    <div className="pgr-foot">
      {sheet.can_enter && <Button icon="doc" onClick={() => setPaste(true)}>Coller une liste de cotes</Button>}
      <Button icon="print" onClick={() => void downloadGradeSheetPdf(token, classId, course, sheet.period.code, false, file).catch(e => toast.error(friendlyError(e)))}>Fiche vierge à imprimer</Button>
      {marks.length > 0 && <Button icon="print" onClick={() => void downloadGradeSheetPdf(token, classId, course, sheet.period.code, true, file).catch(e => toast.error(friendlyError(e)))}>Fiche avec les cotes</Button>}
    </div>
    {paste && <PasteDialog token={token} sheet={sheet} classId={classId} course={course} onClose={() => setPaste(false)} onDone={() => { setPaste(false); load(sheet.period.code); }}/>}
  </div>;
}

function PasteDialog({token, sheet, classId, course, onClose, onDone}: {token: string; sheet: GradeSheet; classId: string; course: string; onClose: () => void; onDone: () => void}) {
  const [text, setText] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const lines = text.replace(/\r/g, '').split('\n'); while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  const present = sheet.pupils.filter(p => !p.departed).length;
  async function go() {
    setBusy(true); setError('');
    try { const r = await pasteGrades(token, {class_id: classId, course_code: course, period: sheet.period.code, text});
      toast.success(`${r.pasted.filled} cote${r.pasted.filled > 1 ? 's' : ''} ajoutée${r.pasted.filled > 1 ? 's' : ''}${r.pasted.kept ? ` · ${r.pasted.kept} déjà saisie(s), gardée(s)` : ''}`); onDone(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <Modal title="Coller une liste de cotes" subtitle={`${sheet.course.label} · ${sheet.class.label} · ${sheet.period.label} (sur ${sheet.period.max})`} onClose={onClose}>
    <div className="es-form">
      <p className="es-hint">Copiez la colonne de cotes depuis Excel, WhatsApp ou vos notes : <b>une cote par ligne, dans l’ordre de la liste de la classe</b> ({sheet.pupils.filter(p => !p.departed).length} élèves présents, sans ceux qui sont partis). « a » = absent. Seules les cases encore vides sont remplies : aucune cote déjà saisie n’est remplacée.</p>
      <textarea rows={10} value={text} onChange={e => setText(e.target.value)} placeholder={'14\n9\na\n17'} aria-label="Cotes à coller"/>
      <p className={`pgr-paste-count ${lines.length > present ? 'bad' : ''}`}>{lines.length} ligne{lines.length > 1 ? 's' : ''} pour {present} élèves</p>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <button type="button" className="es-btn es-btn-primary" disabled={busy || !lines.length || lines.length > present} onClick={() => void go()}>{busy ? 'Remplissage…' : 'Remplir les cases vides'}</button></div>
    </div>
  </Modal>;
}

// ------------------------------------------------------------------------------------------------ directors' follow-up
export function GradeProgressTab({token}: {token: string}) {
  const [data, setData] = useState<GradeProgress | null>(null); const [error, setError] = useState('');
  const [late, setLate] = useState<MissingTeacher[]>([]); const [busy, setBusy] = useState('');
  const load = useCallback(() => { getGradeProgress(token).then(setData).catch(e => setError(friendlyError(e)));
    getGradesMissing(token).then(r => setLate(r.teachers)).catch(() => undefined); }, [token]);
  async function nudge(ids?: string[]) {
    setBusy(ids?.[0] ?? 'all');
    try { const r = await remindTeachers(token, ids); toast.success(r.sent ? `${r.sent} enseignant${r.sent > 1 ? 's' : ''} relancé${r.sent > 1 ? 's' : ''}` : 'Déjà relancé aujourd’hui'); }
    catch (e) { toast.error(friendlyError(e)); } finally { setBusy(''); }
  }
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
    <p className="pc-intro">Mis à jour en direct : chaque cote saisie par un enseignant apparaît ici sans recharger. Un rappel automatique part aussi 3 jours avant la fin de chaque période.</p>
    {late.length > 0 && <section className="pg-section pgl"><h3>Qui n’a pas fini ({late.length})</h3>
      <div className="pgl-all"><Button variant="primary" icon="bell" disabled={!!busy} onClick={() => void nudge()}>{busy === 'all' ? 'Envoi…' : 'Relancer tous les enseignants'}</Button></div>
      <ul className="pgl-list">{late.map(t => <li key={t.membership_id}>
        <div><b>{t.full_name}</b><small>{t.items.length} cours · {t.items.reduce((n, i) => n + i.missing, 0)} cotes manquantes</small>
          <small className="pgl-detail">{t.items.slice(0, 4).map(i => `${i.course_label} (${i.class_label})`).join(' · ')}{t.items.length > 4 ? ' …' : ''}</small></div>
        <Button size="sm" disabled={!!busy} onClick={() => void nudge([t.membership_id])}>{busy === t.membership_id ? '…' : 'Relancer'}</Button>
      </li>)}</ul></section>}
    {sections.map(sec => <section key={sec} className="pg-section"><h3>{sec}</h3>
      <ul className="pgp-list">{data.items.filter(i => i.section_label === sec).map(i => <li key={i.class_id}>
        <div><b>{i.label}</b><small>{i.period ? `Période ${i.period}` : 'Aucune période ouverte'} · {i.pupils} élèves</small></div>
        <div className="pgp-bar" aria-label={`${i.complete} cours complets sur ${i.courses}`}><i><span style={{width: `${i.courses ? i.complete / i.courses * 100 : 0}%`}}/></i>
          <small><b>{i.complete}</b>/{i.courses} cours complets{i.started > i.complete ? ` · ${i.started - i.complete} en cours` : ''}</small></div>
      </li>)}</ul></section>)}
  </>;
}
