import { toast } from 'sonner';
import { friendlyError, reportTechnical } from './platform/errors';
import {exportManaged,previewPdf} from './document_io';
import React,{useEffect,useState} from 'react';
import {
  ContributionType,DepositRow,EffectifsCounts,EffectifsMovement,EffectifsOverview,EffectifsRow,EffectifsScope,
  fetchDepositsExport,fetchEffectifsExport,getDepositRegister,getEffectifsCounts,getEffectifsMovements,getEffectifsOverview,
  getStudent,listContributionTypes,listStudents,recordMaterialDeposit,SchoolingStudent
} from './api';

type Props={token:string;permissions:string[];schoolName:string;yearId?:string};
type Tab='class'|'section'|'option'|'movements';
type Mode='headcounts'|'deposits';
const scopes:[EffectifsScope,string][]=[['ALL','Toute l’école'],['MATERNELLE','Maternelle'],['PRIMAIRE','Primaire'],['SECONDAIRE','Secondaire']];

function Icon({name}:{name:'students'|'classes'|'average'|'print'|'pdf'|'excel'|'box'|'search'|'plus'|'move'}){
 const paths={students:<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,classes:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/></>,average:<><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/></>,print:<><path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></>,pdf:<><path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6M8 15h8M8 18h6"/></>,excel:<><path d="M4 3h16v18H4zM8 8l4 8M12 8l-4 8M14 8h3M14 12h3M14 16h3"/></>,box:<><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/></>,search:<><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,plus:<><path d="M12 5v14M5 12h14"/></>,move:<><path d="M8 7h11l-3-3M19 7l-3 3M16 17H5l3-3M5 17l3 3"/></>};
 return <svg className="fxIcon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}
function download(blob:Blob,name:string,print=false){if(print){previewPdf(blob);return}void exportManaged(blob,{school:'EduSync École',module:'Effectifs & dépôts',category:'Exports',filename:name})}
function FgtCell({r}:{r:{female:number;male:number;total:number}}){return <><span>{r.female}</span><span>{r.male}</span><b>{r.total}</b></>}

export default function EffectifsPage({token,permissions,schoolName,yearId}:Props){
 const can=(p:string)=>permissions.includes(p);
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
 const [movementType,setMovementType]=useState('');
 const [showDeposit,setShowDeposit]=useState(false);
 async function refresh(){
   setBusy(true);setError('');
   try{
     const o=await getEffectifsOverview(token,scope,yearId);setOverview(o);
     if(mode==='headcounts'){
       if(tab==='movements') setMovements(await getEffectifsMovements(token,scope,{yearId,q,eventType:movementType||undefined}));
       else setCounts(await getEffectifsCounts(token,tab,scope,yearId));
     }else{
       setDeposits(await getDepositRegister(token,scope,{yearId,q}));
     }
   }catch(e){setError(friendlyError(e))}
   finally{setBusy(false)}
 }
 useEffect(()=>{void refresh()},[token,scope,tab,mode,yearId]);
 const rows=counts?.items??[];const total=counts?.total;
 async function exportNow(kind:'pdf'|'xlsx'|'print'){try{const group=tab==='movements'?'class':tab;const blob=await fetchEffectifsExport(token,kind,group,scope,overview?.academic_year.id);const name=`effectifs_${group}.${kind==='xlsx'?'xlsx':'pdf'}`;if(kind==='print')previewPdf(blob);else await exportManaged(blob,{school:schoolName,academicYear:overview?.academic_year.label,module:'Effectifs & dépôts',category:'Effectifs',filename:name})}catch(e){setError(friendlyError(e))}}
 return <div className="effectifsPage">
  <div className="fxHero"><div><div className="eyebrow">SCOLARITÉ</div><h2>Effectifs & dépôts</h2><p>Lecture annuelle certifiée F/G/T, mouvements et registre des contributions matérielles.</p></div><div className="fxMode"><button className={mode==='headcounts'?'active':''} onClick={()=>setMode('headcounts')}>Effectifs</button><button className={mode==='deposits'?'active':''} onClick={()=>setMode('deposits')}>Dépôts matériels</button></div></div>
  <div className="fxScope" aria-label="Périmètre">{scopes.map(([v,l])=><button key={v} className={scope===v?'active':''} onClick={()=>setScope(v)}>{l}</button>)}</div>
  {error&&<div className="error">{error}</div>}
  <div className="fxKpis">
   <article><i><Icon name="students"/></i><div><b>{overview?.active_students??'—'}</b><span>Élèves actifs</span><small>{overview?`${overview.active_girls} filles • ${overview.active_boys} garçons`:'Chargement…'}</small></div></article>
   <article><i><Icon name="classes"/></i><div><b>{overview?.active_classes??'—'}</b><span>Classes actives</span><small>{overview?.academic_year.label??'Année active'}</small></div></article>
   <article><i><Icon name="average"/></i><div><b>{overview?.average_per_class??'—'}</b><span>Moyenne</span><small>élèves / classe</small></div></article>
  </div>
  {mode==='headcounts'?<section className="fxPanel">
   <div className="fxPanelTop"><div className="fxTabs"><button className={tab==='class'?'active':''} onClick={()=>setTab('class')}>Par classe</button><button className={tab==='section'?'active':''} onClick={()=>setTab('section')}>Par section</button><button className={tab==='option'?'active':''} onClick={()=>setTab('option')}>Par filière / option</button><button className={tab==='movements'?'active':''} onClick={()=>setTab('movements')}>Mouvements</button></div><div className="fxActions">{tab!=='movements'&&can('headcounts.print')&&<button onClick={()=>void exportNow('print')}><Icon name="print"/>Imprimer</button>}{tab!=='movements'&&can('headcounts.export_pdf')&&<button onClick={()=>void exportNow('pdf')}><Icon name="pdf"/>PDF</button>}{tab!=='movements'&&can('headcounts.export_xlsx')&&<button onClick={()=>void exportNow('xlsx')}><Icon name="excel"/>Excel</button>}</div></div>
   {tab!=='movements'?<div className="fxTableWrap"><div className="fxTable" role="table"><div className="fxGroupRow"><span className="fxDouble">Section</span><span className="fxDouble">{tab==='class'?'Classe':tab==='section'?'Section':'Filière / option'}</span><span className="fxTriple">Inscrits</span><span className="fxTriple">Abandons</span><span className="fxTriple">Transférés</span><span className="fxTriple">Élèves actifs</span></div><div className="fxSubRow"><span/><span/><span>F</span><span>G</span><span>T</span><span>F</span><span>G</span><span>T</span><span>F</span><span>G</span><span>T</span><span>F</span><span>G</span><span>T</span></div>{rows.map((r:EffectifsRow)=><div className="fxDataRow" key={`${r.section}-${r.code}`}><span>{r.section}</span><strong>{r.label}</strong><FgtCell r={r.enrolled}/><FgtCell r={r.abandoned}/><FgtCell r={r.transferred}/><FgtCell r={r.active}/></div>)}{total&&<div className="fxDataRow total"><span/><strong>Total général</strong><FgtCell r={total.enrolled}/><FgtCell r={total.abandoned}/><FgtCell r={total.transferred}/><FgtCell r={total.active}/></div>}{!busy&&rows.length===0&&<div className="fxEmpty">Aucun effectif dans ce périmètre pour l’année consultée.</div>}</div></div>:<MovementsView items={movements.items} total={movements.total} q={q} setQ={setQ} type={movementType} setType={setMovementType} refresh={refresh}/>} 
  </section>:<DepositsView token={token} scope={scope} deposits={deposits} can={can} q={q} setQ={setQ} refresh={refresh} show={showDeposit} setShow={setShowDeposit} yearId={overview?.academic_year.id} schoolName={schoolName}/>} 
 </div>
}

function MovementsView({items,total,q,setQ,type,setType,refresh}:{items:EffectifsMovement[];total:number;q:string;setQ:(x:string)=>void;type:string;setType:(x:string)=>void;refresh:()=>Promise<void>}){return <div><div className="fxFilters"><label><Icon name="search"/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Élève, matricule, motif…"/></label><select value={type} onChange={e=>setType(e.target.value)}><option value="">Tous les mouvements</option><option value="ABANDON">Abandons</option><option value="TRANSFER">Transferts</option><option value="REINTEGRATE">Réintégrations</option><option value="CLASS_CHANGE">Changements de classe</option></select><button onClick={()=>void refresh()}>Appliquer</button><span>{total} mouvement(s)</span></div><div className="fxMoveTable"><div className="fxMoveRow head"><span>Date</span><span>Élève</span><span>Classe</span><span>Type</span><span>Motif / destination</span></div>{items.map(m=><div className="fxMoveRow" key={m.id}><span>{m.effective_date}</span><span><b>{m.student_name}</b><small>{m.matricule}</small></span><span>{m.class_label}<small>{m.section_label}</small></span><span><em className={`movement ${m.event_type.toLowerCase()}`}>{m.event_type}</em></span><span>{m.reason}<small>{m.destination||''}</small></span></div>)}</div></div>}

function DepositsView({token,scope,deposits,can,q,setQ,refresh,show,setShow,yearId,schoolName}:{token:string;scope:EffectifsScope;deposits:{items:DepositRow[];total:number};can:(p:string)=>boolean;q:string;setQ:(x:string)=>void;refresh:()=>Promise<void>;show:boolean;setShow:(v:boolean)=>void;yearId?:string;schoolName:string}){async function exportX(){try{await exportManaged(await fetchDepositsExport(token,scope,yearId),{school:schoolName,module:'Effectifs & dépôts',category:'Dépôts matériels',filename:'registre_depots_materiels.xlsx'})}catch(e){reportTechnical(e,'export dépôts');toast.error(friendlyError(e))}}return <section className="fxPanel"><div className="fxPanelTop"><div><h3>Registre des dépôts matériels</h3><p>Le périmètre sélectionné s’applique exactement comme aux effectifs.</p></div><div className="fxActions">{can('contributions.record')&&<button className="primary" onClick={()=>setShow(true)}><Icon name="plus"/>Enregistrer un dépôt</button>}{can('contributions.register.export_xlsx')&&<button onClick={()=>void exportX()}><Icon name="excel"/>Excel</button>}</div></div><div className="fxFilters"><label><Icon name="search"/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Élève, matricule, contribution…"/></label><button onClick={()=>void refresh()}>Rechercher</button><span>{deposits.total} dépôt(s)</span></div><div className="fxDepositTable"><div className="fxDepositRow head"><span>Date</span><span>Élève</span><span>Classe</span><span>Contribution</span><span>Quantité</span><span>Agent</span></div>{deposits.items.map(d=><div className="fxDepositRow" key={d.id}><span>{d.deposited_on}</span><span><b>{d.student_name}</b><small>{d.matricule}</small></span><span>{d.class_label}<small>{d.section_label}</small></span><span>{d.contribution_label}</span><span><b>{d.quantity}</b> {d.unit}</span><span>{d.recorded_by_name}</span></div>)}{deposits.items.length===0&&<div className="fxEmpty">Aucun dépôt matériel dans ce périmètre.</div>}</div>{show&&<DepositDialog token={token} scope={scope} yearId={yearId} onClose={()=>setShow(false)} onSaved={async()=>{setShow(false);await refresh()}}/>}</section>}

function DepositDialog({token,scope,yearId,onClose,onSaved}:{token:string;scope:EffectifsScope;yearId?:string;onClose:()=>void;onSaved:()=>Promise<void>}){const [search,setSearch]=useState('');const [students,setStudents]=useState<SchoolingStudent[]>([]);const [selected,setSelected]=useState<SchoolingStudent|null>(null);const [types,setTypes]=useState<ContributionType[]>([]);const [typeId,setTypeId]=useState('');const [qty,setQty]=useState('1');const [notes,setNotes]=useState('');const [error,setError]=useState('');useEffect(()=>{void listContributionTypes(token).then(setTypes).catch(e=>setError(friendlyError(e)))},[token]);async function find(){const r=await listStudents(token,{q:search,limit:20});setStudents(r.items)}async function save(){try{if(!selected||!typeId||!yearId)throw new Error('Sélectionnez un élève et une contribution');const full=await getStudent(token,selected.id);const enrollment=(full.enrollments||[]).find(e=>e.academic_year_id===yearId&&e.status!=='CANCELLED');if(!enrollment)throw new Error('Cet élève n’a pas d’inscription active dans l’année consultée');await recordMaterialDeposit(token,{enrollment_id:enrollment.id,contribution_type_id:typeId,quantity:Number(qty),notes,scope});await onSaved()}catch(e){setError(friendlyError(e))}}return <div className="wizardBackdrop"><div className="fxDepositDialog"><div className="modalHead"><div><h3>Nouveau dépôt matériel</h3><p>Une ligne append-only sera ajoutée au registre. L’historique n’est jamais écrasé.</p></div><button onClick={onClose}>×</button></div>{error&&<div className="error">{error}</div>}<div className="fxSearchStudent"><label><Icon name="search"/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nom ou matricule"/></label><button onClick={()=>void find()}>Chercher</button></div><div className="fxCandidate">{students.map(s=><button className={selected?.id===s.id?'selected':''} key={s.id} onClick={()=>setSelected(s)}><b>{s.last_name} {s.middle_name} {s.first_name}</b><small>{s.matricule} · {s.class_label||'Classe'}</small></button>)}</div><div className="formGrid"><label>Contribution<select value={typeId} onChange={e=>setTypeId(e.target.value)}><option value="">Choisir…</option>{types.map(t=><option key={t.id} value={t.id}>{t.label} ({t.unit})</option>)}</select></label><label>Quantité<input type="number" min="0.001" step="0.001" value={qty} onChange={e=>setQty(e.target.value)}/></label><label className="span2">Observation<input value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Facultatif"/></label></div><div className="modalActions"><button className="ghost" onClick={onClose}>Annuler</button><button onClick={()=>void save()}>Enregistrer le dépôt</button></div></div></div>}
