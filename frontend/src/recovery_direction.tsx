// Rapport de recouvrement de direction (owner, 2026-11-14): the report given to the school's hierarchy, by fee and period.
// The screen shows the key figures; the full report (classes, analysis, pupils to follow up, pupils not concerned) is the PDF.
import React,{useEffect,useState} from 'react';
import {recoveryDirectionReport,recoveryDirectionReportPdf,recoveryFees} from './api';
import {previewPdf} from './document_io';
import {friendlyError} from './platform/errors';
import './recovery_direction.css';

const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const money=(v:any,c:string)=>`${Number(v||0).toLocaleString('fr-FR')} ${c==='CDF'?'FC':c}`;
const pct=(v:any)=>`${Number(v||0).toLocaleString('fr-FR',{minimumFractionDigits:1,maximumFractionDigits:1})} %`;

export default function RecoveryDirection({token,can,yearId,currency,live}:{token:string;can:(p:string)=>boolean;yearId:string;currency:string;live:number}){
  const [fees,setFees]=useState<any[]>([]),[feeTypeId,setFeeTypeId]=useState(''),[periodOrder,setPeriodOrder]=useState(''),[asOf,setAsOf]=useState(today());
  const [report,setReport]=useState<any>(null),[loading,setLoading]=useState(false),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
  const periods=fees.find(f=>f.id===feeTypeId)?.periods??[];
  const params={yearId:yearId||undefined,currency,feeTypeId:feeTypeId||undefined,periodOrder:periodOrder?Number(periodOrder):undefined,asOf:asOf||undefined};

  useEffect(()=>{if(!yearId)return;recoveryFees(token,yearId).then(x=>{setFees(x.items);setFeeTypeId(v=>x.items.some((f:any)=>f.id===v)?v:'')}).catch(e=>setMsg(friendlyError(e)))},[token,yearId]);
  useEffect(()=>{if(!yearId)return;let active=true;setLoading(true);setMsg('');
    recoveryDirectionReport(token,params).then(x=>{if(active)setReport(x)}).catch(e=>{if(active){setReport(null);setMsg(friendlyError(e))}}).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false}},[token,yearId,currency,feeTypeId,periodOrder,asOf,live]);

  async function pdf(){setBusy(true);setMsg('');try{previewPdf(await recoveryDirectionReportPdf(token,params),'Rapport de recouvrement')}catch(e){setMsg(friendlyError(e))}finally{setBusy(false)}}
  const t=report?.total;

  return <>
    <div className="recoveryActions">
      <div><b>Rapport de direction</b><span>Le rapport de recouvrement pour la hiérarchie : chiffres clés, sections, classes, analyse et élèves à relancer</span></div>
      <div className="registerControls">
        <label><span>Type de frais</span><select aria-label="Type de frais du rapport" value={feeTypeId} onChange={e=>{setFeeTypeId(e.target.value);setPeriodOrder('')}}>
          <option value="">Tous les frais échus</option>{fees.map(f=><option key={f.id} value={f.id}>{f.label}</option>)}</select></label>
        <label><span>Période</span><select aria-label="Période du rapport" value={periodOrder} onChange={e=>setPeriodOrder(e.target.value)} disabled={!feeTypeId||periods.length===0}>
          <option value="">Toutes les périodes échues</option>{periods.map((p:any)=><option key={p.order} value={p.order}>{p.label}</option>)}</select></label>
        <label><span>Situation au</span><input type="date" aria-label="Date de situation" value={asOf} max={today()} onChange={e=>setAsOf(e.target.value||today())}/></label>
        {can('finance.views.vf01.export')&&<button onClick={()=>void pdf()} disabled={busy||!t?.concerned} aria-label="Produire le rapport PDF"><span>{busy?'Préparation…':'Rapport PDF'}</span></button>}
      </div>
    </div>
    {msg&&<div className="error" role="alert">{msg}</div>}
    {loading&&<div className="recoveryLoading" role="status">Calcul du rapport…</div>}
    {report&&<div className="directionReport" aria-busy={loading}>
      <p className="directionScope">{report.title} · situation au {report.as_of_label}</p>
      {!t.concerned?<p className="empty">Aucun élève n’est concerné à cette date.</p>:<>
        <div className="kpis">
          <article><span>%</span><b>{pct(t.rate)}</b><small>Taux de recouvrement</small></article>
          <article><span>✓</span><b>{money(t.collected,currency)}</b><small>Encaissé sur {money(t.expected,currency)}</small></article>
          <article><span>!</span><b>{money(t.remaining,currency)}</b><small>Reste à recouvrer</small></article>
          <article><span>=</span><b>{t.in_order} sur {t.concerned}</b><small>Élèves à jour · {t.not_in_order} à relancer</small></article>
        </div>
        <div className="directionTable" role="table" aria-label="Résultats par section">
          <div className="directionRow head" role="row"><span>Section</span><span>Élèves</span><span>À jour</span><span>Pas à jour</span><span>Attendu</span><span>Encaissé</span><span>Reste</span><span>Taux</span></div>
          {[...report.sections,t].map((s:any,i:number)=><div role="row" key={i} className={`directionRow ${i===report.sections.length?'total':''}`}>
            <b>{s.label}</b><span>{s.concerned}</span><span>{s.in_order}</span><span>{s.not_in_order}</span><span>{money(s.expected,currency)}</span>
            <span>{money(s.collected,currency)}</span><span>{money(s.remaining,currency)}</span><strong>{pct(s.rate)}</strong></div>)}
        </div>
        <p className="recoveryFootnote">
          {report.analysis.without_contact>0&&<>{report.analysis.without_contact} élève(s) pas à jour sans numéro de téléphone enregistré. </>}
          {(report.exempted_counts.ARRIVAL+report.exempted_counts.EXEMPTION)>0&&<>{report.exempted_counts.ARRIVAL+report.exempted_counts.EXEMPTION} élève(s) non concerné(s) (inscription après la date limite ou exonération), non comptés. </>}
          Le PDF contient aussi le détail par classe, l’analyse et la liste des élèves à relancer avec le contact des parents.
        </p>
      </>}
    </div>}
  </>;
}
