import { friendlyError } from './platform/errors';
import React,{useEffect,useMemo,useRef,useState} from 'react';
import {toast} from 'sonner';
import {ArchivedDocument,DocumentCatalogItem,PrintSettings,documentHistory,documentLink,getDocumentCatalog,getPrintSettings,putPrintSettings,schoolLogoBlob,studentImportTemplate,uploadSchoolLogo} from './api';
import {chooseManagedExportFolder,exportManaged,managedFolderReady,supportsManagedExportFolder} from './document_io';
import {NavGlyph} from './platform/nav_icons';
import './documents.css';

type Tab='history'|'catalog'|'identity';
const SIZE=(n:number)=>n<1024?`${n} o`:n<1048576?`${(n/1024).toFixed(0)} Ko`:`${(n/1048576).toFixed(1)} Mo`;

function History({token,canOpen}:{token:string;canOpen:boolean}){
 const [data,setData]=useState<{items:ArchivedDocument[];has_more:boolean;offset:number;limit:number;storage_available:boolean}|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState('');const [q,setQ]=useState('');
 useEffect(()=>{documentHistory(token).then(setData).catch(e=>setError(friendlyError(e)))},[token]);
 async function more(){if(!data)return;try{const n=await documentHistory(token,data.offset+data.limit);setData({...n,items:[...data.items,...n.items]})}catch(e){setError(friendlyError(e))}}
 async function open(d:ArchivedDocument){try{setBusy(d.id);const l=await documentLink(token,d.id);window.open(l.url,'_blank','noopener')}catch(e){setError(friendlyError(e))}finally{setBusy('')}}
 const items=(data?.items||[]).filter(d=>!q||`${d.title} ${d.file_name||''}`.toLowerCase().includes(q.toLowerCase()));
 if(!data&&!error)return <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>;
 return <section className="panel docPanel">
  {data&&!data.storage_available&&<div className="es-alert es-alert-bad" role="status">Le stockage des documents n’est pas disponible : les nouveaux exports restent téléchargeables mais ne sont pas archivés.</div>}
  {error&&<div className="error">{error}</div>}
  <div className="docToolbar"><div className="docSearch"><NavGlyph g="search" size={16}/><input aria-label="Rechercher dans les documents générés" placeholder="Rechercher un document…" value={q} onChange={e=>setQ(e.target.value)}/></div><small>{data?.items.length||0} document(s) · la version la plus récente de chaque document</small></div>
  {items.length===0?<div className="docEmpty"><NavGlyph g="doc" size={28}/><b>Aucun document généré pour l’instant</b><p>Chaque export PDF ou Excel réalisé dans EduSync apparaît ici automatiquement, avec son historique.</p></div>:
  <div className="docList" role="list">{items.map(d=><article key={d.id} className="docRow" role="listitem">
   <span className={`docFmt ${d.format.toLowerCase()}`} aria-hidden="true"><NavGlyph g={d.format==='PDF'?'doc':'sheet'} size={18}/></span>
   <div className="docMain"><b>{d.title}</b><small>{d.file_name||d.document_code} · {SIZE(d.byte_size)}{d.generations>1?` · ${d.generations} versions`:''}</small></div>
   <div className="docMeta"><span>{new Date(d.updated_at).toLocaleString('fr-FR',{dateStyle:'medium',timeStyle:'short'})}</span><small>{d.generated_by||'Membre de l’école'}</small></div>
   {canOpen&&<button className="es-btn" disabled={busy===d.id} onClick={()=>void open(d)}><NavGlyph g="external" size={15}/>{busy===d.id?'Ouverture…':'Ouvrir'}</button>}
  </article>)}</div>}
  {data?.has_more&&<button className="es-btn es-btn-ghost" onClick={()=>void more()}>Afficher plus</button>}
 </section>
}

function Catalog({token,permissions,schoolName}:{token:string;permissions:string[];schoolName:string}){
 const [items,setItems]=useState<DocumentCatalogItem[]>([]);const [error,setError]=useState('');const [q,setQ]=useState('');const [module,setModule]=useState('ALL');
 useEffect(()=>{getDocumentCatalog(token).then(x=>setItems(x.items)).catch(e=>setError(friendlyError(e)))},[token]);
 const modules=useMemo(()=>['ALL',...Array.from(new Set(items.map(x=>x.module)))],[items]);
 const filtered=items.filter(x=>(module==='ALL'||x.module===module)&&(!q||`${x.label} ${x.code} ${x.module}`.toLowerCase().includes(q.toLowerCase())));
 async function template(){try{const b=await studentImportTemplate(token);await exportManaged(b,{school:schoolName,module:'Scolarité',category:'Imports',filename:'modele_import_eleves_edusync.xlsx'})}catch(e){setError(friendlyError(e))}}
 async function chooseFolder(){try{const ok=await chooseManagedExportFolder();if(!ok)setError('Ce navigateur ne permet pas de gérer directement un dossier. Utilisez Edge ou Chrome récent ; les fichiers seront sinon téléchargés normalement.');else setError('')}catch(e){setError(friendlyError(e))}}
 return <section className="panel docPanel">
  <div className="panelHead"><div><h3>Catalogue des documents</h3><p>Les documents que EduSync sait produire pour votre école.</p><small>{supportsManagedExportFolder()?(managedFolderReady()?'Dossier EduSync actif pour cette session.':'Vous pouvez choisir un dossier : EduSync y classe les fichiers par année et par module.'):'Les fichiers sont enregistrés dans le dossier de téléchargement du navigateur.'}</small></div>
   <div className="docActions">{supportsManagedExportFolder()&&<button className="es-btn" onClick={()=>void chooseFolder()}><NavGlyph g="folder" size={16}/>Choisir un dossier</button>}{permissions.includes('documents.student_import_template.export')&&<button className="es-btn" onClick={()=>void template()}><NavGlyph g="download" size={16}/>Modèle d’import élèves</button>}</div></div>
  {error&&<div className="error">{error}</div>}
  <div className="docToolbar"><div className="docSearch"><NavGlyph g="search" size={16}/><input aria-label="Rechercher dans le catalogue" placeholder="Rechercher un document…" value={q} onChange={e=>setQ(e.target.value)}/></div><select aria-label="Filtrer par module" value={module} onChange={e=>setModule(e.target.value)}>{modules.map(m=><option key={m} value={m}>{m==='ALL'?'Tous les modules':m}</option>)}</select></div>
  <div className="docGrid">{filtered.map(d=><article className="docCard" key={d.code}><span className={`docFmt ${d.formats.includes('PDF')?'pdf':'xlsx'}`} aria-hidden="true"><NavGlyph g={d.formats.includes('PDF')?'doc':'sheet'} size={18}/></span><div><small>{d.module}</small><h4>{d.label}</h4><p>{d.formats.join(' · ')}</p><em className={d.status.startsWith('WEB_IMPLEMENTED')?'pill ready':'pill'}>{d.status.startsWith('WEB_IMPLEMENTED')?'Disponible':'Mise en page à valider'}</em></div></article>)}</div>
 </section>
}

function Identity({token}:{token:string}){
 const [logo,setLogo]=useState<string|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [busy,setBusy]=useState(false);const input=useRef<HTMLInputElement>(null);
 const [print,setPrint]=useState<PrintSettings|null>(null);
 async function load(){try{const b=await schoolLogoBlob(token);setLogo(old=>{if(old)URL.revokeObjectURL(old);return b?URL.createObjectURL(b):null})}catch(e){setError(friendlyError(e))}finally{setLoading(false)}}
 useEffect(()=>{void load();getPrintSettings(token).then(setPrint).catch(()=>setPrint(null));return()=>{setLogo(old=>{if(old)URL.revokeObjectURL(old);return null})}},[token]);
 async function upload(f:File){setError('');if(f.size>1048576){setError('Le logo dépasse 1 Mo.');return}if(!['image/png','image/jpeg'].includes(f.type)){setError('Choisissez une image PNG ou JPEG.');return}
  try{setBusy(true);await uploadSchoolLogo(token,f);toast.success('Logo enregistré : il apparaîtra sur les prochains documents.');await load()}catch(e){setError(friendlyError(e))}finally{setBusy(false);if(input.current)input.current.value=''}}
 async function savePrint(next:Partial<PrintSettings>){if(!print)return;try{const r=await putPrintSettings(token,{receipt_policy:next.receipt_policy||print.receipt_policy,receipt_format:next.receipt_format||print.receipt_format});setPrint(r);toast.success('Réglage d’impression enregistré')}catch(e){setError(friendlyError(e))}}
 return <div className="docIdentity">
  <section className="panel docPanel"><div className="panelHead"><div><h3>Logo de l’école</h3><p>Utilisé dans l’en-tête des documents PDF et Excel et sur les reçus.</p></div></div>
   {error&&<div className="error" role="alert">{error}</div>}
   <div className="logoBox"><div className="logoPreview">{loading?<span className="es-sr">Chargement…</span>:logo?<img src={logo} alt="Logo actuel de l’école"/>:<span><NavGlyph g="image" size={30}/><small>Aucun logo</small></span>}</div>
    <div className="logoActions"><input ref={input} type="file" accept="image/png,image/jpeg" className="es-sr" id="logoFile" onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f)}}/>
     <label htmlFor="logoFile" className="es-btn es-btn-primary" aria-disabled={busy}><NavGlyph g="upload" size={16}/>{busy?'Envoi…':logo?'Remplacer le logo':'Ajouter un logo'}</label>
     <small>PNG ou JPEG, 1 Mo maximum, au moins 32 × 32 pixels. Une image carrée sur fond clair donne le meilleur rendu.</small></div></div>
  </section>
  {print&&<section className="panel docPanel"><div className="panelHead"><div><h3>Impression des reçus</h3><p>Le paiement est toujours enregistré d’abord ; l’impression est une action séparée, tracée (original puis duplicata).</p></div></div>
   <fieldset className="choiceGroup"><legend>Après un encaissement</legend>
    {([['NONE','Ne rien proposer','Le caissier imprime le reçu depuis le message de confirmation s’il le souhaite.'],['PROPOSE','Proposer l’impression','Un bouton « Imprimer le reçu » est mis en avant après chaque encaissement.'],['AUTO_PREVIEW','Ouvrir l’aperçu automatiquement','L’aperçu du reçu s’ouvre ; l’impression reste confirmée par le caissier.']] as const).map(([v,l,h])=><label key={v} className={print.receipt_policy===v?'choice on':'choice'}><input type="radio" name="policy" checked={print.receipt_policy===v} onChange={()=>void savePrint({receipt_policy:v})}/><span><b>{l}</b><small>{h}</small></span></label>)}
   </fieldset>
   <fieldset className="choiceGroup"><legend>Format du reçu</legend>
    {([['A5','Feuille A5','Imprimante de bureau classique.'],['80MM','Ticket 80 mm','Imprimante thermique de caisse.']] as const).map(([v,l,h])=><label key={v} className={print.receipt_format===v?'choice on':'choice'}><input type="radio" name="format" checked={print.receipt_format===v} onChange={()=>void savePrint({receipt_format:v})}/><span><b>{l}</b><small>{h}</small></span></label>)}
   </fieldset>
   <p className="es-hint">Un navigateur ne peut pas imprimer sans confirmation. L’impression directe sur une imprimante de caisse nécessitera un petit programme local, prévu pour une étape ultérieure.</p>
  </section>}
 </div>
}

export default function DocumentsPage({token,permissions,schoolName}:{token:string;permissions:string[];schoolName:string}){
 const can=(p:string)=>permissions.includes(p);
 const tabs=([['history','Documents générés','doc',can('documents.history.read')],['catalog','Catalogue','folder',true],['identity','Logo et impression','image',can('settings.documents.manage')]] as const).filter(t=>t[3]);
 const [tab,setTab]=useState<Tab>(tabs[0]?.[0]||'catalog');
 return <div className="docsPage">
  <div className="settingsHeader"><div><h2>Documents</h2><p>Documents produits par EduSync pour {schoolName}, modèles et identité visuelle.</p></div></div>
  <div className="es-tabs docTabs" role="tablist">{tabs.map(([k,l,i])=><button key={k} role="tab" aria-selected={tab===k} className={tab===k?'es-on':''} onClick={()=>setTab(k)}><NavGlyph g={i} size={16}/>{l}</button>)}</div>
  {tab==='history'&&<History token={token} canOpen={can('documents.open')}/>}
  {tab==='catalog'&&<Catalog token={token} permissions={permissions} schoolName={schoolName}/>}
  {tab==='identity'&&<Identity token={token}/>}
 </div>
}
