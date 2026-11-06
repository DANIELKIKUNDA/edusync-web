// Structure & classes (2026-11-06, owner request): the classes are browsed by section and by level instead of one long list,
// with a search, compact class tiles (actions behind « ⋯ »), the sections & options in their own tab, and the Humanités
// classes named with the school sigles (« 1re HP », « 2e HSC A »). Same APIs and permissions as before.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {listOptions, putSection, setClassStatus, updateClass, type AcademicYear, type ReferenceCatalog, type SchoolClass, type SchoolOption, type SchoolSection} from './api';
import {confirmAction, promptText} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {Button as UIButton} from './platform/ui';
import {NavGlyph} from './platform/nav_icons';
import {ClassBatchDialog, OptionCatalog, OPTIONS_SECTION, optionSigle, sigleRenames} from './settings_wizards';

type View = 'classes' | 'sections';
const VIEW_KEY = 'edusync.settings.structure.view';
const readView = (): View => { try { return sessionStorage.getItem(VIEW_KEY) === 'sections' ? 'sections' : 'classes'; } catch { return 'classes'; } };
const statusOf = (c: SchoolClass) => c.status ?? (c.enabled ? 'ACTIVE' : 'INACTIVE');
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
const plural = (n: number, one: string, many: string) => `${n.toLocaleString('fr-FR')} ${n > 1 ? many : one}`;

export function Structure({token, sections, classes, years, refs, can, onDone}: {token: string; sections: SchoolSection[]; classes: SchoolClass[]; years: AcademicYear[];
  refs: ReferenceCatalog | null; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const [error, setError] = useState(''); const [options, setOptions] = useState<SchoolOption[]>([]); const [batch, setBatch] = useState(false);
  const [view, setViewState] = useState<View>(readView); const [sectionFilter, setSectionFilter] = useState('all'); const [query, setQuery] = useState('');
  const [menu, setMenu] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const setView = (v: View) => { setViewState(v); try { sessionStorage.setItem(VIEW_KEY, v); } catch { /* per-viewer convenience only */ } };
  async function loadOptions() { try { setOptions(await listOptions(token)); } catch { setOptions([]); } }
  useEffect(() => { void loadOptions(); }, [token]);
  useEffect(() => {
    if (!menu) return;
    const close = (e: Event) => { if (!(e.target as HTMLElement | null)?.closest?.('.structTile.menuOpen')) setMenu(null); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(null); };
    document.addEventListener('pointerdown', close); window.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', close); window.removeEventListener('keydown', key); };
  }, [menu]);

  const active = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const classYears = years.filter(y => classes.some(c => c.academic_year_id === y.id));
  const [yearId, setYearId] = useState(active?.id ?? classYears[0]?.id ?? '');
  useEffect(() => { if (!yearId || !years.some(y => y.id === yearId)) setYearId(active?.id ?? classYears[0]?.id ?? ''); }, [active?.id, years.length]);
  const year = years.find(y => y.id === yearId);
  const inYear = useMemo(() => classes.filter(c => c.academic_year_id === yearId), [classes, yearId]);
  const refOrder = useMemo(() => new Map((refs?.classes ?? []).map(r => [r.code, r])), [refs]);
  const q = fold(query);
  const visible = inYear.filter(c => (sectionFilter === 'all' || c.section_id === sectionFilter) && (!q || fold(c.label).includes(q)));
  const openCount = inYear.filter(c => statusOf(c) === 'ACTIVE').length;
  const students = inYear.reduce((n, c) => n + (c.student_count ?? 0), 0);
  const humanities = sections.find(s => s.code === OPTIONS_SECTION);
  const openOptions = options.filter(o => o.enabled && o.section_id === humanities?.id);
  const renames = can('settings.classes.rename') && refs ? sigleRenames(inYear, refs.classes, options) : [];
  const canCreate = can('settings.classes.create') && !!active && sections.length > 0 && !!refs;
  const manageClasses = can('settings.classes.activate') || can('settings.classes.rename');

  async function addSection(code: string, label: string) { try { setError(''); await putSection(token, {code, label, enabled: true}); await onDone(); } catch (e) { setError(friendlyError(e)); } }
  async function rename(c: SchoolClass) {
    setMenu(null);
    const label = await promptText({title: `Renommer ${c.label}`, message: 'Le libellé affiché change partout ; les élèves, l’historique et le statut de la classe ne changent pas.', label: 'Nouveau libellé', confirmLabel: 'Renommer', minLength: 2});
    if (!label || label === c.label) return;
    try { setError(''); await updateClass(token, c, {code: c.code, label}); toast.success(`Classe renommée : ${label}`); await onDone(); } catch (e) { setError(friendlyError(e)); }
  }
  // Desktop set_class_status: pause keeps the students (counted, visible, attached); archive only once the class is empty.
  async function changeStatus(c: SchoolClass, status: 'ACTIVE' | 'INACTIVE' | 'ARCHIVED') {
    setMenu(null); const n = c.student_count ?? 0;
    const ask = status === 'INACTIVE' ? {title: `Mettre ${c.label} en pause ?`, message: `${n > 0 ? `Ses ${n} élève(s) restent inscrits, comptés dans les effectifs et visibles. ` : ''}La classe n’est plus proposée pour de nouvelles inscriptions ni comme destination d’un changement de classe. Elle pourra être réactivée.`, confirmLabel: 'Mettre en pause', danger: true}
      : status === 'ARCHIVED' ? {title: `Archiver ${c.label} ?`, message: 'La classe est vide. Archivée, elle reste dans l’historique mais ne pourra plus être modifiée ni réactivée.', confirmLabel: 'Archiver', danger: true}
      : {title: `Réactiver ${c.label} ?`, message: 'La classe est de nouveau proposée pour les inscriptions et les changements de classe.', confirmLabel: 'Réactiver'};
    if (!await confirmAction(ask)) return;
    try { setError(''); await setClassStatus(token, c, status); toast.success(status === 'INACTIVE' ? `${c.label} en pause` : status === 'ARCHIVED' ? `${c.label} archivée` : `${c.label} réactivée`); await onDone(); } catch (e) { setError(friendlyError(e)); }
  }
  async function applySigles() {
    const sample = renames.slice(0, 6).map(r => `${r.cls.label} → ${r.label}`).join(' · ');
    if (!await confirmAction({title: `Renommer ${plural(renames.length, 'classe', 'classes')} avec les sigles ?`, message: `${sample}${renames.length > 6 ? ' …' : ''}. Seul le nom affiché change : les élèves, les paiements et l’historique restent attachés à la classe.`, confirmLabel: 'Appliquer les sigles'})) return;
    setBusy(true); setError(''); let ok = 0;
    for (const r of renames) { try { await updateClass(token, r.cls, {code: r.cls.code, label: r.label}); ok++; } catch (e) { setError(`${r.cls.label} : ${friendlyError(e)}`); break; } }
    setBusy(false); if (ok) { toast.success(`${plural(ok, 'classe renommée', 'classes renommées')} avec les sigles`); await onDone(); }
  }

  const shownSections = sections.filter(s => sectionFilter === 'all' || s.id === sectionFilter);
  const existing = new Set(sections.map(s => s.code));
  return <section className="panel structurePage">
    <div className="panelHead"><div><h3>Structure &amp; classes{year && <small> · {year.label}</small>}</h3><p>Les classes ouvertes par section et par niveau. Les sections et les options des Humanités se règlent dans le second onglet.</p></div>
      {canCreate && <UIButton variant="primary" icon="plus" onClick={() => setBatch(true)}>Ouvrir des classes</UIButton>}</div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="structStats">
      <div><b>{openCount}</b><span>classe{openCount > 1 ? 's' : ''} ouverte{openCount > 1 ? 's' : ''}</span></div>
      <div><b>{students.toLocaleString('fr-FR')}</b><span>élève{students > 1 ? 's' : ''}</span></div>
      <div><b>{sections.filter(s => s.enabled).length}</b><span>section{sections.filter(s => s.enabled).length > 1 ? 's' : ''}</span></div>
      <div><b>{openOptions.length}</b><span>option{openOptions.length > 1 ? 's' : ''} des Humanités</span></div>
    </div>
    <div className="structTabs" role="tablist" aria-label="Structure">
      <button type="button" role="tab" aria-selected={view === 'classes'} className={view === 'classes' ? 'on' : ''} onClick={() => setView('classes')}>Classes <small>{inYear.length}</small></button>
      <button type="button" role="tab" aria-selected={view === 'sections'} className={view === 'sections' ? 'on' : ''} onClick={() => setView('sections')}>Sections &amp; options <small>{sections.length}</small></button>
    </div>

    {view === 'classes' && <div role="tabpanel" aria-label="Classes">
      {!active && <div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Préparez une année scolaire avant d’ouvrir des classes : chaque classe appartient à une année.</p></div>}
      {renames.length > 0 && <div className="structNotice"><div><b>{renames.length > 1 ? `${renames.length} classes peuvent prendre leur sigle` : '1 classe peut prendre son sigle'}</b>
        <small>Exemple : « {renames[0].cls.label} » devient « {renames[0].label} ». Les élèves et l’historique ne changent pas.</small></div>
        <button type="button" className="softBtn" disabled={busy} onClick={() => void applySigles()}>{busy ? 'Renommage…' : 'Appliquer les sigles'}</button></div>}
      {inYear.length > 0 && <div className="structToolbar">
        <div className="structChips" role="group" aria-label="Filtrer par section">
          <button type="button" aria-pressed={sectionFilter === 'all'} className={sectionFilter === 'all' ? 'on' : ''} onClick={() => setSectionFilter('all')}>Toutes <small>{inYear.length}</small></button>
          {sections.map(s => { const n = inYear.filter(c => c.section_id === s.id).length; return n ? <button key={s.id} type="button" aria-pressed={sectionFilter === s.id} className={sectionFilter === s.id ? 'on' : ''} onClick={() => setSectionFilter(s.id)}>{s.label} <small>{n}</small></button> : null; })}
        </div>
        <div className="structFind">
          <input type="search" aria-label="Rechercher une classe" placeholder="Rechercher une classe (ex. 3e HP)" value={query} onChange={e => setQuery(e.target.value)}/>
          {classYears.length > 1 && <select aria-label="Année scolaire" value={yearId} onChange={e => setYearId(e.target.value)}>{classYears.map(y => <option key={y.id} value={y.id}>{y.label}</option>)}</select>}
        </div>
      </div>}
      {active && inYear.length === 0 && <div className="emptyGuide"><b>Aucune classe ouverte{year ? ` en ${year.label}` : ''}</b><p>{sections.length ? 'Utilisez « Ouvrir des classes » : plusieurs niveaux d’un coup, classes parallèles (A, B…) et une classe par option en Humanités.' : 'Choisissez d’abord les sections de l’école dans l’onglet « Sections & options ».'}</p></div>}
      {inYear.length > 0 && visible.length === 0 && <p className="structEmpty">Aucune classe ne correspond à « {query} ».</p>}
      {shownSections.map(s => {
        const list = visible.filter(c => c.section_id === s.id); if (!list.length) return null;
        const levels = new Map<string, SchoolClass[]>();
        for (const c of list) { const k = (c.reference_code ?? '').toUpperCase() || '—'; levels.set(k, [...(levels.get(k) ?? []), c]); }
        const ordered = [...levels.entries()].sort(([a], [b]) => (refOrder.get(a)?.sort_order ?? 9999) - (refOrder.get(b)?.sort_order ?? 9999) || a.localeCompare(b));
        // Levels of one or two classes (maternelle, primaire) read better as one grid; a level grouping only helps when it has many classes.
        const grouped = ordered.some(([, items]) => items.length > 2);
        const groups: [string, SchoolClass[]][] = grouped ? ordered : [['', ordered.flatMap(([, items]) => [...items].sort((a, b) => a.label.localeCompare(b.label, 'fr', {numeric: true})))]];
        return <section key={s.id} className="structSection" aria-label={s.label}>
          <header><h4>{s.label}</h4><small>{plural(list.length, 'classe', 'classes')} · {plural(list.reduce((n, c) => n + (c.student_count ?? 0), 0), 'élève', 'élèves')}</small></header>
          {groups.map(([level, items]) => <div key={level || 'all'} className={`structLevel ${level ? '' : 'flat'}`}>
            {level && <div className="structLevelHead"><b>{refOrder.get(level)?.label ?? (level === '—' ? 'Autres classes' : level)}</b><small>{plural(items.length, 'classe', 'classes')} · {plural(items.reduce((n, c) => n + (c.student_count ?? 0), 0), 'élève', 'élèves')}</small></div>}
            <ul className="structTiles">{(level ? [...items].sort((a, b) => a.label.localeCompare(b.label, 'fr', {numeric: true})) : items).map(c => {
              const st = statusOf(c); const n = c.student_count ?? 0; const locked = c.academic_year_status === 'CLOSED' || c.academic_year_status === 'ARCHIVED';
              const actions = manageClasses && !locked && st !== 'ARCHIVED';
              return <li key={c.id} className={`structTile ${st === 'ACTIVE' ? '' : 'off'} ${menu === c.id ? 'menuOpen' : ''}`}>
                <div className="structTileMain" title={`${c.label} · ${plural(n, 'élève', 'élèves')}`}><b>{c.label}</b><small>{plural(n, 'élève', 'élèves')}{st === 'INACTIVE' ? ' · en pause' : st === 'ARCHIVED' ? ' · archivée' : ''}</small></div>
                {actions && <button type="button" className="structMenuBtn" aria-label={`Gérer ${c.label}`} aria-haspopup="menu" aria-expanded={menu === c.id} onClick={() => setMenu(m => m === c.id ? null : c.id)}>
                  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="3" cy="8" r="1.5" fill="currentColor"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="13" cy="8" r="1.5" fill="currentColor"/></svg></button>}
                {actions && menu === c.id && <div className="structMenu" role="menu" aria-label={`Actions — ${c.label}`}>
                  {can('settings.classes.rename') && <button type="button" role="menuitem" onClick={() => void rename(c)}>Renommer</button>}
                  {can('settings.classes.activate') && (st === 'ACTIVE' ? <button type="button" role="menuitem" onClick={() => void changeStatus(c, 'INACTIVE')}>Mettre en pause</button>
                    : <button type="button" role="menuitem" onClick={() => void changeStatus(c, 'ACTIVE')}>Réactiver</button>)}
                  {can('settings.classes.activate') && n === 0 && <button type="button" role="menuitem" className="dangerText" onClick={() => void changeStatus(c, 'ARCHIVED')}>Archiver</button>}
                </div>}
              </li>; })}</ul>
          </div>)}
        </section>; })}
    </div>}

    {view === 'sections' && <div role="tabpanel" aria-label="Sections et options">
      <div className="sw-field"><span>Sections organisées par l’école</span><div className="suggestions">{refs?.sections.map(r => <button disabled={existing.has(r.code) || !can('settings.sections.manage')} key={r.code} onClick={() => void addSection(r.code, r.label)}>{existing.has(r.code) ? <NavGlyph g="check" size={14}/> : <NavGlyph g="plus" size={14}/>} {r.label}</button>)}</div></div>
      {sections.length === 0 && <div className="emptyGuide"><b>Aucune section</b><p>Touchez les sections que l’école organise réellement ci-dessus. Vous ouvrirez ensuite les classes de chaque section.</p></div>}
      <div className="cardsList sectionList">{sections.map(s => <article key={s.id}><div><b>{s.label}</b>
        <small>{plural(classes.filter(c => c.section_id === s.id && c.academic_year_id === active?.id && statusOf(c) === 'ACTIVE').length, 'classe ouverte', 'classes ouvertes')}{active ? ` en ${active.label}` : ''}</small>
        {s.code === OPTIONS_SECTION && s.enabled && <OptionCatalog token={token} section={s} options={options} canManage={can('settings.options.manage')} onChanged={loadOptions}/>}
        {s.code !== OPTIONS_SECTION && <small className="sw-hint">Pas d’options en {s.label} : elles n’existent qu’en Humanités.</small>}</div>
        <em className={`pill ${s.enabled ? 'ready' : ''}`}>{s.enabled ? 'Active' : 'Inactive'}</em></article>)}</div>
      {openOptions.length > 0 && <div className="structSigles"><b>Sigles des classes des Humanités</b>
        <small>Une classe ouverte prend le sigle de son option : « 1re {optionSigle(openOptions[0])} », « 2e {optionSigle(openOptions[0])} A »… Le nom d’une classe reste modifiable (« Renommer »).</small>
        <dl>{openOptions.map(o => <div key={o.id}><dt>{optionSigle(o)}</dt><dd>{o.label}</dd></div>)}</dl></div>}
    </div>}
    {batch && active && refs && <ClassBatchDialog token={token} year={active} sections={sections} refs={refs} options={options} classes={classes} onClose={() => setBatch(false)} onDone={onDone}/>}
  </section>;
}
