// Student import, industrialised (owner request 2026-10-25: « le ui et le ux de l'import est tellement sale »).
// Same server contract as before — official .xlsx template only → analyze (no write) → explicit execute, audited — as a guided
// stepper: 1. prepare (year + template), 2. drop the file, 3. check the rows (filter by state, search), 4. import.
// Errors block the batch; warnings need an explicit tick; no household is merged silently.
import React, {useEffect, useMemo, useRef, useState} from 'react';
import {analyzeStudentImport, executeStudentImport, studentImportTemplate, type SchoolClass, type StudentImportAnalysis} from './api';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {exportManaged} from './document_io';
import './schooling_kit.css';

type Row = StudentImportAnalysis['preview'][number];
const STATE: Record<Row['status'], {label: string; cls: string}> = {VALID: {label: 'Prête', cls: 'active'}, WARNING: {label: 'À vérifier', cls: 'suspended'}, ERROR: {label: 'Erreur', cls: 'abandon'}};
const kb = (n: number) => n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} Ko` : `${(n / 1024 / 1024).toFixed(1)} Mo`;

export function StudentImportPro({token, classes, schoolName, canExecute, onDone}: {token: string; classes: SchoolClass[]; schoolName: string; canExecute: boolean; onDone: () => Promise<void>}) {
  const years = useMemo(() => [...new Map(classes.map(c => [c.academic_year_id, {id: c.academic_year_id, label: c.academic_year_label ?? c.academic_year_code ?? 'Année scolaire'}])).values()], [classes]);
  const [year, setYear] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<StudentImportAnalysis | null>(null);
  const [done, setDone] = useState<{imported?: number} | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [drag, setDrag] = useState(false);
  const [filter, setFilter] = useState<'ALL' | Row['status']>('ALL');
  const [q, setQ] = useState('');
  const [accept, setAccept] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (!year && years[0]) setYear(years[0].id); }, [years, year]);
  const step = done ? 4 : analysis ? 3 : file ? 2 : 1;

  function pick(f: File | null | undefined) {
    if (!f) return;
    if (!/\.xlsx$/i.test(f.name)) { setErr('Format non accepté : seul le modèle Excel officiel EduSync (.xlsx) est lu.'); return; }
    setErr(''); setFile(f); setAnalysis(null); setDone(null); setAccept(false); setFilter('ALL'); setQ('');
  }
  async function template() {
    try { await exportManaged(await studentImportTemplate(token, year), {school: schoolName, module: 'Scolarité', category: 'Imports', filename: 'modele_import_eleves.xlsx'}); }
    catch (e) { setErr(friendlyError(e)); }
  }
  async function analyze() {
    if (!file || !year) return; setBusy(true); setErr('');
    try { const a = await analyzeStudentImport(token, file, year); setAnalysis(a); setFilter(a.error_rows ? 'ERROR' : a.warning_rows ? 'WARNING' : 'ALL'); }
    catch (e) { setErr(friendlyError(e)); } finally { setBusy(false); }
  }
  async function execute() {
    if (!analysis) return; setBusy(true); setErr('');
    try { const r = await executeStudentImport(token, analysis.batch_id, analysis.warning_rows > 0); setDone({imported: r?.imported_rows ?? r?.imported ?? analysis.valid_rows + analysis.warning_rows}); await onDone(); }
    catch (e) { setErr(friendlyError(e)); } finally { setBusy(false); }
  }
  function restart() { setFile(null); setAnalysis(null); setDone(null); setAccept(false); setErr(''); if (input.current) input.current.value = ''; }

  const rows = useMemo(() => (analysis?.preview ?? []).filter(r => (filter === 'ALL' || r.status === filter) && (!q.trim() || JSON.stringify(r.data).toLowerCase().includes(q.trim().toLowerCase()))), [analysis, filter, q]);
  const blocked = !!analysis && (analysis.error_rows > 0 || !analysis.can_execute);
  const needAccept = !!analysis && analysis.warning_rows > 0;

  return <section className="ki-root">
    <header className="ki-head">
      <div><span className="ki-eyebrow">Reprise des données</span><h3>Importer des élèves</h3><p>Le fichier est d’abord analysé sans rien écrire. Vous vérifiez chaque ligne, puis vous confirmez l’import. Tout est tracé dans le journal.</p></div>
      <button type="button" className="kp-btn ghost" onClick={template} disabled={!year}><NavGlyph g="download" size={18}/> Modèle Excel</button>
    </header>
    <ol className="ki-steps" aria-label="Étapes de l’import">
      {['Préparer', 'Déposer le fichier', 'Vérifier les lignes', 'Importer'].map((l, i) => <li key={l} className={step > i + 1 ? 'done' : step === i + 1 ? 'on' : ''} aria-current={step === i + 1 ? 'step' : undefined}><span>{step > i + 1 ? '✓' : i + 1}</span>{l}</li>)}
    </ol>
    {err && <div className="kp-warn" role="alert">{err}</div>}

    {!done && <div className="ki-prepare">
      <label className="ki-field"><span>Année scolaire de destination</span><select value={year} onChange={e => { setYear(e.target.value); setAnalysis(null); }}>{years.map(y => <option key={y.id} value={y.id}>{y.label}</option>)}</select></label>
      <div className={`ki-drop${drag ? ' drag' : ''}${file ? ' has' : ''}`} role="button" tabIndex={0} aria-label="Choisir le fichier à importer"
        onClick={() => input.current?.click()} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click(); } }}
        onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}>
        <input ref={input} type="file" accept=".xlsx" hidden onChange={e => pick(e.target.files?.[0])}/>
        <span className="ki-dropIcon"><NavGlyph g={file ? 'check' : 'upload'} size={26}/></span>
        {file ? <div><b>{file.name}</b><small>{kb(file.size)} · cliquez pour changer de fichier</small></div>
          : <div><b>Glissez le fichier ici ou cliquez pour le choisir</b><small>Modèle Excel officiel EduSync (.xlsx) · une ligne par élève</small></div>}
      </div>
      <button type="button" className="kp-btn primary" disabled={!file || !year || busy} onClick={analyze}>{busy && !analysis ? 'Analyse en cours…' : analysis ? 'Analyser à nouveau' : 'Analyser le fichier'}</button>
    </div>}

    {analysis && !done && <>
      <div className="ki-stats" role="group" aria-label="Filtrer les lignes">
        {([['ALL', analysis.total_rows, 'Lignes lues', ''], ['VALID', analysis.valid_rows, 'Prêtes', 'ok'], ['WARNING', analysis.warning_rows, 'À vérifier', 'warn'], ['ERROR', analysis.error_rows, 'En erreur', 'bad']] as const).map(([k, v, l, c]) =>
          <button type="button" key={k} className={`${c}${filter === k ? ' on' : ''}`} aria-pressed={filter === k} onClick={() => setFilter(k)}><b>{v}</b><small>{l}</small></button>)}
      </div>
      <div className="ki-tableBar"><label className="kp-search"><NavGlyph g="search" size={16}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Chercher un nom, une classe…" aria-label="Chercher dans l’aperçu"/></label><small>{rows.length} ligne(s) affichée(s)</small></div>
      <div className="ki-table" role="table" aria-label="Aperçu de l’import">
        <div className="ki-row ki-th" role="row"><span>Ligne</span><span>Élève</span><span>Sexe</span><span>Classe</span><span>État</span><span>Contrôle</span></div>
        {rows.length ? rows.map(r => <div className={`ki-row ${r.status.toLowerCase()}`} role="row" key={r.row_number}>
          <span className="ki-num">{r.row_number}</span>
          <span><b>{[r.data.last_name, r.data.middle_name, r.data.first_name].filter(Boolean).join(' ') || '—'}</b>{r.data.matricule && <small>{r.data.matricule}</small>}</span>
          <span>{r.data.gender ?? '—'}</span>
          <span>{r.data.class_label_resolved ?? r.data.class_label ?? '—'}</span>
          <span><em className={`kp-status ${STATE[r.status].cls}`}>{STATE[r.status].label}</em></span>
          <span className="ki-issues">{r.issues.length ? r.issues.map(x => <small key={x.code + x.field} className={x.level === 'ERROR' ? 'bad' : ''}>{x.message}</small>) : <small className="ok">Rien à signaler</small>}</span>
        </div>) : <div className="kp-emptyRow"><b>Aucune ligne dans ce filtre</b><span>Choisissez un autre état ci-dessus.</span></div>}
      </div>
      {analysis.preview_truncated && <p className="ki-note">Aperçu limité aux 100 premières lignes ; toutes les lignes ont bien été analysées.</p>}
      <div className={`ki-commit${blocked ? ' blocked' : ''}`}>
        <div>{blocked ? <><b>Import bloqué</b><span>{analysis.error_rows} ligne(s) en erreur. Corrigez le fichier puis analysez-le à nouveau.</span></>
          : <><b>Prêt à importer {analysis.valid_rows + analysis.warning_rows} élève(s)</b><span>Aucun foyer n’est fusionné silencieusement : les doublons possibles restent des foyers séparés.</span></>}
          {!blocked && needAccept && <label className="ki-accept"><input type="checkbox" checked={accept} onChange={e => setAccept(e.target.checked)}/> J’ai vérifié les {analysis.warning_rows} ligne(s) à vérifier et je les importe quand même.</label>}
        </div>
        {canExecute ? <button type="button" className="kp-btn primary" disabled={blocked || busy || (needAccept && !accept)} onClick={execute}>{busy ? 'Import en cours…' : 'Importer définitivement'}</button>
          : <small>Votre rôle peut analyser mais pas importer : demandez à un responsable de valider ce lot.</small>}
      </div>
    </>}

    {done && <div className="ki-done" role="status">
      <span className="ki-dropIcon ok"><NavGlyph g="check" size={28}/></span>
      <div><b>Import terminé</b><span>{done.imported ?? 0} élève(s) enregistré(s) dans {years.find(y => y.id === year)?.label ?? 'l’année choisie'}. Le lot apparaît dans l’historique ci-dessous.</span></div>
      <button type="button" className="kp-btn ghost" onClick={restart}>Importer un autre fichier</button>
    </div>}
  </section>;
}
