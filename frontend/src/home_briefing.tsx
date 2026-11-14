// « Le point du jour » (owner 2026-10-28: « quand un promoteur ou un chargé des finances ouvre son interface, il doit
// comprendre en quelques secondes ; le système doit lui parler »). Plain-language findings, title first (the conclusion,
// not the metric name), computed from the SAME read models as the cards below — no new data, no guess. Each finding is
// a clickable line that opens its detail. Only the widgets granted by the server projection are used, never a role name.
import React,{useEffect,useState} from 'react';
import {cashDaySummary,financeDecisions,getEffectifsCounts,getEffectifsMovements,getPersonnelSummary,getSchoolingSummary,recoveryMonthly,stewardshipCounts,stewardshipDashboard,type AccessWidget} from './api';
import {NavGlyph} from './platform/nav_icons';
import {ALL_DOMAINS,useLive} from './platform/live';

type Tone='ok'|'warn'|'bad'|'info';
type Finding={widget:string;tone:Tone;icon:string;title:string;text:string};
const num=(v:unknown)=>Number(v??0)||0;
const fc=(v:unknown)=>`${Math.round(num(v)).toLocaleString('fr-FR')} FC`;
const n=(v:unknown)=>num(v).toLocaleString('fr-FR');
// School year months in order (RDC: September → June); a month is « due » once it has started.
const MONTHS=['septembre','octobre','novembre','décembre','janvier','février','mars','avril','mai','juin','juillet','août'];
const schoolMonthIndex=(d:Date)=>(d.getMonth()+4)%12;   // September = 0

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
  // the cash desks' own business day (server), the same day as the promoteur's « Aujourd'hui » (owner, 2026-11-08)
  const d=await cashDaySummary(token);const cdf=d?.currencies?.CDF??{},usd=d?.currencies?.USD??{};
  const open=num(d?.open_count),closed=num(d?.closed_count);
  const gaps=(d?.sessions??[]).filter((x:any)=>x.status==='CLOSED'&&[x?.cdf?.variance,x?.usd?.variance].some((v:any)=>v!=null&&Math.abs(Number(v))>0.0001)).length;
  if(!open&&!closed)return {widget:'cash.supervision',tone:'info',icon:'receipt',title:'Aucune caisse ouverte aujourd’hui',text:'Aucun encaissement enregistré pour la journée.'};
  // net of cancellations / refunds, exactly like « L'argent de l'école » (receipts − cancellations)
  const net=(c:any)=>num(c.receipts)-num(c.reversals)-num(c.supervisor_reversals);
  const usdTxt=net(usd)?` et ${n(net(usd))} USD`:'';
  return {widget:'cash.supervision',tone:gaps?'warn':'ok',icon:'receipt',
    title:gaps?`${gaps} clôture${gaps>1?'s':''} de caisse avec écart à vérifier`:`Aujourd’hui : ${fc(net(cdf))} encaissés${usdTxt}`,
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
// The dashboard returns the LIST of items under their alert threshold (low_stock) and the sale stock with its own
// threshold; assets come as (status, quantity) rows. One finding for what runs out, one for equipment out of use.
async function stockFindings(token:string):Promise<Finding[]>{
  const s=await stewardshipDashboard(token);const out:Finding[]=[];
  const low=[...(Array.isArray(s?.low_stock)?s.low_stock:[]),...(Array.isArray(s?.sale_stock)?s.sale_stock:[]).filter((x:any)=>num(x.low_threshold)>0&&num(x.quantity)<=num(x.low_threshold))];
  if(low.length){const empty=low.filter((x:any)=>num(x.quantity)<=0).length;const names=low.slice(0,3).map((x:any)=>x.label).join(', ');
    out.push({widget:'inventory.stock',tone:empty?'bad':'warn',icon:'box',title:empty?`${n(empty)} article${empty>1?'s':''} en rupture de stock`:`${n(low.length)} article${low.length>1?'s':''} sous le seuil d’alerte`,
      text:`${names}${low.length>3?` et ${n(low.length-3)} autre(s)`:''} : à réapprovisionner${empty?' sans attendre':' avant rupture'}.`});}
  const assets=Array.isArray(s?.assets)?s.assets:[];const qty=(st:string)=>num(assets.find((a:any)=>a.status===st)?.n);
  const broken=qty('TO_REPAIR')+qty('OUT_OF_SERVICE'),repairing=qty('IN_REPAIR');
  if(assets.length)out.push(broken?{widget:'inventory.stock',tone:'warn',icon:'settings',title:`${n(broken)} équipement${broken>1?'s':''} hors d’usage`,text:`À réparer ou remplacer${repairing?` · ${n(repairing)} déjà en réparation`:''}. Le détail est dans le patrimoine.`}
    :{widget:'inventory.stock',tone:'ok',icon:'settings',title:'Patrimoine en état de marche',text:`${n(assets.reduce((a:number,x:any)=>a+num(x.n),0))} équipement(s) suivis${repairing?`, dont ${n(repairing)} en réparation`:''}.`});
  if(!low.length&&(Array.isArray(s?.low_stock)||Array.isArray(s?.sale_stock)))out.unshift({widget:'inventory.stock',tone:'ok',icon:'box',title:'Stocks au-dessus des seuils',text:'Aucun article à réapprovisionner pour l’instant.'});
  return out;
}
async function countsFinding(token:string):Promise<Finding|null>{
  const c=await stewardshipCounts(token);const draft=(c?.items??[]).filter((x:any)=>x.status==='DRAFT');
  if(!draft.length)return null;const gaps=draft.filter((x:any)=>num(x.total_variance)>0).length;
  return {widget:'inventory.counts',tone:'warn',icon:'doc',title:`${n(draft.length)} inventaire${draft.length>1?'s':''} en cours à valider`,
    text:`${gaps?`${n(gaps)} avec des écarts entre le compté et le théorique · `:''}le stock n’est corrigé qu’après validation.`};
}
async function movementsFinding(token:string,yearId?:string):Promise<Finding>{
  const since=new Date(Date.now()-30*864e5).toISOString().slice(0,10);
  const m=await getEffectifsMovements(token,'ALL',{yearId,limit:250});const recent=(m.items??[]).filter(x=>String(x.effective_date)>=since);
  const k=(t:string)=>recent.filter(x=>x.event_type===t).length;const ab=k('ABANDON'),tr=k('TRANSFER');
  if(!recent.length)return {widget:'headcounts.movements',tone:'ok',icon:'students',title:'Aucun mouvement d’élève ce mois-ci',text:'Ni abandon, ni transfert, ni suspension sur les 30 derniers jours.'};
  const parts=[[ab,'abandon'],[tr,'transfert'],[k('SUSPEND'),'suspension'],[k('REINTEGRATE'),'réintégration'],[k('CLASS_CHANGE'),'changement de classe']].filter(([v])=>v).map(([v,l])=>`${n(v)} ${l}${Number(v)>1&&l!=='changement de classe'?'s':''}`);
  return {widget:'headcounts.movements',tone:ab||tr?'warn':'info',icon:'students',title:ab?`${n(ab)} abandon${ab>1?'s':''} sur les 30 derniers jours`:`${n(recent.length)} mouvement${recent.length>1?'s':''} d’élèves ce mois-ci`,
    text:`${parts.join(' · ')}. Le dernier : ${recent[0].student_name} (${recent[0].class_label}).`};
}
async function filesFinding(token:string):Promise<Finding>{
  const s=await getSchoolingSummary(token);const k=num(s.profiles_to_complete),a=num(s.active_students);const pct=a?Math.round((a-k)*100/a):100;
  return k?{widget:'students.files',tone:pct<50?'warn':'info',icon:'doc',title:`${n(k)} dossier${k>1?'s':''} d’élève à compléter`,text:`${pct} % des dossiers sont complets. Il manque surtout la naissance, l’adresse ou le responsable : à compléter à l’accueil des parents.`}
    :{widget:'students.files',tone:'ok',icon:'doc',title:'Dossiers des élèves complets',text:`Les ${n(a)} élèves actifs ont un dossier suffisamment rempli.`};
}
async function personnelFinding(token:string):Promise<Finding>{
  const p=await getPersonnelSummary(token);
  return {widget:'personnel.summary',tone:num(p.suspended)?'warn':'info',icon:'users',title:`${n(p.active)} agent${num(p.active)>1?'s':''} en service`,
    text:`${n(p.teachers)} enseignant(s), ${n(p.administrative)} administratif(s), ${n(p.workers)} ouvrier(s)${num(p.suspended)?` · ${n(p.suspended)} suspendu(s)`:''}.`};
}

export function DailyBriefing({token,yearId,widgets,open}:{token:string;yearId?:string;widgets:AccessWidget[];open:(w:AccessWidget)=>void}){
  const has=(id:string)=>widgets.find(w=>w.id===id);
  const [items,setItems]=useState<Finding[]|null>(null);
  const [live,setLive]=useState(0);useLive(ALL_DOMAINS,()=>setLive(x=>x+1));   // the findings follow what happens in the school
  useEffect(()=>{let alive=true;if(!live)setItems(null);
    const jobs:Array<Promise<Finding|Finding[]|null>>=[];
    if(has('finance.recovery'))jobs.push(recoveryFinding(token,yearId));
    if(has('cash.supervision'))jobs.push(cashFinding(token));
    if(has('headcounts.summary'))jobs.push(headcountFinding(token,yearId));
    if(has('finance.decisions'))jobs.push(decisionsFinding(token));
    if(has('headcounts.movements'))jobs.push(movementsFinding(token,yearId));
    if(has('personnel.summary'))jobs.push(personnelFinding(token));
    if(has('students.files'))jobs.push(filesFinding(token));
    if(has('inventory.stock'))jobs.push(stockFindings(token));
    if(has('inventory.counts'))jobs.push(countsFinding(token));
    // one unavailable read model never hides the others
    Promise.allSettled(jobs).then(r=>{if(alive)setItems(r.flatMap(x=>x.status==='fulfilled'&&x.value?(Array.isArray(x.value)?x.value:[x.value]):[]))});
    return()=>{alive=false}},[token,yearId,widgets.map(w=>w.id).join(),live]);
  if(items&&items.length===0)return null;
  const worst=items?.find(i=>i.tone==='bad')??items?.find(i=>i.tone==='warn');
  return <section className="sh-brief" aria-labelledby="sh-brief-title" aria-busy={!items}>
    <header><span className="sh-brief-mark" aria-hidden="true"><NavGlyph g="sparkles" size={18}/></span>
      <div><h2 id="sh-brief-title">Le point du jour</h2>
        <p>{!items?'Lecture des chiffres de l’établissement…':worst?`À retenir en priorité : ${worst.title.charAt(0).toLowerCase()}${worst.title.slice(1)}.`:'Rien d’anormal aujourd’hui : les indicateurs suivis sont en ordre.'}</p></div></header>
    {!items?<div className="sh-brief-skel" aria-hidden="true"><i/><i/><i/></div>
      :<ul>{items.map((f,i)=>{const w=has(f.widget)!;return <li key={`${f.widget}-${i}`}>
        <button type="button" className={`sh-brief-item tone-${f.tone}`} onClick={()=>open(w)} aria-label={`${f.title}. ${f.text} Ouvrir le détail`}>
          <span className="sh-brief-icon" aria-hidden="true"><NavGlyph g={f.icon} size={18}/></span>
          <span className="sh-brief-text"><b>{f.title}</b><small>{f.text}</small></span>
          <span className="sh-brief-go" aria-hidden="true"><NavGlyph g="chevronRight" size={16}/></span></button></li>})}</ul>}
  </section>;
}
