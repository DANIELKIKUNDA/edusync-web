import { toast } from 'sonner';
import {ContributionRegister} from './schooling_parity_ui';
import { friendlyError, reportTechnical } from './platform/errors';
import {exportManaged,previewPdf} from './document_io';
import React,{useEffect,useMemo,useState} from 'react';
import {
  ContributionType,DepositRow,EffectifsCounts,EffectifsMovement,EffectifsOverview,EffectifsRow,EffectifsScope,
  fetchDepositsExport,fetchEffectifsExport,getDepositRegister,getEffectifsCounts,getEffectifsMovements,getEffectifsOverview,
  getStudent,listContributionTypes,listStudents,recordMaterialDeposit,SchoolingStudent
} from './api';
import './schooling_kit.css';
import './effectifs.css';

/* Effectifs & dépôts — industrialised 2026-10-25 (owner request). The certified desktop F/G/T table, scopes and tabs are
   unchanged; around them: clickable indicators, a single-hue distribution of active pupils, a row filter, live searches,
   French movement labels, deposit totals per contribution and a guided deposit dialog. */
type Props={token:string;permissions:string[];schoolName:string;yearId?:string};
type Tab='class'|'section'|'option'|'movements';
type Mode='headcounts'|'deposits';
const scopes:[EffectifsScope,string][]=[['ALL','Toute l’école'],['MATERNELLE','Maternelle'],['PRIMAIRE','Primaire'],['SECONDAIRE','Secondaire']];
const MOVE_FR:Record<EffectifsMovement['event_type'],string>={ABANDON:'Abandon',TRANSFER:'Transfert',SUSPEND:'Suspension',REINTEGRATE:'Réintégration',CLASS_CHANGE:'Changement de classe'};
const GROUP_FR:Record<Exclude<Tab,'movements'>,string>={class:'classe',section:'section',option:'filière / option'};
const nf=(v:number)=>new Intl.NumberFormat('fr-FR').format(v);
const dateFr=(d:string)=>{const t=new Date(`${d}T12:00:00`);return Number.isNaN(t.getTime())?d:t.toLocaleDateString('fr-FR',{day:'2-digit',month:'short',year:'numeric'})};

type IconName='students'|'classes'|'average'|'print'|'pdf'|'excel'|'box'|'search'|'plus'|'move'|'girl'|'close'|'check';
function Icon({name}:{name:IconName}){
 const paths={students:<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,classes:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/></>,average:<><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/></>,print:<><path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></>,pdf:<><path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6M8 15h8M8 18h6"/></>,excel:<><path d="M4 3h16v18H4zM8 8l4 8M12 8l-4 8M14 8h3M14 12h3M14 16h3"/></>,box:<><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/></>,search:<><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,plus:<><path d="M12 5v14M5 12h14"/></>,move:<><path d="M8 7h11l-3-3M19 7l-3 3M16 17H5l3-3M5 17l3 3"/></>,girl:<><circle cx="12" cy="8" r="5"/><path d="M12 13v8M9 18h6"/></>,close:<><path d="M18 6 6 18M6 6l12 12"/></>,check:<><path d="m5 12 5 5L20 7"/></>};
 return <svg className="fxIcon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}
function FgtCell({r}:{r:{female:number;male:number;total:number}}){return <><span>{r.female}</span><span>{r.male}</span><b>{r.total}</b></>}
function useDebounced<T>(v:T,ms=300){const [d,setD]=useState(v);useEffect(()=>{const t=setTimeout(()=>setD(v),ms);return()=>clearTimeout(t)},[v,ms]);return d}

export default function EffectifsPage({token,permissions,schoolName,yearId}:Props){
 const can=(p:string)=>permissions.includes(p);
 // The movements journal has its own capability (headcounts.movements.read): hidden, not refused, when absent.
 const canMoves=can('headcounts.movements.read');
 const [scope,setScope]=useState<EffectifsScope>('ALL');
 const [tab,setTab]=useState<Tab>('class');
 const [mode,setMode]=useState<Mode>('headcounts');
 const [overview,setOverview]=useState<EffectifsOverview|null>(null);
 const [counts,setCounts]=useState<EffectifsCounts|null>(null);
 const [movements,setMovements]=useState<{items:EffectifsMovement[];total:number}>({items:[],total:0});
 const [deposits,setDeposits]=useState<{items:DepositRow[];total:number}>({items:[],total:0});
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [q,setQ]=useState('');
 const [rowFilter,setRowFilter]=useState('');
 const [movementType,setMovementType]=useState('');
 const [showDeposit,setShowDeposit]=useState(false);
 const dq=useDebounced(q);
 async function refresh(){
   setBusy(true);setError('');
   try{
     const o=await getEffectifsOverview(token,scope,yearId);setOverview(o);
     if(mode==='headcounts'){
       if(tab==='movements') setMovements(await getEffectifsMovements(token,scope,{yearId,q:dq,eventType:movementType||undefined}));
       else setCounts(await getEffectifsCounts(token,tab,scope,yearId));
     }else{
       setDeposits(await getDepositRegister(token,scope,{yearId,q:dq}));
     }
   }catch(e){setError(friendlyError(e))}
   finally{setBusy(false)}
 }
 useEffect(()=>{void refresh()},[token,scope,tab,mode,yearId,dq,movementType]);
 useEffect(()=>{setRowFilter('')},[tab,scope]);
 const allRows=counts?.items??[];const total=counts?.total;
 const rows=useMemo(()=>{const f=rowFilter.trim().toLowerCase();return f?allRows.filter(r=>`${r.section} ${r.label} ${r.code}`.toLowerCase().includes(f)):allRows},[allRows,rowFilter]);
 const girlsShare=overview&&overview.active_students?Math.round(overview.active_girls*100/overview.active_students):null;
 const moves=total?total.abandoned.total+total.transferred.total:null;
 async function exportNow(kind:'pdf'|'xlsx'|'print'){try{const group=tab==='movements'?'class':tab;const blob=await fetchEffectifsExport(token,kind,group,scope,overview?.academic_year.id);const name=`effectifs_${group}.${kind==='xlsx'?'xlsx':'pdf'}`;if(kind==='print')previewPdf(blob);else await exportManaged(blob,{school:schoolName,academicYear:overview?.academic_year.label,module:'Effectifs & dépôts',category:'Effectifs',filename:name})}catch(e){setError(friendlyError(e))}}
 const go=(m:Mode,t?:Tab)=>{setMode(m);if(t)setTab(t)};
 return <div className="effectifsPage">
  <div className="fxHero"><div><div className="eyebrow">SCOLARITÉ</div><h2>Effectifs & dépôts</h2><p>Lecture annuelle certifiée F/G/T, mouvements et registre des contributions matérielles{overview?` · ${overview.academic_year.label}`:''}.</p></div><div className="fxMode" role="tablist"><button role="tab" aria-selected={mode==='headcounts'} className={mode==='headcounts'?'active':''} onClick={()=>setMode('headcounts')}><Icon name="students"/>Effectifs</button><button role="tab" aria-selected={mode==='deposits'} className={mode==='deposits'?'active':''} onClick={()=>setMode('deposits')}><Icon name="box"/>Dépôts matériels</button></div></div>
  <div className="fxScope" role="group" aria-label="Périmètre">{scopes.map(([v,l])=><button key={v} aria-pressed={scope===v} className={scope===v?'active':''} onClick={()=>setScope(v)}>{l}</button>)}</div>
  {error&&<div className="error" role="alert">{error}</div>}
  <div className="fxKpis fx2Kpis">
   <button type="button" onClick={()=>go('headcounts','class')}><i><Icon name="students"/></i><div><b>{overview?nf(overview.active_students):'—'}</b><span>Élèves actifs</span><small>{overview?`${nf(overview.active_girls)} filles • ${nf(overview.active_boys)} garçons`:'Chargement…'}</small></div></button>
   <button type="button" onClick={()=>go('headcounts','class')}><i><Icon name="classes"/></i><div><b>{overview?nf(overview.active_classes):'—'}</b><span>Classes actives</span><small>{overview?.academic_year.label??'Année active'}</small></div></button>
   <button type="button" onClick={()=>go('headcounts','section')}><i><Icon name="average"/></i><div><b>{overview?.average_per_class??'—'}</b><span>Moyenne</span><small>élèves / classe · voir par section</small></div></button>
   <button type="button" onClick={()=>go('headcounts','class')}><i><Icon name="girl"/></i><div><b>{girlsShare===null?'—':`${girlsShare} %`}</b><span>Part des filles</span><small>parmi les élèves actifs</small></div></button>
   <button type="button" onClick={()=>go('headcounts',canMoves?'movements':'class')}><i><Icon name="move"/></i><div><b>{moves===null?'—':nf(moves)}</b><span>Abandons & transferts</span><small>{moves===null?'ouvrez un tableau d’effectifs':canMoves?'voir les mouvements':'colonnes du tableau par classe'}</small></div></button>
   <button type="button" onClick={()=>go('deposits')}><i><Icon name="box"/></i><div><b>{mode==='deposits'?nf(deposits.total):'›'}</b><span>Dépôts matériels</span><small>registre exigé / déposé / reste</small></div></button>
  </div>
  {mode==='headcounts'?<section className="fxPanel">
   <div className="fxPanelTop"><div className="fxTabs" role="tablist"><button role="tab" aria-selected={tab==='class'} className={tab==='class'?'active':''} onClick={()=>setTab('class')}>Par classe</button><button role="tab" aria-selected={tab==='section'} className={tab==='section'?'active':''} onClick={()=>setTab('section')}>Par section</button><button role="tab" aria-selected={tab==='option'} className={tab==='option'?'active':''} onClick={()=>setTab('option')}>Par filière / option</button>{canMoves&&<button role="tab" aria-selected={tab==='movements'} className={tab==='movements'?'active':''} onClick={()=>setTab('movements')}>Mouvements</button>}</div><div className="fxActions">{tab!=='movements'&&can('headcounts.export')&&<button onClick={()=>void exportNow('print')}><Icon name="print"/>Imprimer</button>}{tab!=='movements'&&can('headcounts.export')&&<button onClick={()=>void exportNow('pdf')}><Icon name="pdf"/>PDF</button>}{tab!=='movements'&&can('headcounts.export')&&<button onClick={()=>void exportNow('xlsx')}><Icon name="excel"/>Excel</button>}</div></div>
   {tab!=='movements'?<>
    {allRows.length>0&&<Distribution rows={allRows} group={GROUP_FR[tab]} onPick={l=>setRowFilter(l)}/>}
    <div className="fx2Bar"><label className="fx2Search"><Icon name="search"/><input value={rowFilter} onChange={e=>setRowFilter(e.target.value)} placeholder={`Filtrer par ${GROUP_FR[tab]} ou section…`} aria-label="Filtrer le tableau"/>{rowFilter&&<button type="button" aria-label="Effacer le filtre" onClick={()=>setRowFilter('')}><Icon name="close"/></button>}</label><small>{rows.length} ligne(s){rowFilter?` sur ${allRows.length}`:''}</small></div>
    <div className="fxTableWrap"><div className="fxTable" role="table"><div className="fxGroupRow"><span className="fxDouble">Section</span><span className="fxDouble">{tab==='class'?'Classe':tab==='section'?'Section':'Filière / option'}</span><span className="fxTriple">Inscrits</span><span className="fxTriple">Abandons</span><span className="fxTriple">Transférés</span><span className="fxTriple">Élèves actifs</span></div><div className="fxSubRow"><span/><span/><span>F</span><span>G</span><span>T</span><span>F</span><span>G</span><span>T</span><span>F</span><span>G</span><span>T</span><span>F</span><span>G</span><span>T</span></div>
     {busy&&!allRows.length?[0,1,2,3].map(i=><div className="fxDataRow fx2Skel" key={i}><i/><i/></div>)
      :rows.map((r:EffectifsRow)=><div className={`fxDataRow${r.abandoned.total+r.transferred.total>0?' fx2HasMoves':''}`} key={`${r.section}-${r.code}`}><span>{r.section}</span><strong>{r.label}</strong><FgtCell r={r.enrolled}/><FgtCell r={r.abandoned}/><FgtCell r={r.transferred}/><FgtCell r={r.active}/></div>)}
     {total&&!rowFilter&&<div className="fxDataRow total"><span/><strong>Total général</strong><FgtCell r={total.enrolled}/><FgtCell r={total.abandoned}/><FgtCell r={total.transferred}/><FgtCell r={total.active}/></div>}
     {!busy&&rows.length===0&&<div className="fxEmpty">{rowFilter?`Aucune ligne ne correspond à « ${rowFilter} ».`:'Aucun effectif dans ce périmètre pour l’année consultée.'}</div>}</div></div>
   </>:<MovementsView items={movements.items} total={movements.total} busy={busy} q={q} setQ={setQ} type={movementType} setType={setMovementType}/>}
  </section>:<DepositsView token={token} scope={scope} deposits={deposits} busy={busy} can={can} q={q} setQ={setQ} refresh={refresh} show={showDeposit} setShow={setShowDeposit} yearId={overview?.academic_year.id} schoolName={schoolName}/>}
 </div>
}

/** Active pupils per row, one hue, sorted; the value is printed, the F/G split is in the hover/focus tip; a click filters the table. */
function Distribution({rows,group,onPick}:{rows:EffectifsRow[];group:string;onPick:(label:string)=>void}){
 const [all,setAll]=useState(false);const [tip,setTip]=useState<string|null>(null);
 const sorted=[...rows].sort((a,b)=>b.active.total-a.active.total);const shown=all?sorted:sorted.slice(0,8);
 const max=Math.max(1,...rows.map(r=>r.active.total));
 return <figure className="fx2Dist"><figcaption><b>Élèves actifs par {group}</b><span className="fx2Key"><i/>Élèves actifs</span></figcaption>
  <div className="fx2Bars">{shown.map(r=>{const k=`${r.section}-${r.code}`;return <button type="button" key={k} className="fx2BarRow" onMouseEnter={()=>setTip(k)} onMouseLeave={()=>setTip(null)} onFocus={()=>setTip(k)} onBlur={()=>setTip(null)} onClick={()=>onPick(r.label)} aria-label={`${r.label} : ${r.active.total} élèves actifs, ${r.active.female} filles, ${r.active.male} garçons. Filtrer le tableau.`}>
   <span className="fx2Label">{r.label}<small>{r.section}</small></span>
   <span className="fx2Track"><i style={{width:`${Math.max(r.active.total?2:0,r.active.total*100/max)}%`}}/></span>
   <b>{nf(r.active.total)}</b>
   {tip===k&&<span className="fx2Tip" role="tooltip"><b>{r.label}</b><span>Filles <em>{r.active.female}</em></span><span>Garçons <em>{r.active.male}</em></span><span>Inscrits <em>{r.enrolled.total}</em></span>{r.abandoned.total+r.transferred.total>0&&<span>Abandons / transferts <em>{r.abandoned.total} / {r.transferred.total}</em></span>}</span>}
  </button>})}</div>
  {sorted.length>8&&<button type="button" className="fx2More" onClick={()=>setAll(!all)}>{all?'Réduire':`Voir les ${sorted.length} lignes`}</button>}
 </figure>}

function MovementsView({items,total,busy,q,setQ,type,setType}:{items:EffectifsMovement[];total:number;busy:boolean;q:string;setQ:(x:string)=>void;type:string;setType:(x:string)=>void}){
 const types:[string,string][]=[['','Tous'],['ABANDON','Abandons'],['TRANSFER','Transferts'],['REINTEGRATE','Réintégrations'],['CLASS_CHANGE','Changements de classe'],['SUSPEND','Suspensions']];
 return <div className="fx2Stack"><div className="fx2Bar"><label className="fx2Search"><Icon name="search"/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Élève, matricule, motif…" aria-label="Rechercher un mouvement"/></label><small>{busy?'Recherche…':`${nf(total)} mouvement(s)`}</small></div>
  <div className="fx2Chips" role="group" aria-label="Type de mouvement">{types.map(([v,l])=><button type="button" key={v} aria-pressed={type===v} className={type===v?'on':''} onClick={()=>setType(v)}>{l}</button>)}</div>
  <div className="fxMoveTable"><div className="fxMoveRow head"><span>Date</span><span>Élève</span><span>Classe</span><span>Type</span><span>Motif / destination</span></div>
   {items.map(m=><div className="fxMoveRow" key={m.id}><span>{dateFr(m.effective_date)}</span><span><b>{m.student_name}</b><small>{m.matricule}</small></span><span>{m.class_label}<small>{m.section_label}</small></span><span><em className={`movement ${m.event_type.toLowerCase()}`}>{MOVE_FR[m.event_type]??m.event_type}</em></span><span>{m.reason}<small>{m.destination||''}</small></span></div>)}
   {!busy&&items.length===0&&<div className="fxEmpty">{q||type?'Aucun mouvement ne correspond à ces critères.':'Aucun mouvement enregistré dans ce périmètre pour l’année consultée.'}</div>}</div></div>}

function DepositsView({token,scope,deposits,busy,can,q,setQ,refresh,show,setShow,yearId,schoolName}:{token:string;scope:EffectifsScope;deposits:{items:DepositRow[];total:number};busy:boolean;can:(p:string)=>boolean;q:string;setQ:(x:string)=>void;refresh:()=>Promise<void>;show:boolean;setShow:(v:boolean)=>void;yearId?:string;schoolName:string}){
 async function exportX(){try{await exportManaged(await fetchDepositsExport(token,scope,yearId),{school:schoolName,module:'Effectifs & dépôts',category:'Dépôts matériels',filename:'registre_depots_materiels.xlsx'})}catch(e){reportTechnical(e,'export dépôts');toast.error(friendlyError(e))}}
 // Totals of the rows shown, per contribution and unit (never mixes units).
 const totals=useMemo(()=>{const m=new Map<string,{label:string;unit:string;qty:number;n:number}>();for(const d of deposits.items){const k=`${d.contribution_label}|${d.unit}`;const c=m.get(k)??{label:d.contribution_label,unit:d.unit,qty:0,n:0};c.qty+=Number(d.quantity)||0;c.n++;m.set(k,c)}return [...m.values()].sort((a,b)=>b.n-a.n)},[deposits.items]);
 return <section className="fxPanel"><div className="fxPanelTop"><div><h3>Registre des dépôts matériels</h3><p>Le périmètre sélectionné s’applique exactement comme aux effectifs. Chaque dépôt est une ligne ajoutée, jamais modifiée.</p></div><div className="fxActions">{can('contributions.record')&&<button className="primary" onClick={()=>setShow(true)}><Icon name="plus"/>Enregistrer un dépôt</button>}{can('contributions.register.export_xlsx')&&<button onClick={()=>void exportX()}><Icon name="excel"/>Excel</button>}</div></div>
  {totals.length>0&&<div className="fx2Totals" aria-label="Totaux par contribution">{totals.slice(0,6).map(t=><div key={`${t.label}|${t.unit}`}><b>{nf(Math.round(t.qty*1000)/1000)} <small>{t.unit}</small></b><span>{t.label}</span><small>{t.n} dépôt(s) affiché(s)</small></div>)}</div>}
  <div className="fx2Bar"><label className="fx2Search"><Icon name="search"/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Élève, matricule, contribution…" aria-label="Rechercher un dépôt"/></label><small>{busy?'Recherche…':`${nf(deposits.total)} dépôt(s)`}</small></div>
  <div className="fxDepositTable"><div className="fxDepositRow head"><span>Date</span><span>Élève</span><span>Classe</span><span>Contribution</span><span>Quantité</span><span>Agent</span></div>{deposits.items.map(d=><div className="fxDepositRow" key={d.id}><span>{dateFr(d.deposited_on)}</span><span><b>{d.student_name}</b><small>{d.matricule}</small></span><span>{d.class_label}<small>{d.section_label}</small></span><span>{d.contribution_label}{d.notes&&<small>{d.notes}</small>}</span><span><b>{d.quantity}</b> {d.unit}</span><span>{d.recorded_by_name}</span></div>)}{!busy&&deposits.items.length===0&&<div className="fxEmpty">{q?`Aucun dépôt ne correspond à « ${q} ».`:'Aucun dépôt matériel dans ce périmètre.'}</div>}</div>
  {can('contributions.register.read')&&<><h3>Registre exigé / déposé / reste</h3><ContributionRegister token={token}/></>}
  {show&&<DepositDialog token={token} scope={scope} yearId={yearId} onClose={()=>setShow(false)} onSaved={async()=>{setShow(false);toast.success('Dépôt enregistré dans le registre.');await refresh()}}/>}</section>}

function DepositDialog({token,scope,yearId,onClose,onSaved}:{token:string;scope:EffectifsScope;yearId?:string;onClose:()=>void;onSaved:()=>Promise<void>}){
 const [search,setSearch]=useState('');const [students,setStudents]=useState<SchoolingStudent[]>([]);const [selected,setSelected]=useState<SchoolingStudent|null>(null);const [types,setTypes]=useState<ContributionType[]>([]);const [typeId,setTypeId]=useState('');const [qty,setQty]=useState('1');const [notes,setNotes]=useState('');const [error,setError]=useState('');const [saving,setSaving]=useState(false);const [looking,setLooking]=useState(false);
 const ds=useDebounced(search,280);
 useEffect(()=>{void listContributionTypes(token).then(setTypes).catch(e=>setError(friendlyError(e)))},[token]);
 useEffect(()=>{const t=ds.trim();if(t.length<2){setStudents([]);return}setLooking(true);listStudents(token,{q:t,limit:8}).then(r=>setStudents(r.items)).catch(e=>setError(friendlyError(e))).finally(()=>setLooking(false))},[ds,token]);
 useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
 const type=types.find(t=>t.id===typeId);const n=Number(qty);const ok=!!selected&&!!typeId&&n>0&&!!yearId;
 async function save(){if(!ok||saving)return;setSaving(true);setError('');try{const full=await getStudent(token,selected!.id);const enrollment=(full.enrollments||[]).find(e=>e.academic_year_id===yearId&&e.status!=='CANCELLED');if(!enrollment)throw new Error('Cet élève n’a pas d’inscription active dans l’année consultée');await recordMaterialDeposit(token,{enrollment_id:enrollment.id,contribution_type_id:typeId,quantity:n,notes,scope});await onSaved()}catch(e){setError(friendlyError(e))}finally{setSaving(false)}}
 return <div className="kp-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><div className="kp-dialog fx2Dialog" role="dialog" aria-modal="true" aria-labelledby="fx2-dep-title">
  <header className="kp-dhead"><span className="kp-dicon"><Icon name="box"/></span><div><h3 id="fx2-dep-title">Nouveau dépôt matériel</h3><p>Une ligne est ajoutée au registre. L’historique n’est jamais écrasé.</p></div><button type="button" className="kp-close" aria-label="Fermer" onClick={onClose}><Icon name="close"/></button></header>
  <div className="kp-dbody">
   {error&&<div className="kp-warn" role="alert">{error}</div>}
   <section><h4><span>1</span>Élève {selected&&<small>✓ choisi</small>}</h4>
    {selected?<div className="kp-pupil"><i>{(selected.last_name?.[0]??'')+(selected.first_name?.[0]??'')}</i><div><b>{[selected.last_name,selected.middle_name,selected.first_name].filter(Boolean).join(' ')}</b><small>{selected.matricule} · {selected.class_label||'classe non renseignée'}</small></div><button type="button" className="kp-link" onClick={()=>setSelected(null)}>Changer</button></div>
    :<><label className="kp-searchBig"><Icon name="search"/><input autoFocus value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nom, postnom ou matricule…" aria-label="Rechercher l’élève"/></label>
     <div className="kp-hits">{search.trim().length<2?<p className="kp-empty">Tapez au moins 2 lettres.</p>:looking&&!students.length?<p className="kp-empty">Recherche…</p>:!students.length?<p className="kp-empty">Aucun élève trouvé.</p>
      :students.map(s=><button type="button" className="kp-hit" key={s.id} onClick={()=>setSelected(s)}><i>{(s.last_name?.[0]??'')+(s.first_name?.[0]??'')}</i><span><b>{[s.last_name,s.middle_name,s.first_name].filter(Boolean).join(' ')}</b><small>{s.matricule} · {s.class_label||'classe'}</small></span><em className="kp-link">Choisir ›</em></button>)}</div></>}
   </section>
   <section><h4><span>2</span>Contribution</h4>
    {types.length?<div className="fx2Chips">{types.map(t=><button type="button" key={t.id} aria-pressed={typeId===t.id} className={typeId===t.id?'on':''} onClick={()=>setTypeId(t.id)}>{t.label} <small>({t.unit})</small></button>)}</div>:<p className="kp-empty">Aucune contribution matérielle n’est paramétrée.</p>}
   </section>
   <section><h4><span>3</span>Quantité et observation</h4>
    <div className="fx2Qty"><button type="button" aria-label="Diminuer" onClick={()=>setQty(String(Math.max(1,Math.floor((Number(qty)||1)-1))))}>−</button><input type="number" min="0.001" step="0.001" value={qty} onChange={e=>setQty(e.target.value)} aria-label="Quantité"/><button type="button" aria-label="Augmenter" onClick={()=>setQty(String(Math.floor((Number(qty)||0)+1)))}>+</button><span>{type?.unit??''}</span></div>
    <label className="fx2Note"><span>Observation</span><input value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Facultatif"/></label>
   </section>
  </div>
  <footer className="kp-dfoot"><span className="kp-summary">{ok?<>Dépôt de <b>{qty} {type?.unit}</b> · {type?.label} pour <b>{selected?.last_name} {selected?.first_name}</b></>:!yearId?'Année scolaire non chargée.':'Choisissez l’élève, la contribution et la quantité.'}</span><button type="button" className="kp-btn ghost" onClick={onClose}>Annuler</button><button type="button" className="kp-btn primary" disabled={!ok||saving} onClick={()=>void save()}><Icon name="check"/>{saving?'Enregistrement…':'Enregistrer le dépôt'}</button></footer>
 </div></div>}
