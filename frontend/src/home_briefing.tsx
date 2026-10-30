// « Le point du jour » (owner 2026-10-28: « quand un promoteur ou un chargé des finances ouvre son interface, il doit
// comprendre en quelques secondes ; le système doit lui parler »). Plain-language findings, title first (the conclusion,
// not the metric name), computed from the SAME read models as the cards below — no new data, no guess. Each finding is
// a clickable line that opens its detail. Only the widgets granted by the server projection are used, never a role name.
import React,{useEffect,useState} from 'react';
import {cashDaySummary,financeDecisions,getEffectifsCounts,recoveryMonthly,stewardshipDashboard,type AccessWidget} from './api';
import {NavGlyph} from './platform/nav_icons';

type Tone='ok'|'warn'|'bad'|'info';
type Finding={widget:string;tone:Tone;icon:string;title:string;text:string};
const num=(v:unknown)=>Number(v??0)||0;
const fc=(v:unknown)=>`${Math.round(num(v)).toLocaleString('fr-FR')} FC`;
const n=(v:unknown)=>num(v).toLocaleString('fr-FR');
// School year months in order (RDC: September → June); a month is « due » once it has started.
const MONTHS=['septembre','octobre','novembre','décembre','janvier','février','mars','avril','mai','juin','juillet','août'];
const schoolMonthIndex=(d:Date)=>(d.getMonth()+4)%12;   // September = 0
const localDay=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};

async function recoveryFinding(token:string,yearId?:string):Promise<Finding|null>{
  const r=await recoveryMonthly(token,yearId,'CDF');const now=schoolMonthIndex(new Date());
  const due=(r.items??[]).filter(i=>{const k=MONTHS.indexOf(String(i.month_label??'').toLowerCase());return k>=0&&k<=now});
  const expected=due.reduce((a,i)=>a+num(i.expected),0),paid=due.reduce((a,i)=>a+num(i.regularized_total),0);
  const year=r.total;
  if(!expected&&!num(year?.expected))return {widget:'finance.recovery',tone:'info',icon:'finance',title:'Aucun frais attendu pour l’instant',text:'Le recouvrement s’affichera dès que des frais mensuels seront dus.'};
  const rate=expected?Math.round(paid*1000/expected)/10:0;
  const span=due.length?(due.length===1?due[0].month_label:`${due[0].month_label} à ${due[due.length-1].month_label}`).toString().toLowerCase():'';
  const tone:Tone=rate>=80?'ok':rate>=50?'warn':'bad';
  const title=rate>=80?`Recouvrement en bonne voie : ${n(rate)} %`:rate>=50?`Recouvrement à surveiller : ${n(rate)} %`:`Recouvrement en retard : ${n(rate)} %`;
  return {widget:'finance.recovery',tone,icon:'finance',title,
    text:`Mois échus (${span}) : ${fc(paid)} encaissés sur ${fc(expected)} attendus, il manque ${fc(expected-paid)}. Sur l’année : ${n(year?.recovery_rate)} % (${fc(year?.regularized_total)} sur ${fc(year?.expected)}).`};
}
async function cashFinding(token:string):Promise<Finding>{
  const d=await cashDaySummary(token,localDay());const cdf=d?.currencies?.CDF??{},usd=d?.currencies?.USD??{};
  const open=num(d?.open_count),closed=num(d?.closed_count);
  const gaps=(d?.sessions??[]).filter((x:any)=>x.status==='CLOSED'&&[x?.cdf?.variance,x?.usd?.variance].some((v:any)=>v!=null&&Math.abs(Number(v))>0.0001)).length;
  if(!open&&!closed)return {widget:'cash.supervision',tone:'info',icon:'receipt',title:'Aucune caisse ouverte aujourd’hui',text:'Aucun encaissement enregistré pour la journée.'};
  const usdTxt=num(usd.receipts)?` et ${n(usd.receipts)} USD`:'';
  return {widget:'cash.supervision',tone:gaps?'warn':'ok',icon:'receipt',
    title:gaps?`${gaps} clôture${gaps>1?'s':''} de caisse avec écart à vérifier`:`Aujourd’hui : ${fc(cdf.receipts)} encaissés${usdTxt}`,
    text:`${n(open)} caisse${open>1?'s':''} ouverte${open>1?'s':''}, ${n(closed)} clôturée${closed>1?'s':''} · dépenses ${fc(cdf.expenses)} · solde théorique ${fc(cdf.expected_cash)}.`};
}
async function headcountFinding(token:string,yearId?:string):Promise<Finding>{
  const c=await getEffectifsCounts(token,'section','ALL',yearId);const a=c.total.active;
  const parts=c.items.map(r=>`${r.label} ${n(r.active.total)}`).join(' · ');
  return {widget:'headcounts.summary',tone:'info',icon:'students',title:`${n(a.total)} élèves actifs`,
    text:`${n(a.female)} filles et ${n(a.male)} garçons${parts?` — ${parts}`:''}${num(c.total.abandoned.total)?` · ${n(c.total.abandoned.total)} abandon(s)`:''}.`};
}
async function decisionsFinding(token:string):Promise<Finding|null>{
  const d=await financeDecisions(token,'ACTIVE');const k=(d.items??[]).length;
  return k?{widget:'finance.decisions',tone:'info',icon:'shield',title:`${n(k)} décision${k>1?'s':''} financière${k>1?'s':''} active${k>1?'s':''}`,text:'Exonérations et réductions en vigueur : à garder sous contrôle.'}:null;
}
async function stockFinding(token:string):Promise<Finding|null>{
  const s=await stewardshipDashboard(token);const low=num(s?.low_stock);
  return low?{widget:'inventory.stock',tone:'warn',icon:'box',title:`${n(low)} article${low>1?'s':''} sous le seuil d’alerte`,text:'Le stock doit être réapprovisionné avant rupture.'}:null;
}

export function DailyBriefing({token,yearId,widgets,open}:{token:string;yearId?:string;widgets:AccessWidget[];open:(w:AccessWidget)=>void}){
  const has=(id:string)=>widgets.find(w=>w.id===id);
  const [items,setItems]=useState<Finding[]|null>(null);
  useEffect(()=>{let alive=true;setItems(null);
    const jobs:Array<Promise<Finding|null>>=[];
    if(has('finance.recovery'))jobs.push(recoveryFinding(token,yearId));
    if(has('cash.supervision'))jobs.push(cashFinding(token));
    if(has('headcounts.summary'))jobs.push(headcountFinding(token,yearId));
    if(has('finance.decisions'))jobs.push(decisionsFinding(token));
    if(has('inventory.stock'))jobs.push(stockFinding(token));
    // one unavailable read model never hides the others
    Promise.allSettled(jobs).then(r=>{if(alive)setItems(r.flatMap(x=>x.status==='fulfilled'&&x.value?[x.value]:[]))});
    return()=>{alive=false}},[token,yearId,widgets.map(w=>w.id).join()]);
  if(items&&items.length===0)return null;
  const worst=items?.find(i=>i.tone==='bad')??items?.find(i=>i.tone==='warn');
  return <section className="sh-brief" aria-labelledby="sh-brief-title" aria-busy={!items}>
    <header><span className="sh-brief-mark" aria-hidden="true"><NavGlyph g="sparkles" size={18}/></span>
      <div><h2 id="sh-brief-title">Le point du jour</h2>
        <p>{!items?'Lecture des chiffres de l’établissement…':worst?`À retenir en priorité : ${worst.title.charAt(0).toLowerCase()}${worst.title.slice(1)}.`:'Rien d’anormal aujourd’hui : les indicateurs suivis sont en ordre.'}</p></div></header>
    {!items?<div className="sh-brief-skel" aria-hidden="true"><i/><i/><i/></div>
      :<ul>{items.map(f=>{const w=has(f.widget)!;return <li key={f.widget}>
        <button type="button" className={`sh-brief-item tone-${f.tone}`} onClick={()=>open(w)} aria-label={`${f.title}. ${f.text} Ouvrir le détail`}>
          <span className="sh-brief-icon" aria-hidden="true"><NavGlyph g={f.icon} size={18}/></span>
          <span className="sh-brief-text"><b>{f.title}</b><small>{f.text}</small></span>
          <span className="sh-brief-go" aria-hidden="true"><NavGlyph g="chevronRight" size={16}/></span></button></li>})}</ul>}
  </section>;
}
