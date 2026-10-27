import React,{useEffect,useState} from 'react';
import {NavGlyph} from './platform/nav_icons';
import {ScreenBoundary,ScreenError} from './platform/screen_boundary';
import {RecoveryChart} from './platform/recovery_chart';
import {setFinanceTarget,type FinanceTarget} from './finance_nav';
import {auditActionLabel} from './platform/labels';
import {Button,Card,EmptyState,PageHeader,ProgressJourney,Section,Skeleton,StatusBadge,type JourneyStep} from './platform/ui';
import {listStudents,type SchoolingStudent,cashCurrent,cashJournal,cashDaySummary,checkoutProducts,financeDecisions,generatedReports,documentHistory,getSchoolingSummary,getPersonnelSummary,feeTrackingOverview,getAccessDashboard,getEffectifsCounts,getEffectifsMovements,getSettingsOverview,recoveryMonthly,stewardshipCounts,stewardshipDashboard,
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
const localIsoDay=(d=new Date())=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const frDate=(v?:string|null)=>{if(!v)return '—';const [y,m,d]=String(v).slice(0,10).split('-').map(Number);return y&&m&&d?new Date(y,m-1,d).toLocaleDateString('fr-FR'):String(v)};

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
  'sync.devices':'sync','cash.today':'finance','cash.supervision':'finance','checkout.quick':'receipt','headcounts.summary':'chart','headcounts.movements':'students','personnel.summary':'users','finance.recovery':'finance',
  'finance.by_fee':'tag','finance.decisions':'shield','reports.latest':'doc','documents.recent':'folder','inventory.stock':'box','inventory.counts':'checkCircle','cash.receipts':'receipt','enrollments.today':'students','products.watch':'cart'};

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

function BusinessCard({w,token,yearId,index,go,permissions}:{w:AccessWidget;token:string;yearId?:string;index:number;go:()=>void;permissions:string[]}){
  const common={icon:ICON[w.id],title:w.title,onClick:go,index,ariaLabel:`${w.title} — ouvrir`};
  switch(w.id){
    case 'cash.today':return <CashToday common={common} token={token}/>;
    case 'cash.supervision':return <CashSupervision common={common} token={token}/>;
    case 'checkout.quick':return <Card level="priority" {...common} hint={<><b>Nouvel encaissement</b> : retrouvez l’élève ou la famille, puis encaissez en quelques secondes.</>}/>;
    case 'cash.receipts':return <CashReceipts common={common} token={token}/>;
    case 'enrollments.today':return <Enrollments common={common} token={token}/>;
    case 'products.watch':return <ProductsWatch common={common} token={token}/>;
    case 'headcounts.summary':return <Headcounts common={common} token={token} yearId={yearId} permissions={permissions}/>;
    case 'headcounts.movements':return <Movements common={common} token={token} yearId={yearId}/>;
    case 'personnel.summary':return <PersonnelSummary common={common} token={token}/>;
    case 'finance.recovery':return <Recovery common={common} token={token} yearId={yearId}/>;
    case 'finance.by_fee':return <ByFee common={common} token={token} yearId={yearId}/>;
    case 'finance.decisions':return <FinancialDecisions common={common} token={token}/>;
    case 'reports.latest':return <LatestReports common={common} token={token}/>;
    case 'documents.recent':return <RecentDocuments common={common} token={token}/>;
    case 'inventory.stock':return <Stock common={common} token={token}/>;
    case 'inventory.counts':return <Counts common={common} token={token}/>;
    default:return null;
  }
}
type Common={icon:string;title:string;onClick:()=>void;index:number;ariaLabel:string};
function CashSupervision({common,token}:{common:Common;token:string}){const day=localIsoDay();const s=useData(()=>cashDaySummary(token,day),[token,day]);
  return <Async s={s}>{(d:any)=>{const cdf=d?.currencies?.CDF??{};const usd=d?.currencies?.USD??{};const open=Number(d?.open_count??0),closed=Number(d?.closed_count??0);
    const gaps=(d?.sessions??[]).filter((x:any)=>x.status==='CLOSED'&&[x?.cdf?.variance,x?.usd?.variance].some(v=>v!=null&&Math.abs(Number(v))>0.0001)).length;
    return <Card level={gaps?'priority':'info'} tone={gaps?'warn':undefined} {...common}
      badge={gaps?<StatusBadge tone="warn">{gaps} écart{gaps>1?'s':''} à vérifier</StatusBadge>:<StatusBadge tone="ok">Caisses suivies</StatusBadge>}>
      <p className="ui-card-value">{n(open)}<small>{open>1?'caisses ouvertes':'caisse ouverte'}</small></p>
      <p className="ui-card-hint">{n(closed)} clôturée(s) · Solde théorique global <b>{money(cdf.expected_cash)} FC</b>{Number(usd.expected_cash||0)?<> · <b>{money(usd.expected_cash)} USD</b></>:null}{gaps?<> · <b>{gaps} clôture{gaps>1?'s':''} avec écart</b></>:null}</p>
    </Card>}}</Async>;}

function CashToday({common,token}:{common:Common;token:string}){const s=useData(()=>cashCurrent(token),[token]);
  return <Card level="priority" {...common}><Async s={s}>{d=>{const c:any=d.session;return c?<><p className="ui-card-value">{money(c.cdf?.expected_cash)}<small>FC en caisse</small></p>
    <p className="ui-card-hint"><StatusBadge tone={c.status==='OPEN'?'ok':'neutral'}>{c.status==='OPEN'?'Ouverte':'Fermée'}</StatusBadge> Entrées {money(c.cdf?.receipts)} FC · Solde théorique FC</p></>
    :<p className="ui-card-hint"><b>Ouvrez votre caisse</b> pour commencer à encaisser.</p>}}</Async></Card>}
// Desk cards (each role its own home, owner 2026-10-24): what the cashier-secretary needs at the counter.
function CashReceipts({common,token}:{common:Common;token:string}){
  const s=useData(async()=>{const c=await cashCurrent(token);const session:any=c.session;if(!session)return {session:null,items:[] as any[]};const j=await cashJournal(token,session.id);return {session,items:j.items}},[token]);
  return <Card level="info" wide {...common}><Async s={s} lines={3}>{d=>{if(!d.session)return <p className="ui-card-hint"><b>Ouvrez votre caisse</b> : les encaissements du jour s’afficheront ici.</p>;
    const receipts=d.items.filter((i:any)=>i.kind==='RECEIPT');const sum=(cur:string)=>receipts.filter((i:any)=>i.currency===cur).reduce((a:number,i:any)=>a+Number(i.amount||0),0);
    return <><p className="ui-card-value">{n(receipts.length)}<small>{receipts.length>1?'reçus aujourd’hui':'reçu aujourd’hui'}</small></p>
      <p className="ui-card-hint">{money(sum('CDF'))} FC{sum('USD')?` · ${money(sum('USD'))} USD`:''} encaissés{d.items.length>receipts.length?` · ${d.items.length-receipts.length} dépense(s)`:''}</p>
      {receipts.length>0&&<ul className="ui-list">{[...receipts].reverse().slice(0,4).map((i:any,k:number)=><li key={k}><b>{i.reference}</b><small>{money(i.amount)} {i.currency==='CDF'?'FC':i.currency} · {new Date(i.created_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}</small></li>)}</ul>}</>}}</Async></Card>}
function Enrollments({common,token}:{common:Common;token:string}){const s=useData(()=>getSchoolingSummary(token),[token]);
  return <Card level="info" {...common}><Async s={s}>{(d:any)=><><p className="ui-card-value">{n(d.new_enrollments??0)}<small>{(d.new_enrollments??0)>1?'nouvelles inscriptions':'nouvelle inscription'}</small></p>
    <p className="ui-card-hint">{n(d.active_students??0)} élèves actifs{d.families_to_complete?<> · <b>{plural(d.families_to_complete,'contact à compléter','contacts à compléter')}</b></>:''}</p></>}</Async></Card>}
function ProductsWatch({common,token}:{common:Common;token:string}){const s=useData(()=>checkoutProducts(token),[token]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=>{const items:any[]=(d?.items??[]).filter((p:any)=>p.stock_tracking);
    const out=items.filter(p=>Number(p.stock_quantity||0)<=0);const low=items.filter(p=>Number(p.stock_quantity||0)>0&&Number(p.low_threshold||0)>0&&Number(p.stock_quantity)<=Number(p.low_threshold));
    return out.length||low.length?<><p className="ui-card-value">{n(out.length+low.length)}<small>article(s) à signaler</small></p><ul className="ui-list">{[...low,...out].slice(0,3).map(p=><li key={p.id}><b>{p.label}</b><small>{Number(p.stock_quantity||0)<=0?'Rupture':`Stock bas : ${Number(p.stock_quantity).toLocaleString('fr-FR')}`}</small></li>)}</ul></>
      :<p className="ui-card-hint">Tous les articles en vente sont disponibles.</p>}}</Async></Card>}
function Headcounts({common,token,yearId,permissions}:{common:Common;token:string;yearId?:string;permissions:string[]}){const group=permissions.includes('headcounts.by_section.read')?'section':permissions.includes('headcounts.by_class.read')?'class':permissions.includes('headcounts.by_option.read')?'option':null;const s=useData<EffectifsCounts|null>(()=>group?getEffectifsCounts(token,group,'ALL',yearId):Promise.resolve(null),[token,yearId,group]);
  return <Card level="info" {...common}><Async s={s}>{c=><><p className="ui-card-value">{n(c.total.active.total)}<small>élèves actifs</small></p>
    <p className="ui-card-hint">{n(c.total.enrolled.total)} inscrits · {n(c.total.abandoned.total)} abandons · {n(c.total.transferred.total)} transferts</p>
    {/* Par section (owner 2026-10-27): active pupils, girls / boys, share of the school — one hue, value printed. */}
    {c.items.length>0&&<ul className="sh-sections" aria-label="Effectifs par section">{c.items.map(r=>{const share=c.total.active.total?Math.round(r.active.total*100/c.total.active.total):0;
      return <li key={r.code||r.label}><span><b>{r.label}</b><small>{n(r.active.female)} F · {n(r.active.male)} G</small></span><i aria-hidden="true"><em style={{width:`${share}%`}}/></i><strong>{n(r.active.total)}</strong></li>})}</ul>}</>}</Async></Card>}
function PersonnelSummary({common,token}:{common:Common;token:string}){const s=useData(()=>getPersonnelSummary(token),[token]);
  return <Card level="info" {...common}><Async s={s}>{d=><><p className="ui-card-value">{n(d.active)}<small>agents actifs</small></p>
    <p className="ui-card-hint">{n(d.teachers)} enseignant(s) · {n(d.administrative)} administratif(s){d.suspended?<> · <b>{n(d.suspended)} suspendu(s)</b></>:null}</p></>}</Async></Card>}
function Movements({common,token,yearId}:{common:Common;token:string;yearId?:string}){const s=useData(()=>getEffectifsMovements(token,'ALL',{yearId,limit:5}),[token,yearId]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=>(d.items??[]).length?<ul className="ui-list">{d.items.map((m:any,i:number)=><li key={i}><b>{m.student_name??m.label??m.kind}</b><small>{m.kind_label??m.kind}</small></li>)}</ul>
    :<p className="ui-card-hint">Aucun mouvement récent.</p>}</Async></Card>}
// Real recovery chart (owner, 2026-10-24): rate and amounts per due period, aligned, one currency at a time.
function Recovery({common,token,yearId}:{common:Common;token:string;yearId?:string}){
  return <Card level="info" wide icon={common.icon} title={common.title} index={common.index}><RecoveryChart token={token} yearId={yearId} onOpen={common.onClick}/></Card>}
function ByFee({common,token,yearId}:{common:Common;token:string;yearId?:string}){const s=useData(()=>feeTrackingOverview(token,yearId,'CDF'),[token,yearId]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=><ul className="ui-list">{(d?.items??[]).slice(0,5).map((x:any,i:number)=><li key={x.category_id??i}><b>{x.category_label??x.label}</b><small>reste {money(x.remaining)} FC</small></li>)}</ul>}</Async></Card>}
function FinancialDecisions({common,token}:{common:Common;token:string}){const s=useData(()=>financeDecisions(token,'ACTIVE'),[token]);
  return <Card level="secondary" {...common}><Async s={s}>{d=>{const items=d.items??[];return <><p className="ui-card-value">{n(items.length)}<small>{items.length>1?'décisions actives':'décision active'}</small></p>
    {items.length?<ul className="ui-list">{items.slice(0,4).map(x=><li key={x.id}><b>{x.student}</b><small>{x.fee_label??'Tous frais'} · {x.decision_type}</small></li>)}</ul>
      :<p className="ui-card-hint">Aucune exonération ou réduction active à surveiller.</p>}</>}}</Async></Card>;}
function LatestReports({common,token}:{common:Common;token:string}){const s=useData(()=>generatedReports(token),[token]);
  return <Card level="secondary" {...common}><Async s={s}>{items=>{const rows=(items??[]).slice(0,4);return rows.length?<><p className="ui-card-value">{n(items.length)}<small>{items.length>1?'rapports officiels':'rapport officiel'}</small></p><ul className="ui-list">{rows.map(r=><li key={r.id}><b>{r.report_label}</b><small>{frDate(r.start_date)} · {ago(r.generated_at)}</small></li>)}</ul></>:<p className="ui-card-hint">Aucun rapport officiel généré pour le moment.</p>}}</Async></Card>;}
function RecentDocuments({common,token}:{common:Common;token:string}){const s=useData(()=>documentHistory(token,0),[token]);
  return <Card level="secondary" {...common}><Async s={s}>{d=>{const rows=(d.items??[]).slice(0,4);return rows.length?<><p className="ui-card-value">{n(d.items.length)}<small>{d.items.length>1?'documents récents':'document récent'}</small></p><ul className="ui-list">{rows.map(x=><li key={x.id}><b>{x.title}</b><small>{x.format} · {ago(x.updated_at)}</small></li>)}</ul></>:<p className="ui-card-hint">Aucun document généré pour le moment.</p>}}</Async></Card>;}
function Stock({common,token}:{common:Common;token:string}){const s=useData(()=>stewardshipDashboard(token),[token]);
  return <Card level="info" {...common}><Async s={s}>{(d:any)=>{const low=d?.low_stock??[];return low.length?<><p className="ui-card-value">{n(low.length)}<small>article(s) sous le seuil</small></p><ul className="ui-list">{low.slice(0,3).map((x:any)=><li key={x.id}><b>{x.label}</b><small>{x.quantity} {x.unit}</small></li>)}</ul></>
    :<p className="ui-card-hint">Aucun stock sous son seuil d’alerte.</p>}}</Async></Card>}
function Counts({common,token}:{common:Common;token:string}){const s=useData(()=>stewardshipCounts(token),[token]);
  return <Card level="secondary" {...common}><Async s={s}>{(d:any)=>{const open=(d?.items??[]).filter((x:any)=>x.status!=='VALIDATED');return open.length?<p className="ui-card-hint"><b>{open.length} inventaire(s) en cours</b> à terminer.</p>:<p className="ui-card-hint">Aucun inventaire en cours.</p>}}</Async></Card>}

// Home search (owner report 2026-10-25): a real search with live results, not a jump to the students tab. Choosing a
// pupil opens their file in « Élèves & inscriptions » (read once there through sessionStorage).
function StudentSpotlight({token,onClose,onPick}:{token:string;onClose:()=>void;onPick:(s:SchoolingStudent)=>void}){
  const [q,setQ]=useState('');const [hits,setHits]=useState<SchoolingStudent[]>([]);const [busy,setBusy]=useState(false);const [cur,setCur]=useState(0);const [err,setErr]=useState('');
  useEffect(()=>{const term=q.trim();if(term.length<2){setHits([]);setErr('');return}setBusy(true);
    const t=setTimeout(()=>{listStudents(token,{q:term,all_years:true,limit:8,offset:0}).then(r=>{setHits(r.items);setCur(0);setErr('')}).catch(()=>setErr('Recherche indisponible pour le moment.')).finally(()=>setBusy(false))},250);
    return()=>clearTimeout(t)},[q,token]);
  const key=(e:React.KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();onClose()}else if(e.key==='ArrowDown'){e.preventDefault();setCur(c=>Math.min(c+1,hits.length-1))}else if(e.key==='ArrowUp'){e.preventDefault();setCur(c=>Math.max(c-1,0))}else if(e.key==='Enter'&&hits[cur]){e.preventDefault();onPick(hits[cur])}};
  const term=q.trim();
  return <div className="sp-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
    <div className="sp-box" role="dialog" aria-modal="true" aria-label="Rechercher un élève">
      <label className="sp-input"><NavGlyph g="search" size={20}/><input autoFocus value={q} onChange={e=>setQ(e.target.value)} onKeyDown={key} placeholder="Nom, postnom, matricule ou famille…" aria-label="Rechercher un élève" role="combobox" aria-expanded={hits.length>0} aria-controls="sp-results"/><kbd>Échap</kbd></label>
      <div id="sp-results" role="listbox" className="sp-results">
        {term.length<2?<p className="sp-hint">Tapez au moins 2 lettres. Les élèves des années précédentes sont aussi trouvés.</p>
        :busy&&!hits.length?<p className="sp-hint">Recherche…</p>
        :err?<p className="sp-hint" role="alert">{err}</p>
        :!hits.length?<p className="sp-hint">Aucun élève ne correspond à « {term} ».</p>
        :hits.map((h,i)=><button type="button" role="option" aria-selected={i===cur} key={h.id} className={i===cur?'on':''} onMouseEnter={()=>setCur(i)} onClick={()=>onPick(h)}>
          <i>{(h.first_name?.[0]??h.last_name?.[0]??'?').toUpperCase()}</i>
          <span><b>{[h.last_name,h.middle_name,h.first_name].filter(Boolean).join(' ')}</b><small>{h.matricule??'sans matricule'} · {h.class_label??'classe non renseignée'}{h.academic_year_label?` · ${h.academic_year_label}`:''}{h.family_name?` · famille ${h.family_name}`:''}</small></span>
          <em>Ouvrir ›</em></button>)}
      </div>
      <p className="sp-foot"><span>↑ ↓ pour choisir · Entrée pour ouvrir</span></p>
    </div></div>}

export default function HomePage({token,me,schoolName,userName,onNavigate,yearId,yearLabel}:Props){
  const needsAdmin=me.widgets.some(w=>ADMIN_WIDGETS.has(w.id));
  const desk=me.widgets.some(w=>w.id==='cash.today'||w.id==='checkout.quick');
  const admin=useData(()=>needsAdmin?getAccessDashboard(token):Promise.resolve({} as Record<string,any>),[token,needsAdmin]);
  const openSettings=(section:string)=>{try{sessionStorage.setItem(SETTINGS_TARGET_KEY,section)}catch{/* facultatif */}onNavigate('settings')};
  const search=me.actions.find(a=>a.id==='students.search');
  const shortcuts=me.actions.filter(a=>a.id!=='students.search');
  const [spot,setSpot]=useState(false);
  useEffect(()=>{if(!search)return;const k=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setSpot(true)}};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[search]);
  const pick=(s:SchoolingStudent)=>{try{sessionStorage.setItem('edusync.students.open',s.id)}catch{/* facultatif */}setSpot(false);onNavigate('students')};
  const now=new Date();const today=now.toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'});const greeting=now.getHours()>=18||now.getHours()<5?'Bonsoir':'Bonjour';
  const first=userName.split(' ')[0];
  const readiness=me.widgets.find(w=>w.id==='settings.readiness');
  const figures=me.widgets.filter(w=>w.id!=='settings.readiness'&&w.id!=='audit.recent');
  const executive=figures.some(w=>w.id==='cash.supervision');
  const journal=me.widgets.find(w=>w.id==='audit.recent');
  let index=0;
  const financeTarget=(id:string):FinanceTarget|undefined=>id==='cash.today'||id==='cash.supervision'?'cash':id==='checkout.quick'?'checkout':id==='finance.recovery'?'recovery':id==='finance.by_fee'?'fees':id==='finance.decisions'?'controls':id==='reports.latest'?'reports':undefined;
  const openWidget=(w:AccessWidget)=>{const target=financeTarget(w.id);if(target)setFinanceTarget(target);onNavigate(w.module)};
  const openAction=(a:{id:string;module:string})=>{const target=a.id==='cash.supervise'?'cash':a.id==='reports.open'?'reports':a.id==='checkout.new'?'checkout':undefined;if(target)setFinanceTarget(target);onNavigate(a.module)};
  const render=(w:AccessWidget)=><ScreenBoundary key={w.id} compact label={w.id}>{ADMIN_WIDGETS.has(w.id)
    ?<AdminCard w={w} d={admin} index={index++} go={()=>openWidget(w)}/>
    :<BusinessCard w={w} token={token} yearId={yearId} permissions={me.permissions} index={index++} go={()=>openWidget(w)}/>}</ScreenBoundary>;
  return <div className={`ui-page sh-home${executive?' sh-home-executive':''}`}>
    <PageHeader eyebrow={`${today.charAt(0).toUpperCase()}${today.slice(1)} · ${me.role_label}`} title={`${greeting} ${first}`}
      subtitle={<>{schoolName}{yearLabel?` · année ${yearLabel}`:''} — {executive?'pilotage de l’établissement : caisses, effectifs, recouvrement et alertes.':desk&&!needsAdmin?'votre guichet du jour : caisse, encaissements, inscriptions.':'voici ce qui demande votre attention aujourd’hui.'}</>}
      actions={shortcuts.slice(0,3).map((a,i)=><Button key={a.id} variant={i===0?'primary':'secondary'} icon={a.id==='members.create'||a.id==='enrollments.new'?'plus':a.id==='settings.open'?'settings':a.id==='checkout.new'?'receipt':a.id==='cash.supervise'?'finance':a.id==='reports.open'?'doc':'chevronRight'}
        onClick={()=>a.id==='settings.open'?openSettings('overview'):openAction(a)}>{a.label}</Button>)}/>
    {search&&<button type="button" className="sh-search" onClick={()=>setSpot(true)} aria-haspopup="dialog"><NavGlyph g="search" size={18}/><span>{search.label}</span><small>nom, matricule ou famille · Ctrl K</small></button>}
    {spot&&<StudentSpotlight token={token} onClose={()=>setSpot(false)} onPick={pick}/>}
    {me.widgets.length===0?<EmptyState icon="home" title="Aucun suivi pour votre rôle" text="Les modules auxquels vous avez accès sont dans le menu."/>:<>
      {readiness&&<ScreenBoundary compact label="readiness"><Readiness token={token} open={openSettings} go={()=>openSettings('overview')}/></ScreenBoundary>}
      {figures.length>0&&(()=>{
        const overview=executive?figures.filter(w=>['cash.supervision','headcounts.summary','personnel.summary','finance.recovery'].includes(w.id)):figures;
        const activityIds=new Set(['reports.latest','documents.recent']);
        const activity=executive?figures.filter(w=>activityIds.has(w.id)):[];
        const watch=executive?figures.filter(w=>!['cash.supervision','headcounts.summary','personnel.summary','finance.recovery'].includes(w.id)&&!activityIds.has(w.id)):[];
        return <>{overview.length>0&&<Section title={executive?'Vue d’ensemble':'À suivre'} subtitle={executive?'Les indicateurs essentiels de l’établissement, sans actions opérationnelles.':undefined} id="sh-follow"><div className="ui-grid">{overview.map(render)}</div></Section>}
          {watch.length>0&&<Section title="À vérifier" subtitle="Les exceptions et écarts à traiter en priorité." id="sh-watch"><div className="ui-grid">{watch.map(render)}</div></Section>}
          {(activity.length>0||journal)&&<Section title="Activité récente" subtitle="Rapports, documents et actions récentes de l’établissement." id="sh-activity"><div className="ui-grid">{activity.map(render)}{journal&&render(journal)}</div></Section>}</>})()}
      {!executive&&journal&&<Section title="Activité récente" id="sh-activity"><div className="ui-grid">{render(journal)}</div></Section>}
    </>}
  </div>;
}
