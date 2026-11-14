import React,{useEffect,useState} from 'react';
import {toast} from 'sonner';
import {supervisionAction,supervisionEvaluate,supervisionIncidents,type SupervisionIncident} from './messaging_api';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import './communications.css';

const DOMAIN:Record<string,string>={FINANCE:'Finances',CASH:'Caisse',SCHOOLING:'Scolarité',ACADEMIC:'Pédagogie',DISCIPLINE:'Discipline',PERSONNEL:'Personnel',STEWARDSHIP:'Intendance',CONFIGURATION:'Configuration',TECHNICAL:'Technique'};
const STATUS:Record<string,string>={NEW:'Nouvelle',ACKNOWLEDGED:'Prise en charge',IN_PROGRESS:'Traitement en cours',CLOSED:'Fermée'};
export default function SupervisionCenter({token,canEvaluate}:{token:string;canEvaluate:boolean}){
 const [state,setState]=useState('active'),[domain,setDomain]=useState(''),[data,setData]=useState<{items:SupervisionIncident[];counts:{active:number;critical:number;new:number}}|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 const load=async()=>{try{setError('');setData(await supervisionIncidents(token,state,domain))}catch(e){setError(friendlyError(e))}};
 useEffect(()=>{void load()},[token,state,domain]);
 async function act(i:SupervisionIncident,a:'acknowledge'|'start'|'close'){try{await supervisionAction(token,i.id,a);toast.success(a==='acknowledge'?'Alerte prise en charge':a==='start'?'Traitement commencé':'Alerte fermée');await load()}catch(e){toast.error(friendlyError(e))}}
 async function evaluate(){try{setBusy(true);const r=await supervisionEvaluate(token);toast.success(`Contrôle terminé : ${r.findings} situation(s), ${r.opened} nouvelle(s)`);await load()}catch(e){toast.error(friendlyError(e))}finally{setBusy(false)}}
 function open(path:string|null){if(!path)return;window.dispatchEvent(new CustomEvent('edusync:navigate',{detail:{path}}))}
 return <div className="vigie">
  <div className="vigieHero"><div><span className="eyebrow">VIGIE EDUSYNC</span><h3>Surveillance permanente de l’école</h3><p>Le système mesure les anomalies, explique leur cause et les adresse selon les capacités et le périmètre de chaque responsable.</p></div>
   {canEvaluate&&<button className="softBtn" disabled={busy} onClick={()=>void evaluate()}><NavGlyph g="pulse" size={16}/>{busy?'Contrôle…':'Contrôler maintenant'}</button>}</div>
  {data&&<div className="vigieKpis"><article><b>{data.counts.active}</b><small>situations actives</small></article><article className="critical"><b>{data.counts.critical}</b><small>critiques</small></article><article><b>{data.counts.new}</b><small>à prendre en charge</small></article></div>}
  <div className="vigieFilters"><select value={state} onChange={e=>setState(e.target.value)} aria-label="État"><option value="active">Actives</option><option value="resolved">Résolues</option><option value="all">Toutes</option></select><select value={domain} onChange={e=>setDomain(e.target.value)} aria-label="Domaine"><option value="">Tous les domaines</option>{Object.entries(DOMAIN).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></div>
  {error&&<div className="error" role="alert">{error}</div>}
  {!data?<div className="es-skeleton"><i/><i/><i/></div>:data.items.length===0?<div className="commEmpty"><b>Aucune anomalie dans votre périmètre.</b><p>La Vigie continuera à contrôler l’école automatiquement.</p></div>:
   <ul className="vigieList">{data.items.map(i=><li key={i.id} className={`sev-${i.severity.toLowerCase()}`}><div className="vigieTop"><span>{DOMAIN[i.domain]??i.domain}</span><em>{i.severity==='CRITICAL'?'Critique':i.severity==='WARNING'?'Avertissement':'Information'}</em><small>{STATUS[i.response_status]??i.response_status}</small></div><h4>{i.title}</h4><p>{i.summary}</p><details><summary>Pourquoi cette alerte ?</summary><p>{i.explanation}</p><b>Action recommandée</b><p>{i.recommendation}</p></details><div className="vigieActions">{i.target_path&&<button className="primaryBtn" onClick={()=>open(i.target_path)}>Ouvrir le dossier</button>}{i.response_status==='NEW'&&<button className="softBtn" onClick={()=>void act(i,'acknowledge')}>Prendre en charge</button>}{i.condition_status==='OPEN'&&i.response_status!=='IN_PROGRESS'&&<button className="softBtn" onClick={()=>void act(i,'start')}>Commencer le traitement</button>}{i.condition_status==='RESOLVED'&&i.response_status!=='CLOSED'&&<button className="softBtn" onClick={()=>void act(i,'close')}>Fermer</button>}</div></li>)}</ul>}
 </div>
}
