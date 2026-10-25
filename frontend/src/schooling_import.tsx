// Imports, industrialised (owner request 2026-10-25: « le ui et le ux de l'import est tellement sale » ; « prévoir
// l'import dans le module personnel de façon industrielle »). Same server contract for every kind — official .xlsx
// template only → analyze (no write) → explicit execute, audited — as one guided stepper: 1. prepare (template, year when
// the kind needs one), 2. drop the file, 3. check the rows (filter by state, search), 4. import.
// Errors block the batch; warnings need an explicit tick. Pupils: no household is merged silently. Staff: an existing
// matricule blocks the batch.
import React, {useEffect, useMemo, useRef, useState} from 'react';
import {analyzeStaffImport, analyzeStudentImport, executeStaffImport, executeStudentImport, staffImportTemplate, studentImportTemplate, type SchoolClass, type StudentImportAnalysis} from './api';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {exportManaged} from './document_io';
import {toast} from 'sonner';
import './schooling_kit.css';

type Analysis = StudentImportAnalysis;
type Row = Analysis['preview'][number];
type Column = {label: string; width: string; render: (r: Row) => React.ReactNode};
const STATE: Record<Row['status'], {label: string; cls: string}> = {VALID: {label: 'Prête', cls: 'active'}, WARNING: {label: 'À vérifier', cls: 'suspended'}, ERROR: {label: 'Erreur', cls: 'abandon'}};
const kb = (n: number) => n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} Ko` : `${(n / 1024 / 1024).toFixed(1)} Mo`;
const person = (d: any) => [d.last_name, d.middle_name, d.first_name].filter(Boolean).join(' ') || '—';

type Config = {
  eyebrow: string; title: string; intro: string; noun: string; safety: string; module: string; templateName: string;
  years?: Array<{id: string; label: string}>;
  template: (year: string) => Promise<Blob>; analyze: (file: File, year: string) => Promise<Analysis>; execute: (batch: string, acceptWarnings: boolean) => Promise<any>;
  columns: Column[];
};

export function ImportStepper({cfg, schoolName, canExecute, onDone}: {cfg: Config; schoolName: string; canExecute: boolean; onDone: () => Promise<void>}) {
  const [year, setYear] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [done, setDone] = useState<{imported?: number} | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [drag, setDrag] = useState(false);
  const [filter, setFilter] = useState<'ALL' | Row['status']>('ALL');
  const [q, setQ] = useState('');
  const [accept, setAccept] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const needsYear = !!cfg.years;
  useEffect(() => { if (needsYear && !year && cfg.years?.[0]) setYear(cfg.years[0].id); }, [cfg.years, year, needsYear]);
  const step = done ? 4 : analysis ? 3 : file ? 2 : 1;
  const ready = !needsYear || !!year;

  function pick(f: File | null | undefined) {
    if (!f) return;
    if (!/\.xlsx$/i.test(f.name)) { setErr('Format non accepté : seul le modèle Excel officiel EduSync (.xlsx) est lu.'); return; }
    setErr(''); setFile(f); setAnalysis(null); setDone(null); setAccept(false); setFilter('ALL'); setQ('');
  }
  async function template() {
    try { await exportManaged(await cfg.template(year), {school: schoolName, module: cfg.module, category: 'Imports', filename: cfg.templateName}); toast.success('Modèle Excel téléchargé'); }
    catch (e) { setErr(friendlyError(e)); }
  }
  async function analyze() {
    if (!file || !ready) return; setBusy(true); setErr('');
    try { const a = await cfg.analyze(file, year); setAnalysis(a); window.dispatchEvent(new CustomEvent('edusync:import-changed')); setFilter(a.error_rows ? 'ERROR' : a.warning_rows ? 'WARNING' : 'ALL');
      toast[a.error_rows ? 'error' : 'success'](a.error_rows ? `${a.error_rows} ligne(s) en erreur : corrigez le fichier` : `${a.total_rows} ligne(s) analysée(s), prêtes à vérifier`); }
    catch (e) { setErr(friendlyError(e)); } finally { setBusy(false); }
  }
  async function execute() {
    if (!analysis) return; setBusy(true); setErr('');
    try { const r = await cfg.execute(analysis.batch_id, analysis.warning_rows > 0); const n = r?.imported_rows ?? r?.imported ?? analysis.valid_rows + analysis.warning_rows;
      setDone({imported: n}); window.dispatchEvent(new CustomEvent('edusync:import-changed')); toast.success(`Import terminé : ${n} ${cfg.noun} enregistré(s)`); await onDone(); }
    catch (e) { const m = friendlyError(e); setErr(m); toast.error(m); } finally { setBusy(false); }
  }
  function restart() { setFile(null); setAnalysis(null); setDone(null); setAccept(false); setErr(''); if (input.current) input.current.value = ''; }

  const rows = useMemo(() => (analysis?.preview ?? []).filter(r => (filter === 'ALL' || r.status === filter) && (!q.trim() || JSON.stringify(r.data).toLowerCase().includes(q.trim().toLowerCase()))), [analysis, filter, q]);
  const blocked = !!analysis && (analysis.error_rows > 0 || !analysis.can_execute);
  const needAccept = !!analysis && analysis.warning_rows > 0;
  const grid = {gridTemplateColumns: `64px ${cfg.columns.map(c => c.width).join(' ')} 110px minmax(200px,2fr)`};

  return <section className="ki-root">
    <header className="ki-head">
      <div><span className="ki-eyebrow">{cfg.eyebrow}</span><h3>{cfg.title}</h3><p>{cfg.intro}</p></div>
      <button type="button" className="kp-btn ghost" onClick={template} disabled={!ready}><NavGlyph g="download" size={18}/> Modèle Excel</button>
    </header>
    <ol className="ki-steps" aria-label="Étapes de l’import">
      {[needsYear ? 'Préparer' : 'Télécharger le modèle', 'Déposer le fichier', 'Vérifier les lignes', 'Importer'].map((l, i) => <li key={l} className={step > i + 1 ? 'done' : step === i + 1 ? 'on' : ''} aria-current={step === i + 1 ? 'step' : undefined}><span>{step > i + 1 ? '✓' : i + 1}</span>{l}</li>)}
    </ol>
    {err && <div className="kp-warn" role="alert">{err}</div>}

    {!done && <div className={`ki-prepare${needsYear ? '' : ' noyear'}`}>
      {needsYear && <label className="ki-field"><span>Année scolaire de destination</span><select value={year} onChange={e => { setYear(e.target.value); setAnalysis(null); }}>{cfg.years!.map(y => <option key={y.id} value={y.id}>{y.label}</option>)}</select></label>}
      <div className={`ki-drop${drag ? ' drag' : ''}${file ? ' has' : ''}`} role="button" tabIndex={0} aria-label="Choisir le fichier à importer"
        onClick={() => input.current?.click()} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click(); } }}
        onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}>
        <input ref={input} type="file" accept=".xlsx" hidden onChange={e => pick(e.target.files?.[0])}/>
        <span className="ki-dropIcon"><NavGlyph g={file ? 'check' : 'upload'} size={26}/></span>
        {file ? <div><b>{file.name}</b><small>{kb(file.size)} · cliquez pour changer de fichier</small></div>
          : <div><b>Glissez le fichier ici ou cliquez pour le choisir</b><small>Modèle Excel officiel EduSync (.xlsx) · une ligne par {cfg.noun.replace('(s)', '')}</small></div>}
      </div>
      <button type="button" className="kp-btn primary" disabled={!file || !ready || busy} onClick={analyze}>{busy && !analysis ? 'Analyse en cours…' : analysis ? 'Analyser à nouveau' : 'Analyser le fichier'}</button>
    </div>}

    {analysis && !done && <>
      <div className="ki-stats" role="group" aria-label="Filtrer les lignes">
        {([['ALL', analysis.total_rows, 'Lignes lues', ''], ['VALID', analysis.valid_rows, 'Prêtes', 'ok'], ['WARNING', analysis.warning_rows, 'À vérifier', 'warn'], ['ERROR', analysis.error_rows, 'En erreur', 'bad']] as const).map(([k, v, l, c]) =>
          <button type="button" key={k} className={`${c}${filter === k ? ' on' : ''}`} aria-pressed={filter === k} onClick={() => setFilter(k)}><b>{v}</b><small>{l}</small></button>)}
      </div>
      <div className="ki-tableBar"><label className="kp-search"><NavGlyph g="search" size={16}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Chercher un nom, un matricule…" aria-label="Chercher dans l’aperçu"/></label><small>{rows.length} ligne(s) affichée(s)</small></div>
      <div className="ki-table" role="table" aria-label="Aperçu de l’import">
        <div className="ki-row ki-th" role="row" style={grid}><span>Ligne</span>{cfg.columns.map(c => <span key={c.label}>{c.label}</span>)}<span>État</span><span>Contrôle</span></div>
        {rows.length ? rows.map(r => <div className={`ki-row ${r.status.toLowerCase()}`} role="row" key={r.row_number} style={grid}>
          <span className="ki-num">{r.row_number}</span>
          {cfg.columns.map(c => <span key={c.label}>{c.render(r)}</span>)}
          <span><em className={`kp-status ${STATE[r.status].cls}`}>{STATE[r.status].label}</em></span>
          <span className="ki-issues">{r.issues.length ? r.issues.map(x => <small key={x.code + x.field} className={x.level === 'ERROR' ? 'bad' : ''}>{x.message}</small>) : <small className="ok">Rien à signaler</small>}</span>
        </div>) : <div className="kp-emptyRow"><b>Aucune ligne dans ce filtre</b><span>Choisissez un autre état ci-dessus.</span></div>}
      </div>
      {analysis.preview_truncated && <p className="ki-note">Aperçu limité aux 100 premières lignes ; toutes les lignes ont bien été analysées.</p>}
      <div className={`ki-commit${blocked ? ' blocked' : ''}`}>
        <div>{blocked ? <><b>Import bloqué</b><span>{analysis.error_rows} ligne(s) en erreur. Corrigez le fichier puis analysez-le à nouveau.</span></>
          : <><b>Prêt à importer {analysis.valid_rows + analysis.warning_rows} {cfg.noun}</b><span>{cfg.safety}</span></>}
          {!blocked && needAccept && <label className="ki-accept"><input type="checkbox" checked={accept} onChange={e => setAccept(e.target.checked)}/> J’ai vérifié les {analysis.warning_rows} ligne(s) à vérifier et je les importe quand même.</label>}
        </div>
        {canExecute ? <button type="button" className="kp-btn primary" disabled={blocked || busy || (needAccept && !accept)} onClick={execute}>{busy ? 'Import en cours…' : 'Importer définitivement'}</button>
          : <small>Votre rôle peut analyser mais pas importer : demandez à un responsable de valider ce lot.</small>}
      </div>
    </>}

    {done && <div className="ki-done" role="status">
      <span className="ki-dropIcon ok"><NavGlyph g="check" size={28}/></span>
      <div><b>Import terminé</b><span>{done.imported ?? 0} {cfg.noun} enregistré(s){needsYear ? ` dans ${cfg.years!.find(y => y.id === year)?.label ?? 'l’année choisie'}` : ''}. Le lot apparaît dans l’historique ci-dessous.</span></div>
      <button type="button" className="kp-btn ghost" onClick={restart}>Importer un autre fichier</button>
    </div>}
  </section>;
}

export function StudentImportPro({token, classes, schoolName, canExecute, onDone}: {token: string; classes: SchoolClass[]; schoolName: string; canExecute: boolean; onDone: () => Promise<void>}) {
  const years = useMemo(() => [...new Map(classes.map(c => [c.academic_year_id, {id: c.academic_year_id, label: c.academic_year_label ?? c.academic_year_code ?? 'Année scolaire'}])).values()], [classes]);
  const cfg = useMemo<Config>(() => ({
    eyebrow: 'Reprise des données', title: 'Importer des élèves', noun: 'élève(s)', module: 'Scolarité', templateName: 'modele_import_eleves.xlsx', years,
    intro: 'Le fichier est d’abord analysé sans rien écrire. Vous vérifiez chaque ligne, puis vous confirmez l’import. Tout est tracé dans le journal.',
    safety: 'Aucun foyer n’est fusionné silencieusement : les doublons possibles restent des foyers séparés.',
    template: year => studentImportTemplate(token, year), analyze: (file, year) => analyzeStudentImport(token, file, year), execute: (b, w) => executeStudentImport(token, b, w),
    columns: [
      {label: 'Élève', width: 'minmax(200px,1.6fr)', render: r => <><b>{person(r.data)}</b>{r.data.matricule && <small>{r.data.matricule}</small>}</>},
      {label: 'Sexe', width: '60px', render: r => r.data.gender ?? '—'},
      {label: 'Classe', width: 'minmax(120px,1fr)', render: r => r.data.class_label_resolved ?? r.data.class_label ?? '—'},
    ],
  }), [token, years]);
  return <ImportStepper cfg={cfg} schoolName={schoolName} canExecute={canExecute} onDone={onDone}/>;
}

export function StaffImportPro({token, schoolName, canExecute, onDone}: {token: string; schoolName: string; canExecute: boolean; onDone: () => Promise<void>}) {
  const cfg = useMemo<Config>(() => ({
    eyebrow: 'Reprise des données', title: 'Importer le personnel', noun: 'agent(s)', module: 'Personnel', templateName: 'modele_import_personnel_edusync.xlsx',
    intro: 'Remplissez le modèle officiel (une ligne par agent), déposez-le : il est analysé sans rien écrire, vous vérifiez, puis vous confirmez. Tout est tracé.',
    safety: 'Un matricule déjà présent dans l’école bloque le lot : aucun agent n’est écrasé.',
    template: () => staffImportTemplate(token), analyze: file => analyzeStaffImport(token, file), execute: (b, w) => executeStaffImport(token, b, w),
    columns: [
      {label: 'Matricule', width: '110px', render: r => <b>{r.data.employee_no ?? '—'}</b>},
      {label: 'Agent', width: 'minmax(200px,1.6fr)', render: r => <><b>{person(r.data)}</b>{r.data.phone && <small>{r.data.phone}</small>}</>},
      {label: 'Catégorie', width: 'minmax(110px,1fr)', render: r => r.data.category ?? '—'},
    ],
  }), [token]);
  return <ImportStepper cfg={cfg} schoolName={schoolName} canExecute={canExecute} onDone={onDone}/>;
}
