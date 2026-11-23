import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {acceptClassSuggestions, getCalendars, getClassLinks, getProgrammes, getTeaching, getReferential, getRefProgramme, linkClass, unlinkClass,
  type ClassLink, type ClassLinks, type MaxKey, type RefClass, type Referential, type RefProgramme} from './api';
import {Modal} from './platform/account';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {Button, EmptyState, PageHeader, Skeleton} from './platform/ui';
import {CalendarTab} from './pedagogy_calendar';
import {ProgrammesTab} from './pedagogy_programmes';
import {MyClassesTab, TeachersTab} from './pedagogy_teachers';
import {GradeEntry, GradeProgressTab} from './pedagogy_grades';
import {ConductArea} from './pedagogy_conduct';
import './pedagogy_grades.css';
import './pedagogy_teachers.css';
import './pedagogy.css';
import './pedagogy_v2.css';

/* V2 lot 1 — « Pédagogie » (module sold apart, owner 2026-11-22). Two tabs:
   · Correspondance des classes: each class of the school → its official MINEDUC class (EduSync suggests, the school confirms);
   · Référentiel officiel: sections, the 51 options by group, every official class and its programme (bulletin order, maxima).
   The server refuses everything without the module and decides who may link (pedagogy.class_links.manage). */

const COL: Record<MaxKey, string> = {max_p1: 'P1', max_p2: 'P2', max_ex1: 'EX1', max_p3: 'P3', max_p4: 'P4', max_ex2: 'EX2', max_p5: 'P5', max_p6: 'P6', max_ex3: 'EX3'};
const SECTION_OF: Record<string, 'MAT' | 'PRI' | 'SEC'> = {MATERNELLE: 'MAT', PRIMAIRE: 'PRI', SECONDAIRE: 'SEC'};
const CYCLE_LABEL: Record<string, string> = {MATERNELLE: 'Maternelle', PRIMAIRE: 'Primaire', EB: 'Éducation de base', HUMANITE: 'Humanités'};
type Tab = 'mine' | 'steps' | 'follow' | 'links' | 'calendar' | 'programmes' | 'teachers' | 'conduct' | 'referential';
const MANAGE_ANY = ['pedagogy.class_links.manage', 'pedagogy.calendar.manage', 'pedagogy.programmes.manage', 'pedagogy.teaching.manage'];
/* tab → label and the rights that show it (the server checks again) */
const TABS: [Tab, string, (has: (c: string) => boolean) => boolean][] = [
  ['mine', 'Mes classes', has => has('pedagogy.teaching.own.read')],
  ['steps', 'Étapes', has => MANAGE_ANY.some(has)],
  ['follow', 'Suivi des cotes', has => has('pedagogy.grades.read')],
  ['links', 'Classes', has => MANAGE_ANY.some(has)],
  ['calendar', 'Calendrier', has => has('pedagogy.referential.read')],
  ['programmes', 'Programmes', has => has('pedagogy.referential.read')],
  ['teachers', 'Enseignants', has => has('pedagogy.teaching.manage')],
  ['conduct', 'Conduite', has => has('pedagogy.referential.read') || has('pedagogy.conduct.report')],
  ['referential', 'Référentiel', has => has('pedagogy.referential.read')]];

export default function PedagogyPage({token, permissions = []}: {token: string; permissions?: string[]}) {
  const has = (c: string) => permissions.includes(c);
  const tabs = TABS.filter(([, , show]) => show(has));
  const first = tabs[0]?.[0] ?? 'referential';
  const [tab, setTab] = useState<Tab>(() => { try { const t = sessionStorage.getItem('edusync.pedagogy.tab') as Tab; return tabs.some(([k]) => k === t) ? t : first; } catch { return first; } });
  const [ref, setRef] = useState<Referential | null>(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const [entry, setEntry] = useState<null | {classId: string; course: string}>(null);
  useEffect(() => { getReferential(token).then(setRef).catch(e => setError(friendlyError(e))); }, [token]);
  const go = (t: Tab) => { setEntry(null); setTab(t); try { sessionStorage.setItem('edusync.pedagogy.tab', t); } catch { /* private mode */ } window.scrollTo({top: 0}); };
  const changed = () => setNonce(n => n + 1);
  return <div className="ui-page pg">
    {/* while marking: focus mode — no header nor tabs, the pupils take the whole phone screen (« ← Mes classes » goes back) */}
    {!entry && <PageHeader eyebrow={ref ? `Référentiel ${ref.version.code.replace('MINEDUC-', 'MINEDUC ').replace('-V2', '')}` : 'Référentiel officiel'}
      title="Pédagogie" subtitle="Classes, calendrier et programmes officiels de l’école."/>}
    {!entry && <div className="pg-tabs" role="tablist" aria-label="Pédagogie">
      {tabs.map(([k, label]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'active' : ''} onClick={() => go(k)}>{label}</button>)}
    </div>}
    {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Pédagogie indisponible</b><small>{error}</small></div></div>}
    {!error && !ref && <Skeleton lines={6}/>}
    {ref && entry && <GradeEntry token={token} classId={entry.classId} course={entry.course} onBack={() => { setEntry(null); changed(); }}/>}
    {ref && !entry && tab === 'mine' && <MyClassesTab key={nonce} token={token} onOpen={(classId, course) => { setEntry({classId, course}); window.scrollTo({top: 0}); }}/>}
    {ref && !entry && tab === 'follow' && <GradeProgressTab token={token}/>}
    {ref && !entry && tab === 'steps' && <StepsTab key={nonce} token={token} go={go} canTeach={has('pedagogy.teaching.manage')}/>}
    {ref && !entry && tab === 'links' && <LinksTab token={token} referential={ref} onChanged={changed}/>}
    {ref && !entry && tab === 'calendar' && <CalendarTab token={token} onChanged={changed}/>}
    {ref && !entry && tab === 'programmes' && <ProgrammesTab token={token} onChanged={changed}/>}
    {ref && !entry && tab === 'teachers' && <TeachersTab token={token} onChanged={changed}/>}
    {ref && !entry && tab === 'conduct' && <ConductArea token={token} canReport={has('pedagogy.conduct.report')} canConfigure={has('pedagogy.conduct.configure')}/>}
    {ref && !entry && tab === 'referential' && <ReferentialTab token={token} referential={ref}/>}
  </div>;
}

// ------------------------------------------------------------------------------------------------ guided steps
type StepState = {done: boolean; text: string; action: string};
function StepsTab({token, go, canTeach}: {token: string; go: (t: Tab) => void; canTeach: boolean}) {
  const [steps, setSteps] = useState<StepState[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.all([getClassLinks(token), getCalendars(token).catch(() => null), getProgrammes(token).catch(() => null),
      canTeach ? getTeaching(token).catch(() => null) : Promise.resolve(null)]).then(([links, cals, progs, teach]) => {
      const assigned = teach ? teach.items.reduce((n, i) => n + i.assigned, 0) : 0;
      const titled = teach ? teach.items.filter(i => i.titular).length : 0;
      const s = links.summary; const calsDone = !!cals && cals.calendars.every(c => c.status === 'VALIDATED');
      const pendingCals = cals ? cals.calendars.filter(c => c.status !== 'VALIDATED').length : 0;
      setSteps([
        {done: s.classes > 0 && s.linked === s.classes, action: s.to_confirm ? `Confirmer ${s.to_confirm} proposition${s.to_confirm > 1 ? 's' : ''}` : 'Voir les classes',
          text: s.classes === 0 ? 'Aucune classe pour l’année en cours.' : `${s.linked} classe${s.linked > 1 ? 's' : ''} sur ${s.classes} reliée${s.linked > 1 ? 's' : ''} au programme officiel.`},
        {done: calsDone, action: calsDone ? 'Voir le calendrier' : 'Vérifier les dates',
          text: calsDone ? 'Calendrier validé : les périodes et les examens sont fixés.' : `${pendingCals} calendrier${pendingCals > 1 ? 's' : ''} à vérifier puis valider (dates déjà proposées).`},
        {done: !!progs && progs.summary.classes > 0 && progs.summary.in_use === progs.summary.classes,
          action: progs?.summary.adoptable ? 'Utiliser les programmes officiels' : progs?.summary.without_official ? `Construire ${progs.summary.without_official} programme${progs.summary.without_official > 1 ? 's' : ''}` : 'Voir les programmes',
          text: !progs || progs.summary.classes === 0 ? 'Disponible après l’étape 1.'
            : `${progs.summary.in_use} programme${progs.summary.in_use > 1 ? 's' : ''} en service sur ${progs.summary.classes}.`
              + (progs.summary.without_official && !progs.summary.adoptable ? ` ${progs.summary.without_official} classe${progs.summary.without_official > 1 ? 's n’ont' : ' n’a'} pas de programme officiel (ex. maternelle) : construisez-le à partir des cours officiels.` : '')},
        ...(teach ? [{done: teach.summary.courses > 0 && assigned === teach.summary.courses && titled === teach.summary.classes,
          action: teach.summary.teachers ? 'Attribuer les cours' : 'Voir comment faire',
          text: !teach.summary.teachers ? 'Donnez d’abord le rôle Enseignant à vos professeurs (Accès et rôles).'
            : `${assigned} cours attribués sur ${teach.summary.courses} · ${titled} classe${titled > 1 ? 's' : ''} avec titulaire sur ${teach.summary.classes}.`}] : []),
      ]);
    }).catch(e => setError(friendlyError(e)));
  }, [token]);
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Étapes indisponibles</b><small>{error}</small></div></div>;
  if (!steps) return <Skeleton lines={5}/>;
  const done = steps.filter(s => s.done).length; const n = steps.length;
  const meta: [Tab, string, string][] = [['links', 'Relier les classes', 'layers'], ['calendar', 'Fixer le calendrier', 'calendar'],
    ['programmes', 'Mettre les programmes en service', 'doc'], ['teachers', 'Attribuer les cours et les titulaires', 'users']];
  const next = steps.findIndex(s => !s.done);
  return <div className="ps">
    <div className="ps-progress" role="progressbar" aria-valuemin={0} aria-valuemax={n} aria-valuenow={done} aria-label="Étapes terminées">
      <div><b>{done === n ? 'La pédagogie est prête' : `${done} étape${done > 1 ? 's' : ''} sur ${n} terminée${done > 1 ? 's' : ''}`}</b>
        <small>{done === n ? 'Prochaine étape : la saisie des cotes.' : 'Suivez les étapes dans l’ordre : EduSync a déjà tout préparé.'}</small></div>
      <i><span style={{width: `${done / n * 100}%`}}/></i>
    </div>
    <ol className="ps-steps">{steps.map((s, i) => <li key={meta[i][0]} className={s.done ? 'ps-done' : i === next ? 'ps-next' : ''}>
      <span className="ps-num" aria-hidden="true">{s.done ? <NavGlyph g="check" size={18}/> : i + 1}</span>
      <div className="ps-body"><b>{meta[i][1]}</b><small>{s.text}</small></div>
      <Button variant={i === next ? 'primary' : 'secondary'} onClick={() => go(meta[i][0])}>{s.action}</Button>
    </li>)}</ol>
  </div>;
}

// ------------------------------------------------------------------------------------------------ class links
function LinksTab({token, referential, onChanged}: {token: string; referential: Referential; onChanged?: () => void}) {
  const [data, setData] = useState<ClassLinks | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [choosing, setChoosing] = useState<ClassLink | null>(null);
  const load = useCallback(() => { setError(''); getClassLinks(token).then(setData).catch(e => setError(friendlyError(e))); }, [token]);
  useEffect(load, [load]);
  async function act(key: string, run: () => Promise<unknown>, ok: string) {
    setBusy(key);
    try { await run(); toast.success(ok); load(); onChanged?.(); } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(''); }
  }
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Correspondances indisponibles</b><small>{error}</small></div>
    <Button onClick={load}>Réessayer</Button></div>;
  if (!data) return <Skeleton lines={6}/>;
  const s = data.summary;
  const sections = [...new Set(data.items.map(i => i.section_label))];
  if (data.items.length === 0) return <EmptyState icon="layers" title="Aucune classe pour l’année en cours" text="Ouvrez d’abord les classes de l’année dans Paramètres › Structure."/>;
  return <>
    <div className="pg-summary" aria-label="Résumé">
      <div><b>{s.linked}/{s.classes}</b><small>classes reliées</small></div>
      <div className={s.to_confirm ? 'pg-warn' : ''}><b>{s.to_confirm}</b><small>propositions à confirmer</small></div>
      <div className={s.without_suggestion ? 'pg-warn' : ''}><b>{s.without_suggestion}</b><small>à choisir</small></div>
      <div className={s.without_programme ? 'pg-warn' : ''}><b>{s.without_programme}</b><small>sans programme officiel</small></div>
    </div>
    {data.can_manage && s.to_confirm > 0 && <div className="pg-callout">
      <NavGlyph g="sparkles" size={18}/><div><b>EduSync propose une classe officielle pour {s.to_confirm} classe{s.to_confirm > 1 ? 's' : ''}.</b>
        <small>Vérifiez la liste, puis confirmez en une fois. Vous pouvez tout modifier ensuite.</small></div>
      <Button variant="primary" disabled={!!busy} onClick={() => void act('all', () => acceptClassSuggestions(token), 'Propositions confirmées')}>
        {busy === 'all' ? 'Confirmation…' : `Confirmer les ${s.to_confirm} propositions`}</Button>
    </div>}
    {sections.map(sec => <section key={sec} className="pg-section" aria-label={sec}>
      <h3>{sec}</h3>
      <ul className="pg-links">{data.items.filter(i => i.section_label === sec).map(i => <li key={i.class_id} className={i.link ? 'pg-linked' : 'pg-open'}>
        <div className="pg-class"><b>{i.label}</b>{i.option_label && <small>{i.option_label}</small>}</div>
        <div className="pg-target">
          {i.link ? <><span className="pg-arrow" aria-hidden="true">→</span><span><b className="pg-code">{i.link.ref_class_code}</b><small>{i.link.label}</small>
              {!i.link.has_programme && <em className="pg-noprog">Sans programme officiel</em>}</span></>
            : i.suggestion ? <><span className="pg-arrow pg-arrow-soft" aria-hidden="true">→</span><span><b className="pg-code pg-code-soft">{i.suggestion.ref_class_code}</b>
              <small>Proposé : {i.suggestion.label}</small></span></>
              : <span className="pg-none">Aucune proposition : choisissez la classe officielle</span>}
        </div>
        {data.can_manage && <div className="pg-actions">
          {!i.link && i.suggestion && <Button size="sm" variant="primary" disabled={!!busy}
            onClick={() => void act(i.class_id, () => linkClass(token, i.class_id, i.suggestion!.ref_class_code), `${i.label} → ${i.suggestion!.ref_class_code}`)}>Confirmer</Button>}
          <Button size="sm" variant={i.link ? 'quiet' : 'secondary'} disabled={!!busy} onClick={() => setChoosing(i)} aria-label={`${i.link ? 'Modifier' : 'Choisir'} la classe officielle de ${i.label}`}>{i.link ? 'Modifier' : 'Choisir'}</Button>
        </div>}
      </li>)}</ul>
    </section>)}
    {choosing && <ChooseDialog token={token} item={choosing} referential={referential} onClose={() => setChoosing(null)}
      onDone={() => { setChoosing(null); load(); onChanged?.(); }}/>}
  </>;
}

function ChooseDialog({token, item, referential, onClose, onDone}: {token: string; item: ClassLink; referential: Referential; onClose: () => void; onDone: () => void}) {
  const section = SECTION_OF[(item.section_code || '').toUpperCase()];
  const [code, setCode] = useState(item.link?.ref_class_code || item.suggestion?.ref_class_code || '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const options = new Map(referential.groups.flatMap(g => g.options.map(o => [o.code, {...o, group: g.label}] as const)));
  const candidates = referential.classes.filter(c => !section || c.section_code === section);
  const groups = useMemo(() => {
    const out = new Map<string, RefClass[]>();
    for (const c of candidates) {
      const o = c.option_code ? options.get(c.option_code) : null;
      const key = o ? `${o.group} — ${o.label} (${o.sigle})` : CYCLE_LABEL[c.cycle];
      out.set(key, [...(out.get(key) || []), c]);
    }
    return [...out.entries()];
  }, [referential, section]);
  async function save(e: React.FormEvent) {
    e.preventDefault(); if (!code) { setError('Choisissez la classe officielle.'); return; }
    setBusy(true); setError('');
    try { await linkClass(token, item.class_id, code); toast.success(`${item.label} → ${code}`); onDone(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError('');
    try { await unlinkClass(token, item.class_id); toast.success('Correspondance retirée'); onDone(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <Modal title="Classe officielle" subtitle={`${item.label} · ${item.section_label}`} onClose={onClose}>
    <form className="es-form pg-choose" onSubmit={save} noValidate>
      <label htmlFor="pg-ref">Classe du référentiel MINEDUC *</label>
      <select id="pg-ref" value={code} onChange={e => setCode(e.target.value)}>
        <option value="">— Choisir —</option>
        {groups.map(([label, list]) => <optgroup key={label} label={label}>{list.map(c =>
          <option key={c.code} value={c.code}>{c.code} · {c.label}{c.has_programme ? '' : ' (sans programme)'}</option>)}</optgroup>)}
      </select>
      <p className="es-hint">La classe garde son nom dans l’école. Ce lien sert au programme, aux cotes et aux bulletins.</p>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot">
        {item.link && <button type="button" className="es-btn es-btn-ghost pg-remove" disabled={busy} onClick={() => void remove()}>Retirer le lien</button>}
        <button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <button className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer'}</button>
      </div>
    </form>
  </Modal>;
}

// ------------------------------------------------------------------------------------------------ referential
function ReferentialTab({token, referential}: {token: string; referential: Referential}) {
  const [section, setSection] = useState<'MAT' | 'PRI' | 'SEC'>('SEC');
  const [group, setGroup] = useState('GENERAL');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const options = useMemo(() => new Map(referential.groups.flatMap(g => g.options.map(o => [o.code, o] as const))), [referential]);
  const needle = q.trim().toLowerCase();
  const list = referential.classes.filter(c => {
    if (c.section_code !== section) return false;
    const o = c.option_code ? options.get(c.option_code) : null;
    if (section === 'SEC' && !needle && o && o.option_group !== group) return false;
    if (!needle) return true;
    return [c.code, c.label, o?.sigle, o?.label, o ? String(o.code) : ''].some(v => (v || '').toLowerCase().includes(needle));
  });
  const byOption = new Map<string, RefClass[]>();
  for (const c of list) {
    const o = c.option_code ? options.get(c.option_code) : null;
    const key = o ? `${o.code} · ${o.sigle} — ${o.label}` : CYCLE_LABEL[c.cycle];
    byOption.set(key, [...(byOption.get(key) || []), c]);
  }
  return <>
    <div className="pg-filters">
      <div className="pg-chips" role="group" aria-label="Section">
        {referential.sections.map(s => <button key={s.code} type="button" aria-pressed={section === s.code} onClick={() => setSection(s.code as typeof section)}>{s.label}</button>)}
      </div>
      {section === 'SEC' && <div className="pg-chips" role="group" aria-label="Groupe d’options">
        {referential.groups.map(g => <button key={g.code} type="button" aria-pressed={!needle && group === g.code} onClick={() => { setGroup(g.code); setQ(''); }}>
          {g.label}<i>{g.options.length}</i></button>)}
      </div>}
      <label className="pg-search"><NavGlyph g="search" size={16}/><span className="sr-only">Rechercher</span>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Code, sigle ou option (ex. CG, 301, 4SC)" inputMode="search"/></label>
    </div>
    {list.length === 0 && <EmptyState icon="search" title="Aucune classe" text="Modifiez la recherche ou la section."/>}
    {[...byOption.entries()].map(([label, classes]) => <section key={label} className="pg-section">
      <h3>{label}</h3>
      <ul className="pg-refclasses">{classes.map(c => <li key={c.code}>
        <button type="button" onClick={() => setOpen(c.code)} aria-label={`Programme ${c.label}`}>
          <b className="pg-code">{c.code}</b><span>{c.label}</span>
          {c.has_programme ? <small>{c.courses} cours · {c.structure === 'SEMESTRIEL' ? 'semestriel' : 'trimestriel'}</small> : <em className="pg-noprog">Sans programme officiel</em>}
        </button></li>)}</ul>
    </section>)}
    {open && <ProgrammeDialog token={token} code={open} onClose={() => setOpen(null)}/>}
  </>;
}

function ProgrammeDialog({token, code, onClose}: {token: string; code: string; onClose: () => void}) {
  const [p, setP] = useState<RefProgramme | null>(null); const [error, setError] = useState('');
  useEffect(() => { getRefProgramme(token, code).then(setP).catch(e => setError(friendlyError(e))); }, [token, code]);
  let lastDomain: string | null = null;
  return <Modal wide title={p ? `${p.class.code} · ${p.class.label}` : code} subtitle={p ? [p.class.option_label, p.class.structure === 'SEMESTRIEL' ? 'Semestriel' : 'Trimestriel', `${p.lines.length} cours`].filter(Boolean).join(' · ') : 'Programme officiel'} onClose={onClose}>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {!p && !error && <Skeleton lines={8}/>}
    {p && p.lines.length === 0 && <EmptyState icon="info" title="Pas de programme officiel" text="La source MINEDUC ne contient pas encore le programme de cette classe. L’école pourra saisir ses cours au lot suivant."/>}
    {p && p.lines.length > 0 && <div className="pg-table-wrap" tabIndex={0} aria-label="Programme, défilement horizontal possible">
      <table className="pg-table" data-keep-table>
        <thead><tr><th scope="col">Cours</th>{p.columns.map(k => <th key={k} scope="col" className={k.includes('ex') ? 'pg-ex' : ''}>{COL[k]}</th>)}</tr></thead>
        <tbody>{p.lines.map(l => {
          const head = l.domain && l.domain !== lastDomain ? l.domain : null; lastDomain = l.domain || lastDomain;
          return <React.Fragment key={l.course_code}>
            {head && <tr className="pg-domain"><th colSpan={p.columns.length + 1} scope="rowgroup">{head}</th></tr>}
            <tr><th scope="row">{l.label}{!l.mandatory && <em> facultatif</em>}{!l.has_exam && <em> sans examen</em>}{l.subdomain && <small>{l.subdomain}</small>}</th>
              {p.columns.map(k => <td key={k} className={k.includes('ex') ? 'pg-ex' : ''}>{l[k] || '—'}</td>)}</tr>
          </React.Fragment>;
        })}</tbody>
        <tfoot><tr><th scope="row">Maxima généraux</th>{p.columns.map(k => <td key={k} className={k.includes('ex') ? 'pg-ex' : ''}>{p.totals[k]}</td>)}</tr></tfoot>
      </table>
    </div>}
  </Modal>;
}
