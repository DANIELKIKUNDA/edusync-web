import React,{useEffect,useState} from 'react';
import {NavGlyph} from './platform/nav_icons';
import {ScreenBoundary,ScreenError} from './platform/screen_boundary';
import {cashCurrent,feeTrackingOverview,getAccessDashboard,getEffectifsCounts,getEffectifsMovements,getSettingsOverview,recoveryMonthly,stewardshipCounts,stewardshipDashboard,
  type AccessMe,type AccessWidget,type EffectifsCounts} from './api';

/* School home driven by capabilities (owner decision 9, 2026-10-23). The server (/access/me) lists the widgets this
   member may see, each one declaring the capabilities it needs; nothing here infers a profile from a combination of
   permissions or from a role name. The page answers « what must this person watch and do today », not « what
   statistics exist ». Each card loads, fails and retries on its own: one card down never takes the page down. */

type Props={token:string;me:AccessMe;schoolName:string;userName:string;onNavigate:(module:string)=>void;yearId?:string;yearLabel?:string};
const n=(v:number)=>new Intl.NumberFormat('fr-FR').format(v);
const money=(v:any)=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:0}).format(Number(v||0));
const dateFr=(v?:string|null)=>v?new Date(v).toLocaleString('fr-FR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'';
const ACTION:Record<string,string>={ACCESS_ROLE_ASSIGNED:'Rôle attribué',ACCESS_ROLE_REVOKED:'Rôle retiré',ACCESS_ROLE_CREATED:'Rôle créé',ACCESS_ROLE_UPDATED:'Rôle modifié',
  ACCESS_ROLE_POLICY_UPDATED:'Rôle ajusté pour l’école',ACCESS_MEMBER_CREATED:'Compte créé',ACCESS_MEMBER_ATTACHED:'Compte rattaché',ACCESS_CHANGE_REQUESTED:'Demande d’approbation',
  ACCESS_CHANGE_APPROVED:'Demande approuvée',ACCESS_MEMBER_DEACTIVATED:'Membre désactivé',ACCESS_MEMBER_ACTIVATED:'Membre réactivé',ACCESS_MEMBER_CREDENTIALS_RESET:'Mot de passe réinitialisé'};

function K({label,value,sub}:{label:string;value:React.ReactNode;sub?:string}){return <div className="homeKpi"><small>{label}</small><b>{value}</b>{sub&&<span>{sub}</span>}</div>}
function Bars({rows}:{rows:Array<{label:string;value:number}>}){const max=Math.max(1,...rows.map(x=>x.value));return <div className="miniBars">{rows.map(x=><div key={x.label}><span>{x.label}</span><i><em style={{width:`${Math.max(3,x.value/max*100)}%`}}/></i><b>{x.value}%</b></div>)}</div>}

/** Loads one widget's data; its own loading / error / retry. */
function useData<T>(load:()=>Promise<T>,deps:unknown[]){
  const [state,setState]=useState<{data?:T;error?:unknown;loading:boolean}>({loading:true});const [attempt,setAttempt]=useState(0);
  useEffect(()=>{let alive=true;setState(s=>({...s,loading:true,error:undefined}));load().then(data=>alive&&setState({data,loading:false})).catch(error=>alive&&setState({error,loading:false}));return()=>{alive=false}},[...deps,attempt]);
  return {...state,retry:()=>setAttempt(a=>a+1)};
}

function Card({w,onNavigate,wide,children}:{w:AccessWidget;onNavigate:(m:string)=>void;wide?:boolean;children:React.ReactNode}){
  return <section className={`homePanel ${wide?'wide':''}`} data-widget={w.id}><div className="panelHead"><div><h3>{w.title}</h3></div>
    <button type="button" className="ghost" onClick={()=>onNavigate(w.module)}>Voir</button></div><ScreenBoundary compact label={w.id}>{children}</ScreenBoundary></section>;
}
function Body<T>({s,children}:{s:{data?:T;error?:unknown;loading:boolean;retry:()=>void};children:(d:T)=>React.ReactNode}){
  if(s.loading&&s.data===undefined)return <p className="muted">Chargement…</p>;
  if(s.error)return <ScreenError compact error={s.error} onRetry={s.retry}/>;
  return <>{children(s.data as T)}</>;
}

function AdminWidget({w,admin,onNavigate}:{w:AccessWidget;admin:ReturnType<typeof useData<Record<string,any>>>;onNavigate:(m:string)=>void}){
  return <Card w={w} onNavigate={onNavigate}><Body s={admin}>{d=>{const x=d[w.id];
    if(w.id==='access.members')return <><p className="bigFact">{n(x?.active??0)} <span>membres actifs</span></p>
      <p>{x?.without_role?<b>{n(x.without_role)} sans rôle</b>:'Tous les membres ont un rôle'}{x?.expiring?` · ${n(x.expiring)} droit(s) expirant sous 30 jours`:''}{x?.inactive?` · ${n(x.inactive)} désactivé(s)`:''}</p></>;
    if(w.id==='access.requests')return <p>{x?.pending?<b>{n(x.pending)} demande(s) à approuver</b>:'Aucune demande en attente'}{` · ${n(x?.adjusted_roles??0)} rôle(s) standard ajusté(s) pour l’école`}</p>;
    if(w.id==='settings.academic_year')return x?.active?<p className="bigFact">{x.active} <span>année en cours</span></p>:<p><b>Aucune année active</b> — préparez et activez l’année scolaire.</p>;
    if(w.id==='settings.structure')return <p className="bigFact">{n(x?.sections??0)} <span>section(s)</span> · {n(x?.classes??0)} <span>classe(s) de l’année active</span></p>;
    if(w.id==='audit.recent')return (x??[]).length?<ul className="homeList">{x.map((e:any,i:number)=><li key={i}><b>{ACTION[e.action]??e.action}</b><small>{dateFr(e.at)}{e.actor?` · ${e.actor}`:''}</small></li>)}</ul>:<p className="muted">Aucune action récente.</p>;
    return null}}</Body></Card>;
}

function Readiness({w,token,onNavigate}:{w:AccessWidget;token:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>getSettingsOverview(token),[token]);
  return <Card w={w} onNavigate={onNavigate} wide><Body s={s}>{o=>{const todo=o.readiness.items.filter(i=>i.state==='TO_COMPLETE'||i.state==='TO_CONFIRM');
    return <><p className="bigFact">{o.readiness.percent}% <span>du paramétrage</span></p>{todo.length?<ul className="homeList">{todo.slice(0,5).map(i=><li key={i.code}><b>{i.label}</b><small>{i.detail}</small></li>)}</ul>:<p>Paramétrage complet.</p>}</>}}</Body></Card>;
}
function CashToday({w,token,onNavigate}:{w:AccessWidget;token:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>cashCurrent(token),[token]);
  return <Card w={w} onNavigate={onNavigate}><Body s={s}>{d=>{const c:any=d.session;return c?<div className="homeKpis"><K label="Ma caisse" value={c.status==='OPEN'?'OUVERTE':'FERMÉE'} sub={c.business_date}/><K label="Entrées CDF" value={money(c.cdf?.receipts)}/><K label="Solde théorique CDF" value={money(c.cdf?.expected_cash)}/></div>:<p>Aucune caisse ouverte aujourd’hui.</p>}}</Body></Card>;
}
function Headcounts({w,token,yearId,onNavigate}:{w:AccessWidget;token:string;yearId?:string;onNavigate:(m:string)=>void}){
  const s=useData<EffectifsCounts>(()=>getEffectifsCounts(token,'section','ALL',yearId),[token,yearId]);
  return <Card w={w} onNavigate={onNavigate} wide><Body s={s}>{c=><><div className="homeKpis"><K label="Inscrits" value={n(c.total.enrolled.total)}/><K label="Actifs" value={n(c.total.active.total)}/><K label="Abandons" value={n(c.total.abandoned.total)}/><K label="Transferts / sorties" value={n(c.total.transferred.total)}/></div>
    <div className="compactTable"><div className="tr th"><span>Section</span><span>Inscrits</span><span>Actifs</span><span>Abandons</span></div>{c.items.map(x=><div className="tr" key={x.code}><b>{x.label}</b><span>{n(x.enrolled.total)}</span><span>{n(x.active.total)}</span><span>{n(x.abandoned.total)}</span></div>)}</div></>}</Body></Card>;
}
function Movements({w,token,yearId,onNavigate}:{w:AccessWidget;token:string;yearId?:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>getEffectifsMovements(token,'ALL',{yearId,limit:6}),[token,yearId]);
  return <Card w={w} onNavigate={onNavigate}><Body s={s}>{d=>(d.items??[]).length?<ul className="homeList">{d.items.map((m:any,i:number)=><li key={i}><b>{m.student_name??m.label??m.kind}</b><small>{m.kind_label??m.kind} · {m.occurred_on??''}</small></li>)}</ul>:<p className="muted">Aucun mouvement récent.</p>}</Body></Card>;
}
function Recovery({w,token,yearId,onNavigate}:{w:AccessWidget;token:string;yearId?:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>recoveryMonthly(token,yearId,'CDF'),[token,yearId]);
  return <Card w={w} onNavigate={onNavigate} wide><Body s={s}>{(r:any)=><>{r?.total&&<div className="homeKpis"><K label="Attendu net" value={`${money(r.total.expected)} CDF`}/><K label="Régularisé" value={`${money(r.total.regularized_total)} CDF`}/><K label="Recouvrement" value={`${r.total.recovery_rate}%`} sub={`Reste ${money(r.total.remaining)} CDF`}/></div>}
    {(r?.items??[]).length?<Bars rows={r.items.map((x:any)=>({label:x.month_label,value:Number(x.recovery_rate||0)}))}/>:<p className="muted">Aucune donnée de recouvrement pour cette année.</p>}</>}</Body></Card>;
}
function ByFee({w,token,yearId,onNavigate}:{w:AccessWidget;token:string;yearId?:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>feeTrackingOverview(token,yearId,'CDF'),[token,yearId]);
  return <Card w={w} onNavigate={onNavigate} wide><Body s={s}>{(d:any)=><div className="compactTable"><div className="tr th"><span>Famille</span><span>Attendu net</span><span>Régularisé</span><span>Reste</span></div>{(d?.items??[]).slice(0,6).map((x:any,i:number)=><div className="tr" key={x.category_id??i}><b>{x.category_label??x.label}</b><span>{money(x.net_expected)} CDF</span><span>{money(x.regularized)} CDF</span><span>{money(x.remaining)} CDF</span></div>)}</div>}</Body></Card>;
}
function Stock({w,token,onNavigate}:{w:AccessWidget;token:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>stewardshipDashboard(token),[token]);
  return <Card w={w} onNavigate={onNavigate}><Body s={s}>{(d:any)=>(d?.low_stock??[]).length?<ul className="homeList">{d.low_stock.slice(0,6).map((x:any)=><li key={x.id}><b>{x.label}</b><small>{x.quantity} {x.unit} · seuil {x.low_threshold}</small></li>)}</ul>:<p>Aucun stock sous son seuil d’alerte.</p>}</Body></Card>;
}
function Counts({w,token,onNavigate}:{w:AccessWidget;token:string;onNavigate:(m:string)=>void}){
  const s=useData(()=>stewardshipCounts(token),[token]);
  return <Card w={w} onNavigate={onNavigate}><Body s={s}>{(d:any)=>{const open=(d?.items??[]).filter((x:any)=>x.status!=='VALIDATED');return open.length?<p><b>{open.length} inventaire(s) en cours</b></p>:<p>Aucun inventaire en cours.</p>}}</Body></Card>;
}

const ADMIN_WIDGETS=new Set(['access.members','access.requests','settings.academic_year','settings.structure','audit.recent']);
export default function HomePage({token,me,schoolName,userName,onNavigate,yearId,yearLabel}:Props){
  const needsAdmin=me.widgets.some(w=>ADMIN_WIDGETS.has(w.id));
  const admin=useData(()=>needsAdmin?getAccessDashboard(token):Promise.resolve({}),[token,needsAdmin]);
  const search=me.actions.find(a=>a.id==='students.search');
  const widget=(w:AccessWidget)=>{
    if(ADMIN_WIDGETS.has(w.id))return <AdminWidget key={w.id} w={w} admin={admin} onNavigate={onNavigate}/>;
    switch(w.id){
      case 'settings.readiness':return <Readiness key={w.id} w={w} token={token} onNavigate={onNavigate}/>;
      case 'cash.today':return <CashToday key={w.id} w={w} token={token} onNavigate={onNavigate}/>;
      case 'checkout.quick':return <Card key={w.id} w={w} onNavigate={onNavigate}><p>Retrouvez l’élève ou la famille, puis encaissez en quelques secondes.</p><button type="button" className="primaryBtn compact" onClick={()=>onNavigate('finance')}>Nouvel encaissement</button></Card>;
      case 'headcounts.summary':return <Headcounts key={w.id} w={w} token={token} yearId={yearId} onNavigate={onNavigate}/>;
      case 'headcounts.movements':return <Movements key={w.id} w={w} token={token} yearId={yearId} onNavigate={onNavigate}/>;
      case 'finance.recovery':return <Recovery key={w.id} w={w} token={token} yearId={yearId} onNavigate={onNavigate}/>;
      case 'finance.by_fee':return <ByFee key={w.id} w={w} token={token} yearId={yearId} onNavigate={onNavigate}/>;
      case 'inventory.stock':return <Stock key={w.id} w={w} token={token} onNavigate={onNavigate}/>;
      case 'inventory.counts':return <Counts key={w.id} w={w} token={token} onNavigate={onNavigate}/>;
      case 'sync.devices':return <Card key={w.id} w={w} onNavigate={onNavigate}><p>État des appareils et des synchronisations de l’école.</p></Card>;
      default:return null;
    }
  };
  return <div className="homeCockpit">
    <div className="homeTop"><div><small>{me.role_label}</small><h2>{schoolName}</h2><p>{userName}{yearLabel?` · année consultée ${yearLabel}`:''} · ce que vous devez suivre aujourd’hui, selon vos droits</p></div>
      <div className="homeActions">{me.actions.filter(a=>a.id!=='students.search').slice(0,2).map(a=><button key={a.id} type="button" className="ghost" onClick={()=>onNavigate(a.module)}>{a.label}</button>)}</div></div>
    {search&&<button type="button" className="homeSearch" onClick={()=>onNavigate('students')}><NavGlyph g="search" size={17}/> {search.label} : nom, matricule ou famille…</button>}
    {me.widgets.length?<div className="homeGrid">{me.widgets.map(widget)}</div>
      :<div className="homeFuture">Votre rôle ne comporte encore aucun tableau de suivi. Les modules auxquels vous avez accès sont dans le menu.</div>}
  </div>;
}
