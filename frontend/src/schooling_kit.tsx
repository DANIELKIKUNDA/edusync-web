// Élèves & inscriptions — industrialised pieces (owner request 2026-10-25), Desktop golden master parity
// (app/ui/schooling_page.py: student filters year / section / class / status / sex, « Réinscription rapide »):
//  * ClassPicker: section first, then the classes of that section grouped by level (never one endless list);
//  * StudentDirectoryPro: filters (section, class, Humanités option, sex, status, year or whole history), modern table,
//    exports with the same filters;
//  * ReenrollWizard: a re-enrollment is NOT a new enrollment — find a known pupil, see the last class, the arrears and
//    whether the pupil is already enrolled this year; the next class is proposed (promotion), the family is reused.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {
  SchoolClass, SchoolOption, SchoolingStudent, StudentFilters, enrollFamily, listOptions, listStudents, listYearSelector, studentDirectoryPdf, studentDirectoryXlsx,
  type AcademicYear,
} from './api';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {exportManaged, previewPdf} from './document_io';
import './schooling_kit.css';

export const STATUS_FR: Record<string, string> = {ACTIVE: 'Actif', ABANDON: 'Abandon', TRANSFERRED: 'Transféré', SUSPENDED: 'Suspendu', GRADUATED: 'Diplômé'};
const fullName = (s: Pick<SchoolingStudent, 'last_name' | 'middle_name' | 'first_name'>) => [s.last_name, s.middle_name, s.first_name].filter(Boolean).join(' ');
const initials = (s: Pick<SchoolingStudent, 'last_name' | 'first_name'>) => `${s.last_name?.[0] ?? ''}${s.first_name?.[0] ?? ''}`;
const sections = (classes: SchoolClass[]) => [...new Map(classes.map(c => [c.section_id, {id: c.section_id, label: c.section_label ?? 'Section', code: c.section_code ?? ''}])).values()];
const levelOf = (c: SchoolClass) => (c.reference_code ?? c.label).toUpperCase();

/** Section first, then the classes of that section grouped by level; a search narrows long lists. */
export function ClassPicker({classes, value, onChange, invalid, suggested, levelLabels = {}}: {classes: SchoolClass[]; value: string; onChange: (id: string) => void; invalid?: boolean; suggested?: string; levelLabels?: Record<string, string>}) {
  const secs = useMemo(() => sections(classes), [classes]);
  const current = classes.find(c => c.id === value);
  const [section, setSection] = useState(current?.section_id ?? (secs.length === 1 ? secs[0].id : ''));
  const [q, setQ] = useState('');
  useEffect(() => { if (current && current.section_id !== section) setSection(current.section_id); }, [value]);
  const inSection = classes.filter(c => c.section_id === section && (!q.trim() || c.label.toLowerCase().includes(q.trim().toLowerCase())));
  const levels = [...new Map(inSection.map(c => [levelOf(c), c])).keys()];
  return <div className={`kp-picker ${invalid ? 'invalid' : ''}`}>
    <div className="kp-sections" role="radiogroup" aria-label="Section">{secs.map(s => <button key={s.id} type="button" role="radio" aria-checked={section === s.id} className={section === s.id ? 'on' : ''}
      onClick={() => { setSection(s.id); setQ(''); }}>{s.label}<small>{classes.filter(c => c.section_id === s.id).length}</small></button>)}</div>
    {section ? <>
      {classes.filter(c => c.section_id === section).length > 12 && <div className="kp-search"><NavGlyph g="search" size={15}/><input aria-label="Filtrer les classes" placeholder="Filtrer : 1re, Scientifique, B…" value={q} onChange={e => setQ(e.target.value)}/></div>}
      <div className="kp-levels">{levels.map(l => <div key={l} className="kp-level"><span>{levelLabels[l] ?? l}</span>
        <div className="kp-classes" role="radiogroup" aria-label={`Classes ${l}`}>{inSection.filter(c => levelOf(c) === l).map(c => <button key={c.id} type="button" role="radio" aria-checked={value === c.id}
          className={`${value === c.id ? 'on' : ''} ${suggested === c.id ? 'suggested' : ''}`} onClick={() => onChange(c.id)} title={c.label}>
          {c.label}{suggested === c.id && <em>proposée</em>}</button>)}</div></div>)}
        {levels.length === 0 && <p className="kp-empty">Aucune classe ne correspond.</p>}</div>
    </> : <p className="kp-empty">Choisissez d’abord la section ; ses classes apparaissent ensuite.</p>}
    {current && <p className="kp-chosen"><NavGlyph g="checkCircle" size={15}/> {current.section_label} · <b>{current.label}</b></p>}
  </div>;
}

/** Directory with Desktop filters (+ Humanités option), modern table, filtered exports. */
export function StudentDirectoryPro({token, schoolName, classes, filters, setFilters, students, loading, can, onSelect, page, hasMore, onPage}: {
  token: string; schoolName: string; classes: SchoolClass[]; filters: StudentFilters; setFilters: (f: StudentFilters) => void; students: SchoolingStudent[]; loading: boolean;
  can: (p: string) => boolean; onSelect: (s: SchoolingStudent) => void; page: number; hasMore: boolean; onPage: (p: number) => void}) {
  const [options, setOptions] = useState<SchoolOption[]>([]); const [years, setYears] = useState<AcademicYear[]>([]);
  useEffect(() => { listOptions(token).then(o => setOptions(o.filter(x => x.enabled))).catch(() => setOptions([])); listYearSelector(token).then(setYears).catch(() => setYears([])); }, [token]);
  const secs = sections(classes);
  const set = (patch: StudentFilters) => setFilters({...filters, ...patch});
  const classChoices = classes.filter(c => (!filters.section_id || c.section_id === filters.section_id) && (!filters.option_id || c.option_id === filters.option_id));
  const active = (['section_id', 'class_id', 'option_id', 'gender', 'status', 'academic_year_id'] as const).filter(k => filters[k]).length + (filters.all_years ? 1 : 0);
  async function pdf() { try { previewPdf(await studentDirectoryPdf(token, filters)); } catch (e) { toast.error(friendlyError(e)); } }
  async function xlsx() { try { await exportManaged(await studentDirectoryXlsx(token, filters), {school: schoolName, module: 'Scolarité', category: 'Élèves', filename: 'annuaire_eleves.xlsx'}); } catch (e) { toast.error(friendlyError(e)); } }
  return <section className="kp-directory">
    <div className="kp-toolbar">
      <div className="kp-searchBig"><NavGlyph g="search" size={18}/><input aria-label="Rechercher un élève" placeholder="Matricule, nom, famille, responsable ou téléphone…" value={filters.q ?? ''} onChange={e => set({q: e.target.value})}/></div>
      <div className="kp-exports">{can('students.directory.export') && <><button type="button" onClick={() => void pdf()}><NavGlyph g="doc" size={15}/>PDF</button><button type="button" onClick={() => void xlsx()}><NavGlyph g="sheet" size={15}/>Excel</button></>}</div>
    </div>
    <div className="kp-filters" role="group" aria-label="Filtres de l’annuaire">
      <label><span>Section</span><select value={filters.section_id ?? ''} onChange={e => set({section_id: e.target.value, class_id: '', option_id: e.target.value && secs.find(s => s.id === e.target.value)?.code !== 'SECONDAIRE' ? '' : filters.option_id})}>
        <option value="">Toutes</option>{secs.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
      {options.length > 0 && <label><span>Option</span><select value={filters.option_id ?? ''} onChange={e => set({option_id: e.target.value, class_id: ''})}><option value="">Toutes</option>{options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label>}
      <label><span>Classe</span><select value={filters.class_id ?? ''} onChange={e => set({class_id: e.target.value})}><option value="">Toutes</option>{classChoices.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
      <label><span>Sexe</span><select value={filters.gender ?? ''} onChange={e => set({gender: e.target.value as StudentFilters['gender']})}><option value="">Filles et garçons</option><option value="F">Filles</option><option value="M">Garçons</option></select></label>
      <label><span>Statut</span><select value={filters.status ?? ''} onChange={e => set({status: e.target.value})}><option value="">Tous</option>{Object.entries(STATUS_FR).slice(0, 4).map(([k, l]) => <option key={k} value={k}>{l}s</option>)}</select></label>
      <label><span>Année</span><select value={filters.all_years ? 'ALL' : filters.academic_year_id ?? ''} onChange={e => set(e.target.value === 'ALL' ? {all_years: true, academic_year_id: ''} : {all_years: false, academic_year_id: e.target.value})}>
        <option value="">Année en cours</option>{years.filter(y => y.status !== 'ACTIVE').map(y => <option key={y.id} value={y.id}>{y.label}</option>)}<option value="ALL">Tout l’historique</option></select></label>
      {active > 0 && <button type="button" className="kp-reset" onClick={() => setFilters({q: filters.q})}>Réinitialiser ({active})</button>}
    </div>
    <div className="kp-table" role="table" aria-label="Élèves">
      <div className="kp-row kp-head" role="row"><span role="columnheader">Élève</span><span role="columnheader">Classe</span><span role="columnheader">Famille</span><span role="columnheader">Dossier</span><span role="columnheader">Statut</span><span aria-hidden="true"/></div>
      {loading && students.length === 0 ? [0, 1, 2, 3].map(i => <div key={i} className="kp-row kp-skel"><i/><i/><i/><i/><i/></div>)
        : students.length === 0 ? <div className="kp-emptyRow"><NavGlyph g="students" size={26}/><b>Aucun élève ne correspond</b><small>Modifiez la recherche ou les filtres.</small></div>
        : students.map(s => <button key={s.id} type="button" role="row" className="kp-row" onClick={() => onSelect(s)}>
          <span className="kp-who"><i className={s.gender === 'F' ? 'f' : ''}>{initials(s)}</i><span><b>{fullName(s)}</b><small>{s.matricule}</small></span></span>
          <span><b>{s.class_label ?? '—'}</b><small>{s.section_label ?? ''}{filters.all_years && s.academic_year_label ? ` · ${s.academic_year_label}` : ''}</small></span>
          <span><b>{s.family_name ?? '—'}</b><small>{s.family_phone ?? 'Contact à compléter'}</small></span>
          <span className="kp-progress" title={`Dossier complété à ${s.profile_completeness} %`}><i><b style={{width: `${s.profile_completeness}%`}}/></i><small>{s.profile_completeness} %</small></span>
          <span><em className={`kp-status ${s.status.toLowerCase()}`}>{STATUS_FR[s.status] ?? s.status}</em></span>
          <span className="kp-chev" aria-hidden="true"><NavGlyph g="chevronRight" size={16}/></span>
        </button>)}
    </div>
    <div className="kp-pager"><span>Page {page + 1}{students.length ? ` · ${students.length} élève(s) affiché(s)` : ''}</span>
      <button type="button" disabled={page === 0} onClick={() => onPage(page - 1)}>‹ Précédente</button><button type="button" disabled={!hasMore} onClick={() => onPage(page + 1)}>Suivante ›</button></div>
  </section>;
}

/** Next class proposed for a re-enrollment: the level that follows, same option and same parallel letter when possible. */
export function proposeNextClass(last: {class_reference_code?: string | null; class_option_id?: string | null; class_label?: string | null}, classes: SchoolClass[], order: Record<string, number>): string {
  const ref = (last.class_reference_code ?? '').toUpperCase(); if (!ref || order[ref] === undefined) return '';
  const next = Object.entries(order).filter(([, o]) => o > order[ref]).sort((a, b) => a[1] - b[1])[0]?.[0]; if (!next) return '';
  const letter = /\s([A-J])$/.exec(last.class_label ?? '')?.[1];
  const pool = classes.filter(c => (c.reference_code ?? '').toUpperCase() === next);
  const sameOption = pool.filter(c => !last.class_option_id || c.option_id === last.class_option_id);
  const candidates = sameOption.length ? sameOption : pool;
  return (candidates.find(c => letter && c.label.endsWith(` ${letter}`)) ?? candidates[0])?.id ?? '';
}

export function ReenrollWizard({token, classes, refOrder, levelLabels, onClose, onDone}: {token: string; classes: SchoolClass[]; refOrder: Record<string, number>; levelLabels?: Record<string, string>; onClose: () => void; onDone: () => Promise<void>}) {
  const [q, setQ] = useState(''); const [hits, setHits] = useState<SchoolingStudent[]>([]); const [busy, setBusy] = useState(false); const [searching, setSearching] = useState(false);
  const [pupil, setPupil] = useState<SchoolingStudent | null>(null); const [classId, setClassId] = useState(''); const [error, setError] = useState('');
  const [active, setActive] = useState<AcademicYear | null>(null);
  useEffect(() => { listYearSelector(token).then(y => setActive(y.find(x => x.status === 'ACTIVE') ?? null)).catch(() => setActive(null)); }, [token]);
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onClose(); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [busy, onClose]);
  useEffect(() => { if (q.trim().length < 2) { setHits([]); return; } setSearching(true);
    const t = window.setTimeout(() => listStudents(token, {q: q.trim(), all_years: true, limit: 12}).then(r => setHits(r.items)).catch(() => setHits([])).finally(() => setSearching(false)), 220);
    return () => window.clearTimeout(t); }, [q, token]);
  const yearClasses = classes.filter(c => !active || c.academic_year_id === active.id);
  const suggested = pupil ? proposeNextClass(pupil, yearClasses, refOrder) : '';
  const already = pupil && active && pupil.academic_year_id === active.id && pupil.enrollment_status !== 'CANCELLED';
  function choose(s: SchoolingStudent) { setPupil(s); setError(''); setClassId(proposeNextClass(s, yearClasses, refOrder)); }
  async function submit() {
    if (!pupil) return; if (!classId) { setError('Choisissez la nouvelle classe.'); return; }
    if (!pupil.gender || pupil.gender === 'X') { setError('Le sexe de l’élève est à compléter dans sa fiche avant la réinscription.'); return; }
    try { setBusy(true); setError('');
      await enrollFamily(token, {family_id: pupil.family_id, household_confidence: 'CERTAIN', children: [{student_id: pupil.id, class_id: classId, gender: pupil.gender as 'M' | 'F', origin: 'REENROLLMENT'} as any]});
      toast.success(`${fullName(pupil)} est réinscrit(e) en ${classes.find(c => c.id === classId)?.label ?? 'nouvelle classe'}`); await onDone(); onClose();
    } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <div className="kp-backdrop" onClick={() => { if (!busy) onClose(); }}>
    <div className="kp-dialog" role="dialog" aria-modal="true" aria-labelledby="kp-re-title" onClick={e => e.stopPropagation()}>
      <header className="kp-dhead"><span className="kp-dicon"><NavGlyph g="sync" size={22}/></span><div><h3 id="kp-re-title">Réinscription</h3>
        <p>Élève déjà connu de l’école : sa fiche, sa famille et son historique sont conservés. {active ? `Année : ${active.label}.` : ''}</p></div>
        <button type="button" className="kp-close" aria-label="Fermer" onClick={onClose} disabled={busy}><NavGlyph g="close" size={18}/></button></header>
      <div className="kp-dbody">
        <section><h4><span>1</span>Retrouver l’élève</h4>
          <div className="kp-searchBig"><NavGlyph g="search" size={18}/><input autoFocus aria-label="Rechercher l’élève à réinscrire" placeholder="Matricule, nom de l’élève, famille ou téléphone…" value={q} onChange={e => setQ(e.target.value)}/></div>
          {!pupil && <div className="kp-hits">{searching && <p className="kp-empty">Recherche…</p>}
            {!searching && q.trim().length >= 2 && hits.length === 0 && <p className="kp-empty">Aucun élève connu ne correspond. Pour un nouvel élève, utilisez « Nouvelle inscription ».</p>}
            {hits.map(s => <button key={s.id} type="button" className="kp-hit" onClick={() => choose(s)}><i>{initials(s)}</i><span><b>{fullName(s)}</b><small>{s.matricule} · {s.class_label ?? 'sans classe'}{s.academic_year_label ? ` · ${s.academic_year_label}` : ''}</small></span>
              <em className={`kp-status ${s.status.toLowerCase()}`}>{STATUS_FR[s.status] ?? s.status}</em></button>)}</div>}
          {pupil && <div className="kp-pupil"><i>{initials(pupil)}</i><div><b>{fullName(pupil)}</b><small>{pupil.matricule} · famille {pupil.family_name ?? '—'}{pupil.family_phone ? ` · ${pupil.family_phone}` : ''}</small>
            <small>Dernière classe : <b>{pupil.class_label ?? '—'}</b>{pupil.academic_year_label ? ` (${pupil.academic_year_label})` : ''} · statut {STATUS_FR[pupil.status] ?? pupil.status}</small></div>
            <button type="button" className="kp-link" onClick={() => { setPupil(null); setClassId(''); }}>Changer</button></div>}
          {already && <div className="kp-warn" role="alert"><NavGlyph g="alert" size={16}/> Cet élève est déjà inscrit en {active?.label} ({pupil?.class_label}). Un changement de classe se fait depuis sa fiche.</div>}
          {pupil && pupil.status !== 'ACTIVE' && <div className="kp-note"><NavGlyph g="info" size={16}/> Statut actuel : {STATUS_FR[pupil.status] ?? pupil.status}. La réinscription le remet dans l’année en cours ; les dettes antérieures restent dues séparément.</div>}
        </section>
        {pupil && !already && <section><h4><span>2</span>Nouvelle classe {suggested && <small>la classe suivante est proposée</small>}</h4>
          <ClassPicker classes={yearClasses} value={classId} onChange={setClassId} suggested={suggested} levelLabels={levelLabels}/></section>}
        {error && <div className="error" role="alert">{error}</div>}
      </div>
      <footer className="kp-dfoot"><span className="kp-summary">{pupil && classId ? <>{fullName(pupil)} → <b>{classes.find(c => c.id === classId)?.label}</b></> : 'Retrouvez l’élève, puis choisissez sa nouvelle classe'}</span>
        <button type="button" className="kp-btn ghost" onClick={onClose} disabled={busy}>Annuler</button>
        <button type="button" className="kp-btn primary" disabled={busy || !pupil || !!already || !classId} onClick={() => void submit()}><NavGlyph g="sync" size={16}/>{busy ? 'Réinscription…' : 'Réinscrire'}</button></footer>
    </div></div>;
}
