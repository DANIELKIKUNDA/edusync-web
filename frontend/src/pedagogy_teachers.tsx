import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {assignAllCourses, assignCourse, getConductScale, getMyTeaching, getTeaching, saveConductScale, setTitular,
  type ConductRule, type ConductScale, type MyTeaching, type Teaching, type TeachingClass} from './api';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {Button, EmptyState, Skeleton} from './platform/ui';

/* V2 lot 3a (owner 2026-11-22). Parent project rules: grades by the teacher of the course only; one titular per class (a
   teacher may hold 2 or 3 classes — owner), titular powers effective in maternelle / primaire. Conduct is COMPUTED (points
   licence): the school only sets its scale here; the facts are reported in lot 3b. */

const msg = friendlyError;

// ------------------------------------------------------------------------------------------------ teachers & titulars
export function TeachersTab({token, onChanged}: {token: string; onChanged?: () => void}) {
  const [data, setData] = useState<Teaching | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => { setError(''); getTeaching(token).then(setData).catch(e => setError(msg(e))); }, [token]);
  useEffect(load, [load]);
  const replace = (c: TeachingClass) => { setData(d => d && {...d, items: d.items.map(x => x.class_id === c.class_id ? c : x)}); onChanged?.(); };
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Attributions indisponibles</b><small>{error}</small></div><Button onClick={load}>Réessayer</Button></div>;
  if (!data) return <Skeleton lines={6}/>;
  const s = { ...data.summary, with_titular: data.items.filter(i => i.titular).length, assigned: data.items.reduce((n, i) => n + i.assigned, 0) };
  const sections = [...new Set(data.items.map(i => i.section_label))];
  return <>
    <div className="pg-summary" aria-label="Résumé">
      <div className={s.teachers ? '' : 'pg-warn'}><b>{s.teachers}</b><small>enseignant{s.teachers > 1 ? 's' : ''}</small></div>
      <div className={s.with_titular === s.classes ? 'pg-ok' : 'pg-warn'}><b>{s.with_titular}/{s.classes}</b><small>classes avec titulaire</small></div>
      <div className={s.assigned === s.courses && s.courses ? 'pg-ok' : 'pg-warn'}><b>{s.assigned}/{s.courses}</b><small>cours attribués</small></div>
      <div className={s.without_programme ? 'pg-warn' : ''}><b>{s.without_programme}</b><small>classes sans programme en service</small></div>
    </div>
    {data.teachers.length === 0 && <div className="pg-callout"><NavGlyph g="info" size={18}/><div><b>Aucun enseignant pour le moment</b>
      <small>Dans « Accès et rôles », donnez le rôle <b>Enseignant</b> à chaque professeur. Il apparaîtra ici pour recevoir ses cours.</small></div></div>}
    {sections.map(sec => <section key={sec} className="pg-section"><h3>{sec}</h3>
      <ul className="pt-list">{data.items.filter(i => i.section_label === sec).map(c => <ClassCard key={c.class_id} token={token} cls={c} teachers={data.teachers} onSaved={replace}/>)}</ul>
    </section>)}
  </>;
}

function ClassCard({token, cls, teachers, onSaved}: {token: string; cls: TeachingClass; teachers: Teaching['teachers']; onSaved: (c: TeachingClass) => void}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [bulk, setBulk] = useState(cls.titular?.membership_id || '');
  useEffect(() => { if (!bulk && cls.titular) setBulk(cls.titular.membership_id); }, [cls.titular]);
  async function run(key: string, fn: () => Promise<TeachingClass>, ok: string) {
    setBusy(key);
    try { onSaved(await fn()); toast.success(ok); } catch (e) { toast.error(msg(e)); } finally { setBusy(''); }
  }
  const total = cls.courses.length; const done = cls.assigned === total && total > 0;
  const options = <>{teachers.map(t => <option key={t.membership_id} value={t.membership_id}>{t.full_name}</option>)}</>;
  return <li className={done && cls.titular ? 'pt-done' : ''}>
    <div className="pt-head">
      <div><b>{cls.label}</b>{cls.ref_class_code && <small><span className="pg-code">{cls.ref_class_code}</span></small>}</div>
      <span className={`pc-chip ${done ? 'pc-ok' : total ? 'pc-warn' : 'pc-muted'}`}>{total ? `${cls.assigned}/${total} cours attribués` : 'Sans programme en service'}</span>
    </div>
    <label className="pt-field"><span>Titulaire{cls.titular_effective ? ' · conduite et bulletins de la classe' : ''}</span>
      <select value={cls.titular?.membership_id || ''} disabled={!!busy || !teachers.length}
        onChange={e => void run('titular', () => setTitular(token, cls.class_id, e.target.value || null), e.target.value ? 'Titulaire enregistré' : 'Titulaire retiré')}>
        <option value="">— Aucun titulaire —</option>{options}
      </select></label>
    {total > 0 && cls.assigned < total && <div className="pt-bulk">
      <label className="pt-field"><span>Donner tous les cours restants à</span>
        <select value={bulk} onChange={e => setBulk(e.target.value)} disabled={!!busy || !teachers.length}><option value="">— Choisir un enseignant —</option>{options}</select></label>
      <Button variant="primary" disabled={!bulk || !!busy} onClick={() => void run('all', () => assignAllCourses(token, cls.class_id, bulk), 'Cours attribués')}>
        {busy === 'all' ? 'Attribution…' : `Attribuer ${total - cls.assigned} cours`}</Button>
    </div>}
    {total > 0 && <button type="button" className="pt-toggle" aria-expanded={open} onClick={() => setOpen(o => !o)}>
      {open ? 'Masquer les cours' : 'Voir et modifier cours par cours'}<NavGlyph g="chevronDown" size={16}/></button>}
    {open && <ul className="pt-courses">{cls.courses.map(c => <li key={c.course_code}>
      <span>{c.label}</span>
      <select aria-label={`Enseignant — ${c.label}`} value={c.teacher?.membership_id || ''} disabled={!!busy}
        onChange={e => void run(c.course_code, () => assignCourse(token, cls.class_id, c.course_code, e.target.value || null), e.target.value ? `${c.label} attribué` : `${c.label} sans enseignant`)}>
        <option value="">— Personne —</option>{options}
      </select>
    </li>)}</ul>}
  </li>;
}

// ------------------------------------------------------------------------------------------------ teacher's own view
export function MyClassesTab({token, onOpen}: {token: string; onOpen?: (classId: string, course: string) => void}) {
  const [data, setData] = useState<MyTeaching | null>(null); const [error, setError] = useState('');
  useEffect(() => { getMyTeaching(token).then(setData).catch(e => setError(msg(e))); }, [token]);
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Vos classes sont indisponibles</b><small>{error}</small></div></div>;
  if (!data) return <Skeleton lines={5}/>;
  if (!data.classes.length && !data.titular_of.length) return <EmptyState icon="layers" title="Aucun cours attribué pour le moment"
    text="Le préfet ou le directeur des études vous attribuera vos classes et vos cours. Ils apparaîtront ici."/>;
  return <div className="pt-mine">
    {data.titular_of.length > 0 && <div className="pg-callout"><NavGlyph g="star" size={18}/><div><b>Vous êtes titulaire de {data.titular_of.map(t => t.label).join(', ')}</b>
      <small>{data.titular_of.some(t => t.effective) ? 'Vous suivrez la conduite et les bulletins de ces classes.' : 'Vous suivez ces classes au nom de la direction.'}</small></div></div>}
    <ul className="pt-mine-list">{data.classes.map(c => <li key={c.class_id}>
      <div className="pt-head"><div><b>{c.label}</b><small>{c.section_label}</small></div><span className="pc-chip pc-info">{c.courses.length} cours</span></div>
      <p className="pt-soon">Touchez un cours pour saisir ses cotes.</p>
      <div className="pt-chips pt-courses-go">{c.courses.map(k => <button type="button" key={k.course_code} onClick={() => onOpen?.(c.class_id, k.course_code)}>
        {k.label}<NavGlyph g="chevronRight" size={14}/></button>)}</div>
    </li>)}</ul>
  </div>;
}

// ------------------------------------------------------------------------------------------------ conduct scale
const slug = (label: string, taken: Set<string>) => {
  const base = label.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 24) || 'FAIT';
  let code = base; let n = 2; while (taken.has(code)) code = `${base.slice(0, 21)}_${n++}`; return code;
};

export function ConductTab({token}: {token: string}) {
  const [scale, setScale] = useState<ConductScale | null>(null);
  const [rules, setRules] = useState<ConductRule[]>([]);
  const [settings, setSettings] = useState({late_threshold: 5, late_penalty: 5, alert_below: 50});
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [newLabel, setNewLabel] = useState('');
  const reset = (s: ConductScale) => { setScale(s); setRules(s.rules.filter(r => r.active)); setSettings({late_threshold: s.settings.late_threshold, late_penalty: s.settings.late_penalty, alert_below: s.settings.alert_below}); };
  useEffect(() => { getConductScale(token).then(reset).catch(e => setError(msg(e))); }, [token]);
  const example = useMemo(() => {
    const late = rules.find(r => r.code === 'RETARD'); const grave = rules.find(r => r.grave) || rules.find(r => r.points < -5);
    if (!late || !grave) return null;
    const pts = Math.max(0, Math.min(100, 100 + 2 * late.points + grave.points));
    const m = scale?.mentions.find(x => pts >= x.from)?.code || 'MA';
    return `Exemple : 2 retards et 1 « ${grave.label.toLowerCase()} » → ${pts} points, mention ${m}.`;
  }, [rules, scale]);
  if (error && !scale) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Barème indisponible</b><small>{error}</small></div></div>;
  if (!scale) return <Skeleton lines={6}/>;
  const can = scale.can_configure;
  const edit = (i: number, patch: Partial<ConductRule>) => setRules(rs => rs.map((r, j) => j === i ? {...r, ...patch} : r));
  async function save() {
    setBusy(true); setError('');
    try { reset(await saveConductScale(token, rules, settings)); toast.success('Barème de conduite enregistré'); }
    catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }
  return <div className="pk">
    <div className="pk-how"><NavGlyph g="sparkles" size={18}/><div><b>La conduite se calcule toute seule.</b>
      <small>Chaque élève commence chaque période avec <b>{scale.start} points</b>. Chaque fait signalé retire ou rend des points ; EduSync calcule la conduite et sa mention pour le bulletin. Personne ne note la conduite à la main.</small></div></div>
    <div className="pk-mentions" aria-label="Mentions">{scale.mentions.map(m => <span key={m.code}><b>{m.code}</b>{m.from > 0 ? `${m.from} et +` : `moins de ${scale.mentions[scale.mentions.length - 2].from}`}</span>)}</div>
    {!scale.saved && can && <div className="pc-note"><NavGlyph g="info" size={16}/><span>Barème proposé par EduSync : <b>vérifiez-le</b>, adaptez les points à votre règlement, puis enregistrez.</span></div>}
    <ul className="pk-rules">{rules.map((r, i) => <li key={r.code} className={r.points > 0 ? 'pk-plus' : r.grave ? 'pk-grave' : ''}>
      <div className="pk-name">{can ? <input value={r.label} aria-label="Nom du fait" maxLength={120} onChange={e => edit(i, {label: e.target.value})}/> : <b>{r.label}</b>}
        {r.grave && <em>Fait grave : signalé par la direction, alerte immédiate</em>}</div>
      <div className="pk-points">{can ? <><button type="button" aria-label={`Moins pour ${r.label}`} onClick={() => edit(i, {points: Math.max(-50, r.points - 1 || -1)})}>−</button>
        <output aria-live="polite">{r.points > 0 ? `+${r.points}` : r.points}</output>
        <button type="button" aria-label={`Plus pour ${r.label}`} onClick={() => edit(i, {points: Math.min(20, r.points + 1 || 1)})}>+</button></>
        : <output>{r.points > 0 ? `+${r.points}` : r.points}</output>}<small>points</small></div>
      {can && <div className="pk-tools">
        <label className="pp-check"><input type="checkbox" checked={r.grave} onChange={e => edit(i, {grave: e.target.checked})}/>Grave</label>
        <button type="button" className="pp-icon pp-del" aria-label={`Retirer ${r.label}`} onClick={() => setRules(rs => rs.filter((_, j) => j !== i))}><NavGlyph g="trash" size={17}/></button>
      </div>}
    </li>)}</ul>
    {can && <form className="pk-add" onSubmit={e => { e.preventDefault(); const label = newLabel.trim(); if (label.length < 3) return;
      setRules(rs => [...rs, {code: slug(label, new Set(rs.map(x => x.code))), label, points: -2, grave: false, active: true}]); setNewLabel(''); }}>
      <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Ajouter un fait (ex. Téléphone en classe)" aria-label="Nouveau fait"/>
      <Button type="submit" icon="plus" disabled={newLabel.trim().length < 3}>Ajouter</Button></form>}
    <div className="pk-auto"><b>Règles automatiques</b>
      <p>{can ? <><input type="number" min={0} max={20} value={settings.late_threshold} aria-label="Nombre de retards" onChange={e => setSettings(s => ({...s, late_threshold: Number(e.target.value)}))}/> retards dans la période retirent encore
        <input type="number" min={0} max={50} value={settings.late_penalty} aria-label="Pénalité" onChange={e => setSettings(s => ({...s, late_penalty: Number(e.target.value)}))}/> points.</>
        : <>{settings.late_threshold} retards dans la période retirent encore {settings.late_penalty} points.</>}</p>
      <p>{can ? <>Sous <input type="number" min={0} max={100} value={settings.alert_below} aria-label="Seuil d’alerte" onChange={e => setSettings(s => ({...s, alert_below: Number(e.target.value)}))}/> points, </> : <>Sous {settings.alert_below} points, </>}
        le titulaire et le directeur de discipline sont alertés : élève à suivre.</p>
      {example && <p className="pk-example">{example}</p>}
    </div>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {can && <div className="pc-actions"><Button variant="primary" disabled={busy || !rules.length} onClick={() => void save()}>{busy ? 'Enregistrement…' : scale.saved ? 'Enregistrer les changements' : 'Enregistrer ce barème'}</Button></div>}
  </div>;
}
