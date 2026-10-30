// « Journal de l'établissement » (2026-10-28). The Responsable financier and the Promoteur held audit.school.read /
// audit.school.filter / audit.entity.history.read but no screen used /audit/events: the right protected nothing visible.
// Read only: who did what, when, on what — filters by domain and period (audit.school.filter), and the before / after of
// an entry on click (audit.entity.history.read). The server keeps the journal append-only; nothing here writes.
import React,{useEffect,useState} from 'react';
import {friendlyError} from './platform/errors';
import {auditActionLabel} from './platform/labels';
import {NavGlyph} from './platform/nav_icons';
import {schoolJournal,schoolJournalEntity,type SchoolJournalRow} from './api';

// Domains of the journal: each groups the entity types the server records (one filter, several types).
const DOMAINS:{key:string;label:string;icon:string;types:string[]}[]=[
  {key:'finance',label:'Finances',icon:'finance',types:['FinancePayment','FinanceReceipt','CashExpense','CashDay','AdvanceFund','FinancialDecision','ChargeResponsibility','GeneratedReport','financial_history_import_batch','AnticipationPlan','AnticipationMembership','Tariff','FeeType','SchoolPaymentPolicy','SchoolBillingPolicy','StaffNoncashSettlement','OFFLINE_FINANCE_LEASE']},
  {key:'schooling',label:'Élèves et inscriptions',icon:'students',types:['Family','Student','student_import_batch','AdmissionCondition','material_contribution','ContributionType','BenefitPolicy']},
  {key:'staff',label:'Personnel',icon:'users',types:['Staff','StaffMember','StaffAssignment','StaffFunction','StaffAccessLink','StaffStudentLink','StaffStudentFinancePreference','staff_import_batch']},
  {key:'settings',label:'Paramétrage',icon:'settings',types:['School','SchoolBranding','SchoolClass','SchoolSection','SchoolOption','AcademicYear','SchoolPolicy','SchoolPrintSettings','SchoolProduct','inventory_item','CommunicationSettings','CommunicationTemplate','SchoolSmsWallet']},
  {key:'access',label:'Accès et sécurité',icon:'lock',types:['school_membership','SchoolMembership','Membership','rbac_role','rbac_assignment','rbac_change_request','User','UserSecurity']},
];
const PERIODS=[{key:'7',label:'7 derniers jours',days:7},{key:'30',label:'30 jours',days:30},{key:'all',label:'Tout',days:0}];
const domainOf=(type:string)=>DOMAINS.find(d=>d.types.includes(type));
const when=(v:string)=>new Date(v).toLocaleString('fr-FR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
// Before / after in plain language: technical identifiers are hidden, field names translated, money formatted, FC not CDF.
const FIELD_FR:Record<string,string>={amount:'Montant',reason:'Motif',category:'Catégorie',currency:'Devise',reference:'Référence',label:'Libellé',
  code:'Code',name:'Nom',status:'Statut',enabled:'Actif',quantity:'Quantité',unit_price:'Prix unitaire',price:'Prix',stock_quantity:'Stock',
  low_threshold:'Seuil d’alerte',last_name:'Nom',first_name:'Prénom',middle_name:'Postnom',phone:'Téléphone',email:'E-mail',category_code:'Catégorie',
  employee_no:'Matricule',matricule:'Matricule',gender:'Sexe',start_date:'Début',end_date:'Fin',effective_from:'À partir du',mode:'Mode de paiement',
  receipt_number:'N° de reçu',value_type:'Type de valeur',decision_type:'Décision',period_start:'Période du',period_end:'Période au',
  scope_type:'Périmètre',scope_value:'Section ou classe',full_name:'Nom complet',address:'Adresse',enrollment_start:'Ouverture des inscriptions',enrollment_end:'Fin des inscriptions'};
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const technical=(k:string,a:unknown,b:unknown)=>k==='id'||k.endsWith('_id')||k==='version'||k.endsWith('_at')||[a,b].some(v=>typeof v==='string'&&UUID.test(v));
function show(k:string,v:unknown):string{
  if(v===null||v===undefined||v==='')return '—';
  if(typeof v==='boolean')return v?'Oui':'Non';
  if(k==='currency')return v==='CDF'?'FC':String(v);
  if(/amount|price|total/.test(k)&&!isNaN(Number(v)))return Number(v).toLocaleString('fr-FR');
  if(typeof v==='object')return Array.isArray(v)?`${v.length} élément(s)`:'(détail)';
  return String(v).replace(/\bCDF\b/g,'FC').slice(0,80);
}
function changes(oldJ:any,newJ:any):[string,string,string][]{
  const o=oldJ&&typeof oldJ==='object'?oldJ:{},n=newJ&&typeof newJ==='object'?newJ:{};
  return [...new Set([...Object.keys(o),...Object.keys(n)])].filter(k=>JSON.stringify(o[k])!==JSON.stringify(n[k])&&!technical(k,o[k],n[k]))
    .slice(0,12).map(k=>[FIELD_FR[k]??k.replace(/_/g,' '),show(k,o[k]),show(k,n[k])]);
}

export function SchoolJournal({token,canFilter,canDetail}:{token:string;canFilter:boolean;canDetail:boolean}){
  const [domain,setDomain]=useState(''),[period,setPeriod]=useState('30');
  const [rows,setRows]=useState<SchoolJournalRow[]|null>(null),[next,setNext]=useState<{occurred_at:string;id:string}|null>(null),[error,setError]=useState('');
  const [open,setOpen]=useState<SchoolJournalRow|null>(null);
  const filters=()=>{if(!canFilter)return {};const p=PERIODS.find(x=>x.key===period)!;
    return {entity_types:DOMAINS.find(d=>d.key===domain)?.types,date_from:p.days?new Date(Date.now()-p.days*864e5).toISOString():undefined}};
  useEffect(()=>{let alive=true;setRows(null);setError('');
    schoolJournal(token,filters(),null).then(r=>{if(alive){setRows(r.items);setNext(r.next_cursor)}}).catch(e=>{if(alive)setError(friendlyError(e))});
    return()=>{alive=false}},[token,domain,period]);
  async function more(){if(!next)return;try{const r=await schoolJournal(token,filters(),next);setRows(x=>[...(x??[]),...r.items]);setNext(r.next_cursor)}catch(e){setError(friendlyError(e))}}
  return <section className="premiumCard sj">
    <div className="cardHeading"><div><h3>Journal de l’établissement</h3><p>Toutes les actions enregistrées par EduSync : qui a fait quoi, et quand. Lecture seule : rien ne peut y être modifié ni effacé.</p></div></div>
    {canFilter&&<div className="sj-filters">
      <div className="sj-chips" role="group" aria-label="Domaine">
        <button type="button" aria-pressed={domain===''} className={domain===''?'on':''} onClick={()=>setDomain('')}>Tout</button>
        {DOMAINS.map(d=><button key={d.key} type="button" aria-pressed={domain===d.key} className={domain===d.key?'on':''} onClick={()=>setDomain(d.key)}><NavGlyph g={d.icon} size={14}/>{d.label}</button>)}</div>
      <div className="sj-chips" role="group" aria-label="Période">{PERIODS.map(p=><button key={p.key} type="button" aria-pressed={period===p.key} className={period===p.key?'on':''} onClick={()=>setPeriod(p.key)}>{p.label}</button>)}</div>
    </div>}
    {error&&<div className="error" role="alert">{error}</div>}
    {!rows&&!error&&<div className="sj-skel" aria-busy="true"><i/><i/><i/><i/></div>}
    {rows&&rows.length===0&&<div className="personEmpty"><b>Aucune action sur cette période</b><small>Élargissez la période ou choisissez un autre domaine.</small></div>}
    {rows&&rows.length>0&&<ul className="sj-list">{rows.map(r=>{const d=domainOf(r.entity_type);const clickable=canDetail&&!!r.entity_id;
      const body=<><span className="sj-icon" aria-hidden="true"><NavGlyph g={d?.icon??'audit'} size={16}/></span>
        <span className="sj-main"><b>{auditActionLabel(r.action)}</b><small>{r.actor_name||'Système'} · {d?.label??'Autre'}{r.reason?` · « ${r.reason} »`:''}</small></span>
        <span className="sj-when">{when(r.occurred_at)}{r.result&&r.result!=='SUCCESS'?<em className="sj-bad">{r.result==='DENIED'?'Refusé':'Échec'}</em>:null}</span></>;
      return <li key={r.id}>{clickable?<button type="button" className="sj-row" onClick={()=>setOpen(r)} aria-label={`${auditActionLabel(r.action)} — voir le détail`}>{body}<NavGlyph g="chevronRight" size={15}/></button>:<div className="sj-row">{body}</div>}</li>})}</ul>}
    {next&&<button type="button" className="softBtn sj-more" onClick={()=>void more()}>Afficher plus d’actions</button>}
    {open&&<EntityHistory token={token} row={open} onClose={()=>setOpen(null)}/>}
  </section>;
}

function EntityHistory({token,row,onClose}:{token:string;row:SchoolJournalRow;onClose:()=>void}){
  const [items,setItems]=useState<any[]|null>(null),[error,setError]=useState('');
  useEffect(()=>{schoolJournalEntity(token,row.entity_type,row.entity_id!).then(r=>setItems(r.items)).catch(e=>setError(friendlyError(e)))},[token,row]);
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
  return <div className="wizardBackdrop" onClick={onClose}><aside className="sj-drawer" role="dialog" aria-modal="true" aria-label="Historique de l’élément" onClick={e=>e.stopPropagation()}>
    <header><div><small>{domainOf(row.entity_type)?.label??'Élément'}</small><h3>{auditActionLabel(row.action)}</h3><p>Toutes les actions enregistrées sur cet élément, de la plus récente à la plus ancienne.</p></div>
      <button type="button" aria-label="Fermer" onClick={onClose}><NavGlyph g="close" size={18}/></button></header>
    {error&&<div className="error" role="alert">{error}</div>}
    {!items&&!error&&<div className="sj-skel"><i/><i/></div>}
    {items&&<ol className="sj-timeline">{items.map(i=>{const diff=changes(i.old_json,i.new_json);return <li key={i.id}>
      <b>{auditActionLabel(i.action)}</b><small>{i.actor_name||'Système'} · {when(i.occurred_at)}</small>
      {diff.length>0&&<table className="sj-diff"><thead><tr><th>Information</th><th>Avant</th><th>Après</th></tr></thead><tbody>{diff.map(([k,a,b])=><tr key={k}><td>{k}</td><td>{a}</td><td>{b}</td></tr>)}</tbody></table>}
    </li>})}</ol>}
  </aside></div>;
}
