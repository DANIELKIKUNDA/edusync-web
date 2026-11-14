import React,{useEffect,useMemo,useState} from 'react';
import {createPortal} from 'react-dom';
import {toast} from 'sonner';
import {activateAcademicYear,createAcademicYear,createClass,createFeeType,listAcademicYears,listClasses,listFeeTypes,listOptions,listSections,listTariffs,putOption,putSection,updateSchoolIdentity,
  type FeeType,type Tariff,type AcademicYear,type ReferenceCatalog,type SchoolClass,type SchoolOption,type SchoolSection,type SettingsOverview} from './api';
import {friendlyError} from './platform/errors';
import {Button,StatusBadge} from './platform/ui';
import {NavGlyph} from './platform/nav_icons';
import {suggestNextYear} from './platform/format';
import './settings_wizards.css';
import {TariffAssistant} from './settings_tariff_assistant';
import {DateInput} from './platform/date_input';

/* Settings assistants (2026-10-24), ported from the desktop (configuration_wizard.py, settings_page.py):
   - the user never types an internal code: codes are generated from the label (autoCode) and kept unique;
   - options exist only in the Secondaire (Humanités), from the RDC catalogue of the desktop, with their tariff group;
   - classes are opened in batches, with parallels (A, B, C…) and, for the Humanités, one class per option;
   - a first-run assistant chains identity → year → sections → options → classes with existing APIs only. */

export function autoCode(label:string,taken:Iterable<string>=[],max=48):string{
  const base=(label||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toUpperCase().replace(/[^A-Z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,max)||'ITEM';
  const used=new Set([...taken].map(x=>x.toUpperCase()));if(!used.has(base))return base;
  for(let i=2;i<1000;i++){const c=`${base.slice(0,max-String(i).length-1)}_${i}`;if(!used.has(c))return c}
  return `${base.slice(0,max-9)}_${Date.now().toString(36).toUpperCase()}`;
}

/** School year code from its label: « 2027-2028 » (same shape as the platform suggestion), never typed. */
export function yearCode(label:string,taken:Iterable<string>=[]):string{const m=/(\d{4})\D+(\d{4})/.exec(label);return m?`${m[1]}-${m[2]}`:autoCode(label,taken,32)}

/** RDC study options of the Humanités (desktop STUDY_OPTIONS without « Éducation de base », which is not an option). */
export const RDC_OPTIONS:{code:string;label:string;group:'GENERAL'|'TECHNICAL'}[]=[
  {code:'HP',label:'Pédagogie générale',group:'GENERAL'},{code:'SC',label:'Scientifique',group:'GENERAL'},{code:'CG',label:'Commerciale et gestion',group:'GENERAL'},
  {code:'LITTERAIRE',label:'Littéraire',group:'GENERAL'},{code:'MATH_PHYS',label:'Math-physique',group:'GENERAL'},
  {code:'TCC',label:'Technique coupe et couture',group:'TECHNICAL'},{code:'ELEC',label:'Électricité',group:'TECHNICAL'},{code:'ELECTRONIQUE',label:'Électronique',group:'TECHNICAL'},
  {code:'MG',label:'Mécanique générale',group:'TECHNICAL'},{code:'MA',label:'Mécanique automobile',group:'TECHNICAL'},{code:'CONSTRUCTION',label:'Construction',group:'TECHNICAL'},
  {code:'NUTRITION',label:'Nutrition',group:'TECHNICAL'},
];
export const HUMANITIES=new Set(['H1','H2','H3','H4']);
/** Sigles used by the schools to name a Humanités class (owner request 2026-11-06): « 1re HP », « 2e HSC A ». The option keeps
    its full name (Pédagogie générale…); only the CLASS name is short. A school option without known sigle uses its code. */
export const CLASS_SIGLES:Record<string,string>={HP:'HP',SC:'HSC',CG:'CG',LITTERAIRE:'LIT',MATH_PHYS:'MP',TCC:'TCC',ELEC:'ELEC',ELECTRONIQUE:'ELECTRO',
  MG:'MG',MA:'MA',CONSTRUCTION:'CONSTRU',NUTRITION:'NUTRITION'};
export function optionSigle(option:{code:string;label:string}):string{
  const known=CLASS_SIGLES[option.code.toUpperCase()];if(known)return known;
  const code=option.code.toUpperCase().replace(/_\d+$/,'');if(code.length<=8)return code.replace(/_/g,'-');
  const words=option.label.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().split(/[^A-Z0-9]+/).filter(w=>w.length>2);
  return (words.length>1?words.map(w=>w[0]).join(''):(words[0]??code).slice(0,7))||code.slice(0,7);
}
/** « 1re Humanités » → « 1re » (the level ordinal used before the sigle). */
export function levelOrdinal(refLabel:string):string{return (refLabel.trim().split(/\s+/)[0])||refLabel}
/** Name of a class to open: Humanités → « 1re HP A » ; any other level → « 1re primaire A ». */
export function plannedClassLabel(ref:{code:string;label:string},option?:{code:string;label:string},suffix=''):string{
  if(option&&HUMANITIES.has(ref.code.toUpperCase()))return [levelOrdinal(ref.label),optionSigle(option),suffix].filter(Boolean).join(' ');
  return [ref.label,option?.label,suffix].filter(Boolean).join(' ');
}
export const OPTIONS_SECTION='SECONDAIRE';

/** Desktop fee presets mapped to the web periodicities (ONE_TIME, MONTHLY, PERIODIC, OPTIONAL). */
export const FEE_PRESETS:{code:string;label:string;periodicity:'ONE_TIME'|'MONTHLY'|'PERIODIC'|'OPTIONAL';regulatory?:boolean;hint:string}[]=[
  {code:'INSCRIPTION',label:'Frais d’inscription',periodicity:'ONE_TIME',hint:'Payé une fois à l’inscription'},
  {code:'REINSCRIPTION',label:'Frais de réinscription',periodicity:'ONE_TIME',hint:'Élèves déjà connus'},
  {code:'MINERVAL',label:'Frais scolaires mensuels',periodicity:'MONTHLY',hint:'Mensualités de l’année'},
  {code:'EXAMEN',label:'Frais d’examens',periodicity:'PERIODIC',hint:'Par trimestre ou période'},
  {code:'JOURNAL_CLASSE',label:'Journal de classe',periodicity:'ONE_TIME',hint:'Une fois par an'},
  {code:'ECUSSON',label:'Écusson',periodicity:'ONE_TIME',hint:'Une fois par an'},
  {code:'FRAIS_TECHNIQUES',label:'Frais techniques',periodicity:'ONE_TIME',hint:'Ateliers, laboratoires'},
  {code:'ETAT_MINERVAL',label:'Frais de l’État (3 tranches)',periodicity:'PERIODIC',regulatory:true,hint:'Frais réglementaires'},
  {code:'ETAT_EXAMEN_ETAT',label:'Examen d’État',periodicity:'ONE_TIME',regulatory:true,hint:'Finalistes'},
  {code:'ETAT_TENASOSP',label:'TENASOSP',periodicity:'ONE_TIME',regulatory:true,hint:'Test national'},
  {code:'BULLETIN',label:'Bulletin / documents scolaires',periodicity:'OPTIONAL',hint:'Selon la demande'},
];
export const CONTRIBUTION_PRESETS=[{label:'Savon',unit:'pièce',qty:1},{label:'Rame de papier',unit:'rame',qty:1},{label:'Papier hygiénique (PH)',unit:'rouleau',qty:1},{label:'Cahier',unit:'pièce',qty:1},{label:'Craie',unit:'boîte',qty:1}];
export const PRODUCT_PRESETS=[{label:'Pull scolaire'},{label:'Uniforme scolaire'},{label:'Tenue de sport'},{label:'T-shirt scolaire'},{label:'Journal de classe'}];

const LETTERS='ABCDEFGHIJ';
export type PlannedClass={key:string;section:SchoolSection;reference:{code:string;label:string};option?:SchoolOption;suffix:string;code:string;label:string};
/** Parallels are chosen PER LEVEL (owner request 2026-10-24: 1re, 2e and 3e primaire may have A and B while the other
    levels stay single). Key = reference code (« P1 »), or « H1:CG » for one Humanités option; default 1. A plain number
    applies to every level. */
export type Parallels=number|Record<string,number>;
export const MAX_PARALLELS=8;
const clampParallels=(n:number)=>Math.max(1,Math.min(MAX_PARALLELS,Math.floor(Number(n)||1)));
export function parallelCount(parallels:Parallels,ref:string,option?:string):number{
  if(typeof parallels==='number')return clampParallels(parallels);
  return clampParallels((option?parallels[`${ref}:${option}`]:undefined)??parallels[ref]??1);
}
/** Classes to open: one per reference class × option (Humanités) × parallel letter; existing codes are skipped. */
export function planClasses({sections,refs,options,picked,parallels,optionIds,existing}:{sections:SchoolSection[];refs:ReferenceCatalog;options:SchoolOption[];picked:string[];
  parallels:Parallels;optionIds:string[];existing:Set<string>}):PlannedClass[]{
  const out:PlannedClass[]=[];
  for(const code of picked){const ref=refs.classes.find(r=>r.code===code);const section=sections.find(s=>s.code===ref?.section_code);if(!ref||!section)continue;
    const opts=HUMANITIES.has(code)?options.filter(o=>optionIds.includes(o.id)):[undefined];
    for(const option of opts){const n=parallelCount(parallels,code,option?.code);const base=[ref.code,option?.code].filter(Boolean).join('_').slice(0,61).toUpperCase();
      // A level already split in A, B… is never given an extra class without letter; an existing class without letter
      // counts as the first one when parallels are added (« 4e primaire » + B, never a second « 4e primaire A »).
      const hasSuffixed=LETTERS.split('').some(l=>existing.has(`${base}_${l}`));
      const suffixes=n<=1?(hasSuffixed?[]:['']):LETTERS.slice(existing.has(base)?1:0,n).split('');
      for(const suffix of suffixes){
      const c=[ref.code,option?.code,suffix].filter(Boolean).join('_').slice(0,64);
      if(existing.has(c.toUpperCase()))continue;
      out.push({key:c,section,reference:ref,option,suffix,code:c,label:plannedClassLabel(ref,option,suffix)});
    }}}
  return out;
}

/** Humanités classes still named in full (« 1re Humanités Pédagogie générale B ») that can take the school sigle (« 1re HP B »).
    Only classes of a Humanités level with an option are proposed; the parallel letter is kept; archived classes are left alone. */
export function sigleRenames(classes:SchoolClass[],refs:{code:string;label:string}[],options:SchoolOption[]):{cls:SchoolClass;label:string}[]{
  const out:{cls:SchoolClass;label:string}[]=[];
  for(const c of classes){const refCode=(c.reference_code??'').toUpperCase();if(!HUMANITIES.has(refCode)||!c.option_id)continue;
    if((c.status??(c.enabled?'ACTIVE':'INACTIVE'))==='ARCHIVED'||c.academic_year_status==='CLOSED'||c.academic_year_status==='ARCHIVED')continue;
    const ref=refs.find(r=>r.code===refCode);const option=options.find(o=>o.id===c.option_id);if(!ref||!option)continue;
    const letter=/\s([A-J])$/.exec(c.label.trim())?.[1]??'';const label=plannedClassLabel(ref,option,letter);
    if(label!==c.label.trim())out.push({cls:c,label})}
  return out;
}

function Stepper({value,onChange,label}:{value:number;onChange:(n:number)=>void;label:string}){
  return <span className="sw-stepper" role="group" aria-label={label}>
    <button type="button" aria-label={`Une classe de moins — ${label}`} disabled={value<=1} onClick={()=>onChange(value-1)}>−</button>
    <output aria-live="polite">{value}<small>{value>1?` (${LETTERS.slice(0,value).split('').join(', ')})`:' seule'}</small></output>
    <button type="button" aria-label={`Une classe de plus — ${label}`} disabled={value>=MAX_PARALLELS} onClick={()=>onChange(value+1)}>+</button></span>;
}

/** Parallels already open for the year, per level (« P1 ») or Humanités option (« H1:CG »): the starting point of the grid. */
export function existingParallels(classes:SchoolClass[],yearId:string,options:SchoolOption[]):Record<string,number>{
  const out:Record<string,number>={};
  for(const c of classes){if(c.academic_year_id!==yearId||!c.reference_code||(c.status??(c.enabled?'ACTIVE':'INACTIVE'))==='ARCHIVED')continue;
    const ref=c.reference_code.toUpperCase();const opt=options.find(o=>o.id===c.option_id)?.code;const k=opt&&HUMANITIES.has(ref)?`${ref}:${opt}`:ref;out[k]=(out[k]??0)+1}
  return out;
}

/** One row per level: include it or not, and its own number of parallel classes (per option in the Humanités). */
export function ParallelsGrid({levels,picked,setPicked,counts,setCounts,options}:{levels:{code:string;label:string}[];picked:string[];setPicked:(p:string[])=>void;
  counts:Record<string,number>;setCounts:(c:Record<string,number>)=>void;options:SchoolOption[]}){
  const setAll=(n:number)=>{const next:Record<string,number>={};for(const l of levels){if(HUMANITIES.has(l.code))for(const o of options)next[`${l.code}:${o.code}`]=n;else next[l.code]=n}setCounts(next)};
  const put=(k:string,n:number)=>setCounts({...counts,[k]:n});
  return <div className="sw-levels">
    <div className="sw-levels-head"><span>Niveau</span><span className="sw-levels-quick">Tout mettre à <button type="button" onClick={()=>setAll(1)}>1</button><button type="button" onClick={()=>setAll(2)}>2</button></span></div>
    {levels.map(l=>{const on=picked.includes(l.code);const hum=HUMANITIES.has(l.code);
      return <div key={l.code} className={`sw-level ${on?'':'off'}`}>
        <label className="sw-level-name"><input type="checkbox" checked={on} onChange={e=>setPicked(e.target.checked?[...picked,l.code]:picked.filter(x=>x!==l.code))}/>{l.label}</label>
        {on&&(!hum?<Stepper label={l.label} value={parallelCount(counts,l.code)} onChange={n=>put(l.code,n)}/>
          :options.length?<div className="sw-level-options">{options.map(o=><div key={o.id}><span>{o.label}</span><Stepper label={`${l.label} ${o.label}`} value={parallelCount(counts,l.code,o.code)} onChange={n=>put(`${l.code}:${o.code}`,n)}/></div>)}</div>
          :<small className="sw-hint">Cochez au moins une option des Humanités.</small>)}
      </div>})}
  </div>;
}

function Modal({title,subtitle,onClose,children,footer,wide}:{title:string;subtitle?:string;onClose:()=>void;children:React.ReactNode;footer:React.ReactNode;wide?:boolean}){
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
  return createPortal(<div className="sw-backdrop" onClick={onClose}><div className={`sw-dialog ${wide?'sw-wide':''}`} role="dialog" aria-modal="true" aria-label={title} onClick={e=>e.stopPropagation()}>
    <header className="sw-head"><div><h3>{title}</h3>{subtitle&&<p>{subtitle}</p>}</div><button type="button" className="sw-close" aria-label="Fermer" onClick={onClose}><NavGlyph g="plus" size={18}/></button></header>
    <div className="sw-body">{children}</div><footer className="sw-foot">{footer}</footer></div></div>,document.body);
}

/** Humanités options from the RDC catalogue (one click) or a custom one; code and tariff group are set automatically. */
export function OptionCatalog({token,section,options,canManage,onChanged}:{token:string;section:SchoolSection;options:SchoolOption[];canManage:boolean;onChanged:()=>Promise<void>}){
  const [custom,setCustom]=useState('');const [busy,setBusy]=useState('');const [error,setError]=useState('');
  const mine=options.filter(o=>o.section_id===section.id);const byCode=new Map(mine.map(o=>[o.code,o]));
  async function add(code:string,label:string,group:string|null){try{setBusy(code);setError('');await putOption(token,{section_id:section.id,code,label,enabled:true,tariff_group_code:group});toast.success(`Option ${label} ouverte`);await onChanged()}catch(e){setError(friendlyError(e))}finally{setBusy('')}}
  async function toggle(o:SchoolOption){try{setBusy(o.code);setError('');await putOption(token,{section_id:o.section_id,code:o.code,label:o.label,enabled:!o.enabled,expected_version:o.version,tariff_group_code:o.tariff_group_code??null});toast.success(o.enabled?`Option ${o.label} fermée (les classes existantes la gardent)`:`Option ${o.label} rouverte`);await onChanged()}catch(e){setError(friendlyError(e))}finally{setBusy('')}}
  const extra=mine.filter(o=>!RDC_OPTIONS.some(r=>r.code===o.code));
  return <div className="sw-options">
    <p className="sw-hint">Les options n’existent qu’en Humanités. Cochez celles que l’école organise réellement ; le groupe tarifaire (générales / techniques) est proposé automatiquement.</p>
    {error&&<div className="error" role="alert">{error}</div>}
    {(['GENERAL','TECHNICAL'] as const).map(g=><div key={g} className="sw-option-group"><b>{g==='GENERAL'?'Humanités générales':'Humanités techniques'}</b><div className="sw-chips">
      {RDC_OPTIONS.filter(o=>o.group===g).map(o=>{const have=byCode.get(o.code);const on=!!have?.enabled;
        return <button key={o.code} type="button" className={`sw-chip ${on?'on':''}`} aria-pressed={on} disabled={!canManage||busy===o.code}
          onClick={()=>void(have?toggle(have):add(o.code,o.label,o.group))}>{on?<NavGlyph g="check" size={14}/>:<NavGlyph g="plus" size={14}/>}{o.label}</button>})}</div></div>)}
    {extra.length>0&&<div className="sw-option-group"><b>Options propres à l’école</b><div className="sw-chips">{extra.map(o=><button key={o.id} type="button" className={`sw-chip ${o.enabled?'on':''}`} aria-pressed={o.enabled} disabled={!canManage||busy===o.code} onClick={()=>void toggle(o)}>{o.enabled?<NavGlyph g="check" size={14}/>:<NavGlyph g="plus" size={14}/>}{o.label}</button>)}</div></div>}
    {canManage&&<form className="sw-inline" onSubmit={e=>{e.preventDefault();const label=custom.trim();if(label.length<2){setError('Indiquez le nom de l’option, par exemple Agronomie.');return}void add(autoCode(label,mine.map(o=>o.code)),label,'OTHER').then(()=>setCustom(''))}}>
      <input aria-label="Autre option" placeholder="Autre option (ex. Agronomie)" value={custom} onChange={e=>setCustom(e.target.value)}/><Button variant="secondary" size="sm" icon="plus" type="submit">Ajouter</Button></form>}
  </div>;
}

/** Batch opening of classes for the active / prepared year, with parallels and Humanités options. */
export function ClassBatchDialog({token,year,sections,refs,options,classes,onClose,onDone,initialSection}:{token:string;year:AcademicYear;sections:SchoolSection[];refs:ReferenceCatalog;
  options:SchoolOption[];classes:SchoolClass[];onClose:()=>void;onDone:()=>Promise<void>;initialSection?:string}){
  const enabled=sections.filter(s=>s.enabled);
  const [sectionId,setSectionId]=useState(initialSection??enabled[0]?.id??'');
  const section=enabled.find(s=>s.id===sectionId);
  const refList=refs.classes.filter(r=>r.section_code===section?.code).sort((a,b)=>a.sort_order-b.sort_order);
  const [picked,setPicked]=useState<string[]>([]);
  useEffect(()=>{setPicked(refList.map(r=>r.code))},[sectionId]);
  const [parallels,setParallels]=useState<Record<string,number>>(()=>existingParallels(classes,year.id,options));
  const secOptions=options.filter(o=>o.section_id===sectionId&&o.enabled);
  const [optionIds,setOptionIds]=useState<string[]>([]);
  useEffect(()=>{setOptionIds(secOptions.map(o=>o.id))},[sectionId,options.length]);
  const existing=useMemo(()=>new Set(classes.filter(c=>c.academic_year_id===year.id).map(c=>c.code.toUpperCase())),[classes,year.id]);
  const plan=section?planClasses({sections:enabled,refs,options,picked,parallels,optionIds,existing}):[];
  const humanities=picked.some(c=>HUMANITIES.has(c));
  const [busy,setBusy]=useState(false);const [done,setDone]=useState(0);const [error,setError]=useState('');
  async function run(){setBusy(true);setError('');setDone(0);let ok=0;
    for(const p of plan){try{await createClass(token,{academic_year_id:year.id,section_id:p.section.id,reference_code:p.reference.code,code:p.code,label:p.label,option_id:p.option?.id??null});ok++;setDone(ok)}
      catch(e){setError(`${p.label} : ${friendlyError(e)}`);break}}
    setBusy(false);if(ok){toast.success(`${ok} classe${ok>1?'s':''} ouverte${ok>1?'s':''} en ${year.label}`);await onDone()}if(ok===plan.length)onClose();
  }
  return <Modal wide title={`Ouvrir des classes — ${year.label}`} subtitle="Pour chaque niveau, choisissez son propre nombre de classes parallèles : les noms et les codes sont générés automatiquement." onClose={busy?()=>{}:onClose}
    footer={<><span className="sw-count">{plan.length?`${plan.length} classe${plan.length>1?'s':''} à créer`:'Aucune nouvelle classe'}{busy?` · ${done}/${plan.length}`:''}</span>
      <Button variant="secondary" onClick={onClose} disabled={busy}>Annuler</Button><Button variant="primary" icon="plus" disabled={busy||!plan.length||(humanities&&!optionIds.length&&secOptions.length>0)} onClick={()=>void run()}>{busy?'Création…':'Créer les classes'}</Button></>}>
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="sw-field"><span>Section</span><div className="sw-seg">{enabled.map(s=><button key={s.id} type="button" className={s.id===sectionId?'on':''} aria-pressed={s.id===sectionId} onClick={()=>setSectionId(s.id)}>{s.label}</button>)}</div></div>
    {humanities&&<div className="sw-field"><span>Options des Humanités</span>{secOptions.length?<div className="sw-chips">{secOptions.map(o=>{const on=optionIds.includes(o.id);return <button key={o.id} type="button" className={`sw-chip ${on?'on':''}`} aria-pressed={on} onClick={()=>setOptionIds(p=>on?p.filter(x=>x!==o.id):[...p,o.id])}>{on?<NavGlyph g="check" size={14}/>:<NavGlyph g="plus" size={14}/>}{o.label}</button>})}</div>
      :<p className="error">Aucune option ouverte en Secondaire : ouvrez d’abord les options (Commerciale et gestion, Scientifique…) dans la section Secondaire.</p>}</div>}
    <div className="sw-field"><span>Niveaux et classes parallèles</span>
      <ParallelsGrid levels={refList} picked={picked} setPicked={setPicked} counts={parallels} setCounts={setParallels} options={secOptions.filter(o=>optionIds.includes(o.id))}/>
      <small className="sw-hint">Exemple : 2 en 1re primaire ouvre « 1re primaire A » et « 1re primaire B » ; en Humanités, les classes prennent le sigle de l’option (« 1re HP », « 2e HSC A », « 3e MA »…) ; les autres niveaux restent à une seule classe. Les classes déjà ouvertes ne sont jamais recréées : passer de 2 à 3 ajoute seulement la classe C.</small></div>
    <div className="sw-preview"><b>Aperçu</b>{plan.length?<ul>{plan.slice(0,40).map(p=><li key={p.key}>{p.label}</li>)}{plan.length>40&&<li>… et {plan.length-40} autres</li>}</ul>:<p className="sw-hint">Toutes les classes cochées sont déjà ouvertes pour {year.label}.</p>}</div>
  </Modal>;
}

/** First-run assistant (desktop ConfigurationWizard): identity + year → sections → options → classes. Each step saves
    with the regular APIs (same permissions, same audit); tariffs, admission and policies stay in their own sections. */
export function SetupAssistant({token,overview,refs,can,onClose,onDone}:{token:string;overview:SettingsOverview|null;refs:ReferenceCatalog;can:(p:string)=>boolean;onClose:()=>void;onDone:()=>Promise<void>}){
  const school=overview?.school;
  const [step,setStep]=useState(0);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const [identity,setIdentity]=useState({name:school?.name??'',phone:school?.phone??'',email:school?.email??'',address:school?.address??'',city:school?.city??'',province:school?.province??''});
  const [years,setYears]=useState<AcademicYear[]>([]);const [sections,setSections]=useState<SchoolSection[]>([]);const [options,setOptions]=useState<SchoolOption[]>([]);const [classes,setClasses]=useState<SchoolClass[]>([]);
  const [fees,setFees]=useState<FeeType[]>([]);const [tariffs,setTariffs]=useState<Tariff[]>([]);const [tariffAssistant,setTariffAssistant]=useState(false);
  async function reload(){const [y,s,o,c,f,t]=await Promise.all([listAcademicYears(token).catch(()=>[]),listSections(token).catch(()=>[]),listOptions(token).catch(()=>[]),listClasses(token).catch(()=>[]),
    can('settings.fee_types.read')?listFeeTypes(token).catch(()=>[]):Promise.resolve([] as FeeType[]),can('settings.tariffs.read')?listTariffs(token).catch(()=>[]):Promise.resolve([] as Tariff[])]);
    setYears(y);setSections(s);setOptions(o);setClasses(c);setFees(f);setTariffs(t);return {y,s,o,c}}
  // Desktop configuration wizard « tarifs » step (settings parity pass 3): the usual fees in one click, then the tariff assistant.
  async function addFee(code:string,label:string,periodicity:FeeType['periodicity'],regulatory:boolean){try{setBusy(true);setError('');await createFeeType(token,{code,label,periodicity,default_currency:'CDF',regulatory});await reload()}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
  useEffect(()=>{void reload()},[]);
  const next=useMemo(()=>suggestNextYear(years.map(y=>y.code)),[years]);
  const active=years.find(y=>y.status==='ACTIVE')??years.find(y=>y.status==='PREPARED');
  const [year,setYear]=useState<{label:string;start:string;end:string}|null>(null);
  useEffect(()=>{if(!year&&next)setYear({label:next.label,start:next.start_date,end:next.end_date})},[next]);
  const [wantedSections,setWantedSections]=useState<string[]>([]);
  useEffect(()=>{setWantedSections(sections.filter(s=>s.enabled).map(s=>s.code))},[sections.length]);
  const [parallels,setParallels]=useState<Record<string,number>>({});
  const levels=useMemo(()=>refs.classes.filter(r=>sections.some(x=>x.enabled&&x.code===r.section_code)).sort((a,b)=>a.sort_order-b.sort_order),[refs,sections]);
  const [pickedLevels,setPickedLevels]=useState<string[]>([]);
  useEffect(()=>{setPickedLevels(levels.map(l=>l.code))},[levels.length]);
  useEffect(()=>{if(active)setParallels(p=>({...existingParallels(classes,active.id,options),...p}))},[classes.length,options.length,active?.id]);
  const steps=['École & année','Sections','Options','Classes','Frais & tarifs','Terminé'];
  async function guard(fn:()=>Promise<void>){try{setBusy(true);setError('');await fn();setStep(s=>s+1)}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
  const saveIdentityAndYear=()=>guard(async()=>{
    if(identity.name.trim().length<2)throw new Error('Indiquez le nom officiel de l’école.');
    if(can('settings.school_identity.update')&&school)await updateSchoolIdentity(token,{name:identity.name.trim(),phone:identity.phone||null,email:identity.email||null,address:identity.address||null,city:identity.city||null,province:identity.province||null,logo_url:school.logo_url??null},school.version);
    if(!active&&year&&can('settings.academic_year.create')){const created=await createAcademicYear(token,{code:yearCode(year.label,years.map(y=>y.code)),label:year.label,start_date:year.start,end_date:year.end});
      if(can('settings.academic_year.activate')&&created)try{await activateAcademicYear(token,created)}catch{/* activation optional: the year stays prepared */}}
    await reload();
  });
  const saveSections=()=>guard(async()=>{for(const r of refs.sections){const have=sections.find(s=>s.code===r.code);const want=wantedSections.includes(r.code);
    if(want&&(!have||!have.enabled))await putSection(token,{code:r.code,label:r.label,enabled:true,expected_version:have?.version??null});
    else if(!want&&have?.enabled)await putSection(token,{code:r.code,label:r.label,enabled:false,expected_version:have.version})}await reload()});
  const sec=sections.find(s=>s.code===OPTIONS_SECTION&&s.enabled);
  const openClasses=()=>guard(async()=>{const {y,s,o,c}=await reload();const yr=y.find(x=>x.status==='ACTIVE')??y.find(x=>x.status==='PREPARED');if(!yr)throw new Error('Préparez d’abord une année scolaire (étape 1).');
    const enabled=s.filter(x=>x.enabled);const picked=refs.classes.filter(r=>enabled.some(x=>x.code===r.section_code)&&pickedLevels.includes(r.code)).map(r=>r.code);
    const plan=planClasses({sections:enabled,refs,options:o,picked,parallels,optionIds:o.filter(x=>x.enabled).map(x=>x.id),existing:new Set(c.filter(x=>x.academic_year_id===yr.id).map(x=>x.code.toUpperCase()))});
    for(const p of plan)await createClass(token,{academic_year_id:yr.id,section_id:p.section.id,reference_code:p.reference.code,code:p.code,label:p.label,option_id:p.option?.id??null});
    toast.success(plan.length?`${plan.length} classe(s) ouverte(s)`:'Toutes les classes étaient déjà ouvertes');await reload()});
  const finish=async()=>{await onDone();onClose()};
  const field=(k:keyof typeof identity,label:string,type='text')=><label className="sw-input"><span>{label}</span><input type={type} value={identity[k]} onChange={e=>setIdentity(v=>({...v,[k]:e.target.value}))}/></label>;
  return <Modal wide title="Assistant de mise en service" subtitle="Configurez l’établissement dans le bon ordre. Les codes techniques sont générés pour vous." onClose={busy?()=>{}:onClose}
    footer={<>{step>0&&step<5&&<Button variant="quiet" onClick={()=>setStep(s=>s-1)} disabled={busy}>Retour</Button>}<span className="sw-count">Étape {Math.min(step+1,6)} sur 6</span>
      {step===0&&<Button variant="primary" disabled={busy} onClick={()=>void saveIdentityAndYear()}>{busy?'Enregistrement…':'Enregistrer et continuer'}</Button>}
      {step===1&&<Button variant="primary" disabled={busy||!wantedSections.length} onClick={()=>void saveSections()}>{busy?'Enregistrement…':'Enregistrer les sections'}</Button>}
      {step===2&&<Button variant="primary" onClick={()=>setStep(3)}>Continuer</Button>}
      {step===3&&<Button variant="primary" icon="plus" disabled={busy} onClick={()=>void openClasses()}>{busy?'Ouverture…':'Ouvrir les classes'}</Button>}
      {step===4&&<Button variant="primary" onClick={()=>setStep(5)}>Continuer</Button>}
      {step===5&&<Button variant="primary" onClick={()=>void finish()}>Terminer</Button>}</>}>
    <ol className="sw-steps">{steps.map((s,i)=><li key={s} className={i<step?'done':i===step?'on':''}><span>{i<step?<NavGlyph g="check" size={13}/>:i+1}</span>{s}</li>)}</ol>
    {error&&<div className="error" role="alert">{error}</div>}
    {step===0&&<div className="sw-grid">{field('name','Nom officiel *')}{field('phone','Téléphone','tel')}{field('email','E-mail','email')}{field('address','Adresse')}{field('city','Ville')}{field('province','Province')}
      <div className="sw-wide-cell">{active?<p className="sw-ok"><NavGlyph g="checkCircle" size={16}/> Année {active.label} {active.status==='ACTIVE'?'en cours':'préparée'}.</p>:year&&<div className="sw-grid">
        <label className="sw-input"><span>Année scolaire</span><input value={year.label} onChange={e=>setYear({...year,label:e.target.value})}/></label>
        <label className="sw-input"><span>Rentrée</span><DateInput value={year.start} onChange={e=>setYear({...year,start:e.target.value})}/></label>
        <label className="sw-input"><span>Fin d’année</span><DateInput value={year.end} onChange={e=>setYear({...year,end:e.target.value})}/></label></div>}</div></div>}
    {step===1&&<div className="sw-field"><span>Sections organisées par l’école</span><div className="sw-chips">{refs.sections.map(r=>{const on=wantedSections.includes(r.code);return <button key={r.code} type="button" className={`sw-chip big ${on?'on':''}`} aria-pressed={on} onClick={()=>setWantedSections(p=>on?p.filter(x=>x!==r.code):[...p,r.code])}>{on?<NavGlyph g="check" size={15}/>:<NavGlyph g="plus" size={15}/>}{r.label}</button>})}</div>
      <small className="sw-hint">Une section décochée n’efface rien : ses classes existantes restent dans l’historique.</small></div>}
    {step===2&&(sec?<OptionCatalog token={token} section={sec} options={options} canManage={can('settings.options.manage')} onChanged={async()=>{await reload()}}/>
      :<p className="sw-hint">Pas de section Secondaire : aucune option à configurer. Continuez.</p>)}
    {step===3&&<div className="sw-field"><span>Niveaux organisés et classes parallèles</span>
      <ParallelsGrid levels={levels} picked={pickedLevels} setPicked={setPickedLevels} counts={parallels} setCounts={setParallels} options={options.filter(o=>o.enabled)}/>
      <small className="sw-hint">Chaque niveau a son propre nombre de classes : par exemple 2 en 1re, 2e et 3e primaire, une seule ailleurs. Décochez un niveau que l’école n’organise pas. Les classes déjà ouvertes ne sont jamais recréées.</small></div>}
    {step===4&&<div className="sw-field"><span>Frais organisés par l’école</span>
      <div className="sw-chips">{FEE_PRESETS.map(f=>{const have=fees.some(x=>x.code===f.code);return <button key={f.code} type="button" className={`sw-chip ${have?'on':''}`} aria-pressed={have} title={f.hint}
        disabled={have||busy||!can('settings.fee_types.manage')} onClick={()=>void addFee(f.code,f.label,f.periodicity,!!f.regulatory)}>{have?<NavGlyph g="check" size={14}/>:<NavGlyph g="plus" size={14}/>}{f.label}</button>})}</div>
      <small className="sw-hint">Un clic crée le frais ; les frais propres à l’école se créent ensuite dans « Types de frais ». Puis fixez les montants : grille par niveau, frais réglementaires, aperçu de ce que chaque classe paiera.</small>
      {active&&can('settings.tariffs.manage')?<div><Button variant="secondary" icon="plus" disabled={!fees.length} onClick={()=>setTariffAssistant(true)}>Ouvrir l’assistant tarifaire</Button>{tariffs.some(t=>t.academic_year_id===active.id)&&<small className="sw-hint"> {tariffs.filter(t=>t.academic_year_id===active.id).length} règle(s) tarifaire(s) déjà enregistrée(s).</small>}</div>
        :<small className="sw-hint">Les montants se fixent dans « Tarifs & barèmes » une fois l’année préparée.</small>}
      {tariffAssistant&&active&&<TariffAssistant token={token} year={active} fees={fees} classes={classes} sections={sections} refs={refs} tariffs={tariffs} can={can} onClose={()=>setTariffAssistant(false)} onDone={async()=>{await reload()}}/>}</div>}
    {step===5&&<div className="sw-finish"><NavGlyph g="checkCircle" size={34}/><b>L’essentiel est configuré</b><p>Il reste à vérifier les conditions d’inscription, les avantages et les règles d’encaissement, puis à appliquer les barèmes aux classes : le parcours de paramétrage vous y conduit étape par étape.</p></div>}
  </Modal>;
}
