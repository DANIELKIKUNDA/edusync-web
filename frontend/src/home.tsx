import React,{useEffect,useState} from 'react';
import {NavGlyph} from './platform/nav_icons';
import {ScreenBoundary,ScreenError} from './platform/screen_boundary';
import {auditActionLabel} from './platform/labels';
import {Button,Card,EmptyState,PageHeader,ProgressJourney,Section,Skeleton,StatusBadge,type JourneyStep} from './platform/ui';
import {cashCurrent,feeTrackingOverview,getAccessDashboard,getEffectifsCounts,getEffectifsMovements,getSettingsOverview,recoveryMonthly,stewardshipCounts,stewardshipDashboard,
  type AccessMe,type AccessWidget,type EffectifsCounts,type SettingsOverview} from './api';

/* School home driven by capabilities (owner decisions 9 of 2026-10-23 and the premium pass of 2026-10-24). The server
   (/access/me) lists the widgets this member may see; nothing here infers a profile. Every card is the entry point to
   its module (no « Voir » button), shows a useful figure AND the next recommended action, and loads / fails / retries
   on its own. Built with the shared UI kit (platform/ui.tsx) reused by the other school modules. */

type Props={token:string;me:AccessMe;schoolName:string;userName:string;onNavigate:(module:string)=>void;yearId?:string;yearLabel?:string};
const n=(v:number)=>new Intl.NumberFormat('fr-FR').format(v);
const money=(v:any)=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:0}).format(Number(v||0));
const ago=(v?:string|null)=>{if(!v)return '';const m=Math.round((Date.now()-new Date(v).getTime())/60000);if(m<1)return 'à l’instant';if(m<60)return `il y a ${m} min`;const h=Math.round(m/60);if(h<24)return `il y a ${h} h`;const d=Math.round(h/24);return d===1?'hier':`il y a ${d} jours`};
const plural=(k:number,one:string,many:string)=>`${n(k)} ${k>1?many:one}`;

/** Settings section opened by a readiness step (read once by the settings page). */
export const SETTINGS_TARGET_KEY='edusync.settings.open';
const READINESS_SECTION:Record<string,string>={IDENTITY:'identity',ACADEMIC_YEAR:'years',STRUCTURE:'structure',FEE_TYPES:'fees',TARIFFS:'tariffs',PAYMENT_POLICY:'payment',DOCUMENTS:'identity',ENROLLMENT_POLICY:'enrollment'};
export function readinessSteps(o:SettingsOverview,open:(section:string)=>void):JourneyStep[]{
  return o.readiness.items.filter(i=>i.state!=='NOT_APPLICABLE').map(i=>({key:i.code,label:i.label,detail:i.detail,
    status:i.state==='READY'?'done':i.state==='TO_COMPLETE'?'todo':'check',priority:i.state==='TO_COMPLETE'&&i.blocking_only_for.length>0,
    onClick:READINESS_SECTION[i.code]?()=>open(READINESS_SECTION[i.code]):undefined,actionLabel:i.state==='READY'?'Voir':'Compléter'}));
}

function useData<T>(load:()=>Promise<T>,deps:unknown[]){
  const [state,setState]=useState<{data?:T;error?:unknown;loading:boolean}>({loading:true});const [attempt,setAttempt]=useState(0);
  useEffect(()=>{let alive=true;setState(s=>({...s,loading:true,error:undefined}));load().then(data=>alive&&setState({data,loading:false})).catch(error=>alive&&setState({error,loading:false}));return()=>{alive=false}},[...deps,attempt]);
  return {...state,retry:()=>setAttempt(a=>a+1)};
}
type Loaded<T>=ReturnType<typeof useData<T>>;
function Async<T>({s,children,lines=2}:{s:Loaded<T>;children:(d:T)=>React.ReactNode;lines?:number}){
  if(s.loading&&s.data===undefined)return <Skeleton lines={lines}/>;
  if(s.error)return <ScreenError compact error={s.error} onRetry={s.retry}/>;
  return <>{children(s.data as T)}</>;
}

const ADMIN_WIDGETS=new Set(['access.members','access.requests','settings.academic_year','settings.structure','audit.recent','sync.devices']);
const ICON:Record<string,string>={'access.members':'users','access.requests':'shield','settings.academic_year':'calendar','settings.structure':'layers','audit.recent':'clock',
  'sync.devices':'sync','cash.today':'finance','checkout.quick':'receipt','headcounts.summary':'chart','headcounts.movements':'students','finance.recovery':'finance',
  'finance.by_fee':'tag','inventory.stock':'box','inventory.counts':'checkCircle'};

function AdminCard({w,d,index,go}:{w:AccessWidget;d:Loaded<Record<string,any>>;index:number;go:()=>void}){
  const x=d.data?.[w.id];const loading=d.loading&&!d.data;
  if(d.error)return <Card level="info" icon={ICON[w.id]} title={w.title} index={index}><ScreenError compact error={d.error} onRetry={d.retry}/></Card>;
  const common={icon:ICON[w.id],title:w.title,onClick:go,index,ariaLabel:`${w.title} — ouvrir`};
  if(loading)return <Card level="info" {...common}><Skeleton lines={2}/></Card>;
  switch(w.id){
    case 'access.members':{const without=x?.without_role??0;return <Card level={without?'priority':'info'} tone={without?'warn':undefined} {...common} value={n(x?.active??0)} unit="membres actifs"
      badge={without?<StatusBadge tone="warn">{plural(without,'sans rôle','sans rôle')}</StatusBadge>:<StatusBadge tone="ok">Tous ont un rôle</StatusBadge>}
      hint={without?<><b>Attribuez un rôle</b> aux {plural(without,'membre','membres')} sans accès.</>:[x?.expiring?plural(x.expiring,'droit expire sous 30 jours','droits expirent sous 30 jours'):'',x?.inactive?plural(x.inactive,'compte désactivé','comptes désactivés'):''].filter(Boolean).join(' · ')||'Aucune action requise.'}/>}
    case 'access.requests':{const p=x?.pending??0;return <Card level={p?'priority':'info'} tone={p?'warn':undefined} {...common} value={n(p)} unit={p>1?'demandes à approuver':'demande à approuver'}
      badge={p?<StatusBadge tone="warn">À traiter</StatusBadge>:undefined} hint={p?<><b>Approuvez ou refusez</b> — un second gestionnaire doit décider.</>:`${plural(x?.adjusted_roles??0,'rôle standard ajusté','rôles standards ajustés')} pour l’école.`}/>}
    case 'settings.academic_year':return x?.active?<Card level="info" tone="ok" {...common} value={x.active} badge={<StatusBadge tone="ok">En cours</StatusBadge>} hint="Année de travail de l’établissement."/>
      :<Card level="priority" tone="todo" {...common} value="Aucune" unit="année active" badge={<StatusBadge tone="todo">À compléter</StatusBadge>} hint={<><b>Préparez puis activez</b> l’année scolaire.</>}/>;
    case 'settings.structure':{const c=x?.classes??0;return <Card level={c?'info':'priority'} tone={c?undefined:'todo'} {...common} value={n(c)} unit={`classe${c>1?'s':''} · ${plural(x?.sections??0,'section','sections')}`}
      hint={c?'Classes ouvertes pour l’année active.':<><b>Ouvrez les classes</b> de l’année active.</>}/>}
    case 'sync.devices':return <Card level="secondary" {...common} hint="État des appareils, des envois en attente et des conflits de synchronisation."/>;
    case 'audit.recent':{const items:any[]=x??[];return <Card level="secondary" wide {...common}>{items.length?<ul className="ui-list">{items.slice(0,5).map((e,i)=><li key={i}><b>{auditActionLabel(e.action)}</b><small>{e.actor?`${e.actor} · `:''}{ago(e.at)}</small></li>)}</ul>
      :<EmptyState icon="clock" title="Aucune action récente" text="Les changements d’accès et de paramétrage apparaîtront ici."/>}</Card>}
    default:return null;
  }
}

function Readiness({token,open,go}:{token:string;open:(section:string)=>void;go:()=>void}){
  const s=useData(()=>getSettingsOverview(token),[token]);
  return <Card level="priority" wide title="Mise en service de l’établissement" icon="checkCircle" className="sh-readiness">
    <Async s={s} lines={4}>{o=>{const steps=readinessSteps(o,open);
      return <><ProgressJourney percent={o.readiness.percent} title={o.readiness.percent>=100?'Paramétrage complet':'Votre parcours de paramétrage'} steps={steps} max={4} showDone={!steps.some(x=>x.status==='todo'||x.status==='check')}/>
        <div className="sh-readiness-foot"><Button variant="quiet" icon="settings" onClick={go}>Tout le paramétrage</Button></div></>}}</Async>
  </Card>;
}

function BusinessCard({w,token,yearId,index,go}:{w:AccessWidget;token:string;yearId?:string;index:number;go:()=>void}){
  const common={icon:ICON[w.id],title:w.title,onClick:go,index,ariaLabel:`${w.title} — ouvrir`};
  switch(w.id){
    case 'cash.today':return <CashToday common={common} token={token}/>;
    case 'checkout.quick':return <Card level="priority" {...common} hint={<><b>Nouvel encaissement</b> : retrouvez l’élève ou la famille, puis encaissez en quelques secondes.</>}/>;
    case 'headcounts.summary':return <Headcounts common={common} token={token} yearId={yearId}/>;
    case 'headcounts.movements':return <Movements common={common} token={token} yearId={yearId}/>;
    case 'finance.recovery':return <Recovery common={common} token={token} yearId={yearId}/>;
    case 'finance.by_fee':return <ByFee common={common} token={token} yearId={yearId}/>;
    case 'inventory.stock':return <Stock common={common} token={token}/>;
    case 'inventory.counts':return <Counts common={common} token={token}/>;
    default:return null;
  }
}
type Common={icon:string;title:string;onClick:()=>void;index:number;ariaLabel:string};
function CashToday({common,token}:{common:Common;token:string}){const s=useData(()=>cashCurrent(token),[token]);
  return <Card level="priority" {...common}><Async s={s}>{d=>{const c:any=d.session;return c?<><p className="ui-card-value">{money(c.cdf?.expected_cash)}<small>CDF en caisse</small></p>
    <p className="ui-card-hint"><StatusBadge tone={c.status==='OPEN'?'ok':'neutral'}>{c.status==='OPEN'?'Ouverte':'Fermée'}</StatusBadge> Entrées {money(c.cdf?.receipts)} CDF · Solde théorique CDF</p></>
    :<p className="ui-card-hint"><b>Ouvrez votre caisse</b> pour commencer à encaisser.</p>}}</Async></Card>}
function Headcounts({common,token,yearId}:{common:Common;token:string;yearId?:string}){const s=useData<EffectifsCounts>(()=>getEffectifsCounts(token,'section','ALL',yearId),[token,yearId]);
  return <Card level="info" {...common}><Async s={s}>{c=><><p className="ui-card-value">{n(c.total.active.total)}<small>élèves actifs</small></p>
    <p className="ui-card-hint">{n(c.total.enrolled.total)} inscrits · {n(c.total.abandoned.total)} abandons · {n(c.total.transferred.total)} transferts</p></>}</Async></Card>}
function Movements({common,token,yearId}:{common:Common;token:string;yearId?:string}){const s=useData(()=>getEffectifsMovements(token,'ALL',{yearId,limit:5}),[token,yearId]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=>(d.items??[]).length?<ul className="ui-list">{d.items.map((m:any,i:number)=><li key={i}><b>{m.student_name??m.label??m.kind}</b><small>{m.kind_label??m.kind}</small></li>)}</ul>
    :<p className="ui-card-hint">Aucun mouvement récent.</p>}</Async></Card>}
function Recovery({common,token,yearId}:{common:Common;token:string;yearId?:string}){const s=useData(()=>recoveryMonthly(token,yearId,'CDF'),[token,yearId]);
  return <Card level="info" wide {...common}><Async s={s} lines={3}>{(r:any)=>r?.total?<><p className="ui-card-value">{r.total.recovery_rate}%<small>de recouvrement</small></p>
    <p className="ui-card-hint">Régularisé {money(r.total.regularized_total)} CDF sur {money(r.total.expected)} CDF · reste <b>{money(r.total.remaining)} CDF</b></p>
    {(r.items??[]).length>0&&<div className="sh-bars" aria-hidden="true">{r.items.map((x:any)=><span key={x.month_label} title={`${x.month_label} : ${x.recovery_rate}%`}><i style={{height:`${Math.max(4,Number(x.recovery_rate||0))}%`}}/><small>{String(x.month_label).slice(0,3)}</small></span>)}</div>}</>
    :<p className="ui-card-hint">Aucune donnée de recouvrement pour cette année.</p>}</Async></Card>}
function ByFee({common,token,yearId}:{common:Common;token:string;yearId?:string}){const s=useData(()=>feeTrackingOverview(token,yearId,'CDF'),[token,yearId]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=><ul className="ui-list">{(d?.items??[]).slice(0,5).map((x:any,i:number)=><li key={x.category_id??i}><b>{x.category_label??x.label}</b><small>reste {money(x.remaining)} CDF</small></li>)}</ul>}</Async></Card>}
function Stock({common,token}:{common:Common;token:string}){const s=useData(()=>stewardshipDashboard(token),[token]);
  return <Card level="info" {...common}><Async s={s}>{(d:any)=>{const low=d?.low_stock??[];return low.length?<><p className="ui-card-value">{n(low.length)}<small>article(s) sous le seuil</small></p><ul className="ui-list">{low.slice(0,3).map((x:any)=><li key={x.id}><b>{x.label}</b><small>{x.quantity} {x.unit}</small></li>)}</ul></>
    :<p className="ui-card-hint">Aucun stock sous son seuil d’alerte.</p>}}</Async></Card>}
function Counts({common,token}:{common:Common;token:string}){const s=useData(()=>stewardshipCounts(token),[token]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=>{const open=(d?.items??[]).filter((x:any)=>x.status!=='VALIDATED');return open.length?<p className="ui-card-hint"><b>{open.length} inventaire(s) en cours</b> à terminer.</p>:<p className="ui-card-hint">Aucun inventaire en cours.</p>}}</Async></Card>}

export default function HomePage({token,me,schoolName,userName,onNavigate,yearId,yearLabel}:Props){
  const needsAdmin=me.widgets.some(w=>ADMIN_WIDGETS.has(w.id));
  const admin=useData(()=>needsAdmin?getAccessDashboard(token):Promise.resolve({} as Record<string,any>),[token,needsAdmin]);
  const openSettings=(section:string)=>{try{sessionStorage.setItem(SETTINGS_TARGET_KEY,section)}catch{/* facultatif */}onNavigate('settings')};
  const search=me.actions.find(a=>a.id==='students.search');
  const shortcuts=me.actions.filter(a=>a.id!=='students.search');
  const today=new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'});
  const first=userName.split(' ')[0];
  const readiness=me.widgets.find(w=>w.id==='settings.readiness');
  const figures=me.widgets.filter(w=>w.id!=='settings.readiness'&&w.id!=='audit.recent');
  const journal=me.widgets.find(w=>w.id==='audit.recent');
  let index=0;
  const render=(w:AccessWidget)=><ScreenBoundary key={w.id} compact label={w.id}>{ADMIN_WIDGETS.has(w.id)
    ?<AdminCard w={w} d={admin} index={index++} go={()=>onNavigate(w.module)}/>
    :<BusinessCard w={w} token={token} yearId={yearId} index={index++} go={()=>onNavigate(w.module)}/>}</ScreenBoundary>;
  return <div className="ui-page sh-home">
    <PageHeader eyebrow={`${today.charAt(0).toUpperCase()}${today.slice(1)} · ${me.role_label}`} title={`Bonjour ${first}`}
      subtitle={<>{schoolName}{yearLabel?` · année ${yearLabel}`:''} — voici ce qui demande votre attention aujourd’hui.</>}
      actions={shortcuts.slice(0,3).map((a,i)=><Button key={a.id} variant={i===0?'primary':'secondary'} icon={a.id==='members.create'?'plus':a.id==='settings.open'?'settings':a.id==='checkout.new'?'receipt':'chevronRight'}
        onClick={()=>a.id==='settings.open'?openSettings('overview'):onNavigate(a.module)}>{a.label}</Button>)}/>
    {search&&<button type="button" className="sh-search" onClick={()=>onNavigate('students')}><NavGlyph g="search" size={18}/><span>{search.label}</span><small>nom, matricule ou famille</small></button>}
    {me.widgets.length===0?<EmptyState icon="home" title="Aucun suivi pour votre rôle" text="Les modules auxquels vous avez accès sont dans le menu."/>:<>
      {readiness&&<ScreenBoundary compact label="readiness"><Readiness token={token} open={openSettings} go={()=>openSettings('overview')}/></ScreenBoundary>}
      {figures.length>0&&<Section title="À suivre" id="sh-follow"><div className="ui-grid">{figures.map(render)}</div></Section>}
      {journal&&<Section title="Activité récente" id="sh-activity"><div className="ui-grid">{render(journal)}</div></Section>}
    </>}
  </div>;
}
