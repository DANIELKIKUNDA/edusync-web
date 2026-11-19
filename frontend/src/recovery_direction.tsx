// Rapport de recouvrement de direction (owner, 2026-11-14): the report given to the school's hierarchy, by fee and period.
// The screen shows the key figures; the full report (classes, analysis, pupils to follow up, pupils not concerned) is the PDF.
import React,{useEffect,useState,useMemo} from 'react';
import {recoveryDigestPdf,recoveryDigestSend,recoveryDirectionReport,recoveryDirectionReportPdf,recoveryFees} from './api';
import {previewPdf} from './document_io';
import {friendlyError} from './platform/errors';
import {confirmAction} from './platform/dialogs';
import './recovery_direction.css';

const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const money=(v:any,c:string)=>`${Number(v||0).toLocaleString('fr-FR')} ${c==='CDF'?'FC':c}`;
const pct=(v:any)=>`${Number(v||0).toLocaleString('fr-FR',{minimumFractionDigits:1,maximumFractionDigits:1})} %`;

export default function RecoveryDirection({token,can,yearId,currency,live}:{token:string;can:(p:string)=>boolean;yearId:string;currency:string;live:number}){
  const [fees,setFees]=useState<any[]>([]),[feeTypeId,setFeeTypeId]=useState(''),[periodOrder,setPeriodOrder]=useState(''),[asOf,setAsOf]=useState(today());
  const [report,setReport]=useState<any>(null),[loading,setLoading]=useState(false),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
  const [search,setSearch]=useState(''),[section,setSection]=useState(''),[classFilter,setClassFilter]=useState(''),[page,setPage]=useState(0);
  const periods=fees.find(f=>f.id===feeTypeId)?.periods??[];
  const params={yearId:yearId||undefined,currency,feeTypeId:feeTypeId||undefined,periodOrder:periodOrder?Number(periodOrder):undefined,asOf:asOf||undefined};

  useEffect(()=>{if(!yearId)return;recoveryFees(token,yearId).then(x=>{setFees(x.items);setFeeTypeId(v=>x.items.some((f:any)=>f.id===v)?v:'')}).catch(e=>setMsg(friendlyError(e)))},[token,yearId]);
  useEffect(()=>{if(!yearId)return;let active=true;setReport(null);setLoading(true);setMsg('');
    recoveryDirectionReport(token,params).then(x=>{if(active)setReport(x)}).catch(e=>{if(active){setReport(null);setMsg(friendlyError(e))}}).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false}},[token,yearId,currency,feeTypeId,periodOrder,asOf,live]);

  async function pdf(){setBusy(true);setMsg('');try{previewPdf(await recoveryDirectionReportPdf(token,params),'Rapport de recouvrement')}catch(e){setMsg(friendlyError(e))}finally{setBusy(false)}}
  const t=report?.total;
  const unpaid:any[]=report?.unpaid??[];
  const sections=Array.from(new Set(unpaid.map(s=>s.section_label))).sort();
  const classes=Array.from(new Set(unpaid.filter(s=>!section||s.section_label===section).map(s=>s.class_label))).sort((a,b)=>a.localeCompare(b,'fr',{numeric:true}));
  const normalize=(v:string)=>v.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('fr');
  const filtered=useMemo(()=>unpaid.filter(s=>(!section||s.section_label===section)&&(!classFilter||s.class_label===classFilter)&&normalize([s.student_name,s.matricule,s.contact_name,s.contact_phone].join(' ')).includes(normalize(search.trim()))),[report,search,section,classFilter]);
  useEffect(()=>{setPage(0)},[report,search,section,classFilter]);
  useEffect(()=>{setSection('');setClassFilter('')},[token,yearId]);
  const pageSize=50,maxPage=Math.max(0,Math.ceil(filtered.length/pageSize)-1),currentPage=Math.min(page,maxPage);


  // Owner, 2026-11-19: the weekly / monthly letter, in the reader's scope (whole school, or his section).
  async function digest(kind:'WEEK'|'MONTH'){setBusy(true);setMsg('');try{previewPdf(await recoveryDigestPdf(token,kind,currency),kind==='WEEK'?'Rapport de la semaine':'Rapport du mois')}catch(e){setMsg(friendlyError(e))}finally{setBusy(false)}}
  // Owner, 2026-11-19: « Envoyer aux responsables » — each one receives HIS report by e-mail, PDF attached.
  async function send(kind:'WEEK'|'MONTH'){
    if(!await confirmAction({title:kind==='WEEK'?'Envoyer le rapport de la semaine ?':'Envoyer le rapport du mois ?',message:kind==='WEEK'?'Chaque responsable de toute l’école (promoteur, gestionnaire, chargé financier…) reçoit par e-mail sa lettre et le PDF. Un même rapport n’est jamais envoyé deux fois.':'Chaque responsable reçoit par e-mail son rapport : toute l’école pour la direction, sa section pour le préfet et les directeurs. Un même rapport n’est jamais envoyé deux fois.',confirmLabel:'Envoyer'}))return;
    setBusy(true);setMsg('');try{const r=await recoveryDigestSend(token,kind,currency);setMsg([r.sent.length?`Envoyé à : ${r.sent.join(', ')}.`:'',r.already_sent.length?`Déjà envoyé à : ${r.already_sent.join(', ')}.`:'',r.without_email.length?`Sans adresse e-mail (à compléter dans Accès & rôles) : ${r.without_email.join(', ')}.`:''].filter(Boolean).join(' ')||'Aucun responsable à qui envoyer.')}catch(e){setMsg(friendlyError(e))}finally{setBusy(false)}}
  return <>
    {can('finance.views.vf01.export')&&<div className="recoveryActions">
      <div><b>Rapport de la semaine et du mois</b><span>Une lettre claire pour la direction : l’argent, le recouvrement, les élèves et les points à surveiller, puis le détail par classe</span></div>
      <div className="registerControls"><button type="button" className="softBtn" disabled={busy} onClick={()=>void digest('WEEK')}>Rapport de la semaine</button><button type="button" className="softBtn" disabled={busy} onClick={()=>void digest('MONTH')}>Rapport du mois</button>{can('finance.cash.other.read')&&<><button type="button" className="softBtn" disabled={busy} onClick={()=>void send('WEEK')}>Envoyer la semaine aux responsables</button><button type="button" className="softBtn" disabled={busy} onClick={()=>void send('MONTH')}>Envoyer le mois aux responsables</button></>}</div>
    </div>}
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
        <section className="directionPupils" aria-label="Élèves à relancer">
          <div className="directionPupilsTitle"><div><h3>Élèves à relancer</h3><p>Les dettes correspondant aux frais et à la période sélectionnés, dans votre périmètre autorisé.</p></div><strong>{unpaid.length} élève(s)</strong></div>
          <div className="directionPupilFilters">
            <label>Rechercher<input type="search" placeholder="Nom, matricule ou téléphone…" aria-label="Rechercher un élève à relancer" value={search} onChange={e=>setSearch(e.target.value)}/></label>
            <label>Section<select aria-label="Section des élèves à relancer" value={section} onChange={e=>{setSection(e.target.value);setClassFilter('')}}><option value="">Toutes les sections autorisées</option>{sections.map(s=><option key={s}>{s}</option>)}</select></label>
            <label>Classe<select aria-label="Classe des élèves à relancer" value={classFilter} onChange={e=>setClassFilter(e.target.value)}><option value="">Toutes les classes autorisées</option>{classes.map(c=><option key={c}>{c}</option>)}</select></label>
          </div>
          <p role="status">{filtered.length} résultat(s) · Reste dû : <b>{money(filtered.reduce((sum,s)=>sum+Number(s.remaining||0),0),currency)}</b></p>
          <div className="directionPupilTable"><table><caption>Élèves non en ordre — {report.title}</caption><thead><tr><th>Élève</th><th>Section / classe</th><th>Non réglé</th><th>Parent ou tuteur</th><th>Reste dû</th></tr></thead><tbody>
            {filtered.slice(currentPage*pageSize,(currentPage+1)*pageSize).map(s=><tr key={s.enrollment_id}><td><b>{s.student_name}</b><small>{s.matricule}</small></td><td>{s.section_label}<small>{s.class_label}</small></td><td>{s.missing.join(', ')}</td><td>{s.contact_name||'Non renseigné'}<small>{s.contact_phone?<a href={`tel:${s.contact_phone.replace(/[^+0-9]/g,'')}`}>{s.contact_phone}</a>:'Téléphone non renseigné'}</small></td><td className="directionDebt">{money(s.remaining,currency)}</td></tr>)}
            {!filtered.length&&<tr><td colSpan={5}>{unpaid.length?'Aucun élève ne correspond à ces filtres.':'Tous les élèves concernés sont en ordre.'}</td></tr>}
          </tbody></table></div>
          {filtered.length>pageSize&&<nav className="directionPagination" aria-label="Pages des élèves à relancer"><button disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Précédent</button><span>Page {currentPage+1} sur {maxPage+1}</span><button disabled={currentPage===maxPage} onClick={()=>setPage(currentPage+1)}>Suivant</button></nav>}
          <small>Le rapport PDF conserve la liste complète du périmètre autorisé ; la recherche et les filtres ci-dessus concernent cette vue à l’écran.</small>
        </section>
        <p className="recoveryFootnote">
          {report.analysis.without_contact>0&&<>{report.analysis.without_contact} élève(s) pas à jour sans numéro de téléphone enregistré. </>}
          {(report.exempted_counts.ARRIVAL+report.exempted_counts.EXEMPTION)>0&&<>{report.exempted_counts.ARRIVAL+report.exempted_counts.EXEMPTION} élève(s) non concerné(s) (inscription après la date limite ou exonération), non comptés. </>}
          Le PDF contient aussi le détail par classe, l’analyse et la liste des élèves à relancer avec le contact des parents.
        </p>
      </>}
    </div>}
  </>;
}
