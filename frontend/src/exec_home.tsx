import React,{useEffect,useMemo,useState} from 'react';
import {Card,Skeleton} from './platform/ui';
import {ScreenError} from './platform/screen_boundary';
import {ALL_DOMAINS,useLive} from './platform/live';
import {financePilotage,getEffectifsCounts,type EffectifsCounts,type EffectifsRow,type FinancePilotage} from './api';
import './exec_home.css';

/* Executive home (owner, 2026-11-08) — promoteur, his assistant, gestionnaire, responsable financier.
   « Le tableau de bord du promoteur, c'est l'argent et les effectifs » : the money received (today, this week, this
   month, since the start of the year) and what remains to recover; the pupils in total and per section, with the
   detail per class (and per option in the secondary) on hover — or on tap on a phone. No operational action here. */

const n=(v:number)=>new Intl.NumberFormat('fr-FR').format(v);
const money=(v:string|number|undefined)=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:0}).format(Number(v||0));
const hasValue=(v?:string)=>Number(v||0)!==0;

function useLoad<T>(load:()=>Promise<T>,deps:unknown[]){
  const [s,setS]=useState<{data?:T;error?:unknown;loading:boolean}>({loading:true});const [attempt,setAttempt]=useState(0);const [live,setLive]=useState(0);
  useLive(ALL_DOMAINS,()=>setLive(x=>x+1));
  useEffect(()=>{let alive=true;setS(x=>({...x,loading:x.data===undefined,error:undefined}));load().then(data=>alive&&setS({data,loading:false})).catch(error=>alive&&setS({error,loading:false}));return()=>{alive=false}},[...deps,attempt,live]);
  return {...s,retry:()=>setAttempt(a=>a+1)};
}

type Common={icon:string;title:string;onClick:()=>void;index:number;ariaLabel:string};

export function MoneyPilotage({common,token,yearId}:{common:Common;token:string;yearId?:string}){
  const s=useLoad<FinancePilotage>(()=>financePilotage(token,yearId),[token,yearId]);
  const d=s.data;
  const periods:[keyof PilotagePeriodsT,string,string][]=d&&d.cash?[['today','Aujourd’hui',new Date(d.today).toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'})],
    ['week','Cette semaine',`depuis le ${new Date(d.week_start).toLocaleDateString('fr-FR',{day:'numeric',month:'long'})}`],
    ['month','Ce mois',new Date(d.month_start).toLocaleDateString('fr-FR',{month:'long',year:'numeric'})],
    ['year','Depuis la rentrée',`depuis le ${new Date(d.academic_year.start_date).toLocaleDateString('fr-FR',{day:'numeric',month:'long'})}`]]:[];
  const cash=d?.cash;
  return <Card level="info" wide icon={common.icon} title={d&&!cash?'Les finances de votre section':common.title} index={common.index} className="ex-money">
    {s.loading&&!d?<Skeleton lines={3}/>:s.error?<ScreenError compact error={s.error} onRetry={s.retry}/>:d&&!cash?<SectionMoney d={d} open={common.onClick}/>:d&&cash&&<>
      <p className="ex-sub">Argent réellement entré dans les caisses de l’école (encaissements moins annulations et remboursements) · année {d.academic_year.label}</p>
      <div className="ex-money-grid">
        {periods.map(([k,label,when])=><button type="button" key={k} className="ex-tile" onClick={common.onClick} aria-label={`${label} : ${money(cash.CDF[k])} FC${hasValue(cash.USD[k])?` et ${money(cash.USD[k])} USD`:''}`}>
          <small>{label}</small><strong>{money(cash.CDF[k])} <em>FC</em></strong>{hasValue(cash.USD[k])?<b>{money(cash.USD[k])} USD</b>:<b className="ex-muted">0 USD</b>}<span>{when}</span></button>)}
        <button type="button" className="ex-tile ex-tile-due" onClick={common.onClick} aria-label={`Reste à recouvrer : ${money(d.recovery.CDF.remaining)} FC`}>
          <small>Reste à recouvrer</small><strong>{money(d.recovery.CDF.remaining)} <em>FC</em></strong>
          {hasValue(d.recovery.USD.remaining)?<b>{money(d.recovery.USD.remaining)} USD</b>:<b className="ex-muted">0 USD</b>}
          <span>{Number(d.recovery.CDF.rate||0).toLocaleString('fr-FR')} % recouvré sur l’année</span>
          <i aria-hidden="true"><em style={{width:`${Math.min(100,Number(d.recovery.CDF.rate||0))}%`}}/></i></button>
      </div></>}
  </Card>;
}

type PilotagePeriodsT=NonNullable<FinancePilotage['cash']>['CDF'];

/* Préfet / direction de section given the finances (owner, 2026-11-08): the cash desks are school-wide, so a section
   leader follows what HIS section's pupils owe and have paid this year (the server limits the figures to his section). */
function SectionMoney({d,open}:{d:FinancePilotage;open:()=>void}){
  const r=d.recovery;const tile=(label:string,k:'expected'|'regularized'|'remaining',hint:string,due=false)=>
    <button type="button" className={`ex-tile${due?' ex-tile-due':''}`} onClick={open}><small>{label}</small><strong>{money(r.CDF[k])} <em>FC</em></strong>
      {hasValue(r.USD[k])?<b>{money(r.USD[k])} USD</b>:<b className="ex-muted">0 USD</b>}<span>{hint}</span>
      {due&&<i aria-hidden="true"><em style={{width:`${Math.min(100,Number(r.CDF.rate||0))}%`}}/></i>}</button>;
  return <><p className="ex-sub">Frais des élèves de votre section · année {d.academic_year.label} · les caisses de l’école sont suivies par la direction financière.</p>
    <div className="ex-money-grid">{tile('Attendu sur l’année','expected','frais échus et à venir')}{tile('Déjà payé','regularized','encaissé et régularisé')}
      {tile('Reste à recouvrer','remaining',`${Number(r.CDF.rate||0).toLocaleString('fr-FR')} % recouvré sur l’année`,true)}</div></>;
}

type Breakdown={label:string;rows:EffectifsRow[];byOption:EffectifsRow[];total:number;female:number;male:number};

export function ExecutiveHeadcounts({common,token,yearId,breakdowns}:{common:Common;token:string;yearId?:string;breakdowns:('section'|'class'|'option')[]}){
  const canClass=breakdowns.includes('class'),canOption=breakdowns.includes('option'),canSection=breakdowns.includes('section');
  const group=canClass?'class':canSection?'section':canOption?'option':null;
  const s=useLoad<EffectifsCounts|null>(()=>group?getEffectifsCounts(token,group,'ALL',yearId):Promise.resolve(null),[token,yearId,group]);
  const o=useLoad<EffectifsCounts|null>(()=>canOption&&group!=='option'?getEffectifsCounts(token,'option','ALL',yearId):Promise.resolve(null),[token,yearId,canOption,group]);
  const [open,setOpen]=useState<string|null>(null);const [view,setView]=useState<'class'|'option'>('class');
  const hover=typeof window!=='undefined'&&window.matchMedia?.('(hover: hover) and (pointer: fine)').matches;
  const sections=useMemo<Breakdown[]>(()=>{const c=s.data;if(!c)return [];const map=new Map<string,Breakdown>();
    for(const r of c.items){const k=r.section||'Autres';const b=map.get(k)??{label:k,rows:[],byOption:[],total:0,female:0,male:0};
      if(group==='class')b.rows.push(r);b.total+=r.active.total;b.female+=r.active.female;b.male+=r.active.male;map.set(k,b)}
    for(const r of o.data?.items??[]){const b=map.get(r.section);if(b&&r.code)b.byOption.push(r)}
    return [...map.values()]},[s.data,o.data,group]);
  useEffect(()=>{if(!open)return;const k=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(null)};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[open]);
  const c=s.data;
  return <Card level="info" wide icon={common.icon} title={common.title} index={common.index} className="ex-heads">
    {s.loading&&!c?<Skeleton lines={3}/>:s.error?<ScreenError compact error={s.error} onRetry={s.retry}/>:!c?<p className="ui-card-hint">Ventilation des effectifs non autorisée.</p>:<>
      <p className="ex-sub">Élèves actifs (hors abandons et transferts) · {hover?'survolez':'touchez'} une section pour voir le détail{sections.some(b=>b.byOption.length)?' par classe et par option':' par classe'}.</p>
      <div className="ex-heads-grid">
        <button type="button" className="ex-tile ex-total" onClick={common.onClick} aria-label={`${n(c.total.active.total)} élèves actifs — ouvrir les effectifs`}>
          <small>{sections.length===1?'Total de votre section':'Total de l’école'}</small><strong>{n(c.total.active.total)}</strong><span>{n(c.total.active.female)} filles · {n(c.total.active.male)} garçons</span>
          <span className="ex-muted">{n(c.total.enrolled.total)} inscrits · {n(c.total.abandoned.total)} abandons · {n(c.total.transferred.total)} transferts</span></button>
        {sections.map(b=>{const isOpen=open===b.label;const share=c.total.active.total?Math.round(b.total*100/c.total.active.total):0;const opts=b.byOption.length>0;
          const rows=(view==='option'&&opts?b.byOption:b.rows);
          return <div key={b.label} className={`ex-sec${isOpen?' open':''}`} onMouseEnter={hover?()=>setOpen(b.label):undefined} onMouseLeave={hover?()=>setOpen(x=>x===b.label?null:x):undefined}>
            <button type="button" className="ex-tile" aria-expanded={isOpen} onClick={()=>setOpen(x=>hover?b.label:x===b.label?null:b.label)} onFocus={hover?()=>setOpen(b.label):undefined}>
              <small>{b.label}</small><strong>{n(b.total)}</strong><span>{n(b.female)} F · {n(b.male)} G{sections.length>1?` · ${share} % de l’école`:''}</span>
              <i aria-hidden="true"><em style={{width:`${share}%`}}/></i><span className="ex-more">{isOpen&&!hover?'Masquer le détail':'Voir le détail'}</span></button>
            {isOpen&&(b.rows.length>0||opts)&&<div className="ex-pop" role="region" aria-label={`Détail ${b.label}`}>
              {opts&&b.rows.length>0&&<div className="ex-pop-tabs" role="tablist"><button type="button" role="tab" aria-selected={view==='class'} className={view==='class'?'active':''} onClick={()=>setView('class')}>Par classe</button><button type="button" role="tab" aria-selected={view==='option'} className={view==='option'?'active':''} onClick={()=>setView('option')}>Par option</button></div>}
              <table data-keep-table><thead><tr><th>{view==='option'&&opts?'Option':'Classe'}</th><th>F</th><th>G</th><th>Total</th></tr></thead>
                <tbody>{(rows.length?rows:b.byOption).map(r=><tr key={r.section+(r.code||r.label)}><td>{r.label}</td><td>{n(r.active.female)}</td><td>{n(r.active.male)}</td><td><b>{n(r.active.total)}</b></td></tr>)}</tbody>
                <tfoot><tr><td>{b.label}</td><td>{n(b.female)}</td><td>{n(b.male)}</td><td><b>{n(b.total)}</b></td></tr></tfoot></table>
            </div>}
          </div>})}
      </div></>}
  </Card>;
}
