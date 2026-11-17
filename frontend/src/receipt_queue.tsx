import {printReceiptOnWorkstation, receiptWorkstationFormat} from './platform/receipt_print';
import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {receiptQueue,receiptQueuePdf,receiptQueueStatus,receiptQueueBatchStatus,type ReceiptQueueData,type ReceiptQueueItem,type ReceiptQueueStatus} from './api';
import {friendlyError} from './platform/errors';
import {formatDate,formatMoney} from './platform/format';
import './checkout.css';
import {useLive} from './platform/live';

const EMPTY:ReceiptQueueData={counts:{PENDING:0,SUBMITTED:0,PRINTED:0,FAILED:0},items:[],has_more:false};
type Filter=ReceiptQueueStatus|'ALL';

export default function ReceiptQueue({token,canPrint}:{token:string;canPrint:boolean}){
 const [open,setOpen]=useState(false),[filter,setFilter]=useState<Filter>('PENDING');
 const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(0);
 const latestLoad=useRef(0);
 const viewKey=JSON.stringify([token,filter,search,page]);
 const [loadedView,setLoadedView]=useState('');
 const [result,setData]=useState<ReceiptQueueData>(EMPTY),[selected,setSelected]=useState<string[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [preview,setPreview]=useState<{url:string;title:string}|null>(null);const frame=useRef<HTMLIFrameElement>(null);
 const data=loadedView===viewKey?result:{...result,items:[],has_more:false};
 useLive(['finance'],()=>load());   // live: what another member records here appears without reloading (2026-11-01)
 async function load(){const seq=++latestLoad.current;try{const result=await receiptQueue(token,filter,search,page*50);if(seq!==latestLoad.current)return;if(!result.items.length&&page>0){setPage(page-1);return}setData(result);setLoadedView(viewKey);setError('')}catch(e){if(seq===latestLoad.current)setError(friendlyError(e))}}
 useEffect(()=>{void load();const update=()=>void load();window.addEventListener('edusync:receipt-created',update);window.addEventListener('focus',update);const timer=window.setInterval(update,60000);return()=>{window.removeEventListener('edusync:receipt-created',update);window.removeEventListener('focus',update);window.clearInterval(timer)}},[token,filter,search,page]);
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url)},[preview?.url]);
 useEffect(()=>{if(!open)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape'){if(preview)setPreview(null);else setOpen(false)}};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[open,preview]);
 const chosen=data.items.filter(item=>selected.includes(item.payment_id));
 const printable=data.items.filter(item=>item.status==='PENDING'||item.status==='FAILED');
 const ids=chosen.filter(item=>printable.includes(item)).map(item=>item.payment_id);
 const confirmable=chosen.filter(item=>item.status!=='PRINTED').map(item=>item.payment_id);
 async function print(idsToPrint:string[]){
  if(!idsToPrint.length)return;
  try{
   setBusy(true);setError('');setNotice('');
   const notice=await printReceiptOnWorkstation(format=>receiptQueuePdf(token,idsToPrint,format),()=>{
    setNotice('');setError('Le dialogue d’impression ne s’est pas ouvert. Utilisez « Ouvrir » pour imprimer.');
   });
   if(notice){
    try{await receiptQueueBatchStatus(token,idsToPrint,'SUBMITTED');setSelected([]);await load();}
    catch{setError('Reçus envoyés à l’imprimante. La file n’a pas été mise à jour. Vérifiez les tickets avant de réimprimer.');}
   }
   setNotice(notice ?? 'Après la sortie papier, confirmez les reçus en lot.');
  }catch(e){setError(friendlyError(e))}finally{setBusy(false)}
 }
 async function openItem(item:ReceiptQueueItem){try{setBusy(true);const pdf=await receiptQueuePdf(token,[item.payment_id],receiptWorkstationFormat());setPreview({url:URL.createObjectURL(pdf),title:`Reçu ${item.receipt_number}`})}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
 async function change(item:ReceiptQueueItem,status:'PENDING'|'PRINTED'|'FAILED'){try{setBusy(true);await receiptQueueStatus(token,item.payment_id,status,status==='FAILED'?'Imprimante indisponible ou impression interrompue':undefined);setSelected(ids=>ids.filter(id=>id!==item.payment_id));await load();setNotice(status==='PRINTED'?'Sortie papier confirmée par le caissier.':status==='FAILED'?'Échec conservé pour reprise.':'Reçu remis en attente.')}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
 async function confirmSelected(idsToConfirm:string[]){
  try{setBusy(true);await receiptQueueBatchStatus(token,idsToConfirm,'PRINTED');setSelected([]);await load();setNotice('Sortie papier confirmée pour la sélection.');}
  catch(e){setError(friendlyError(e))}finally{setBusy(false)}
 }
 async function retry(){try{setBusy(true);const failed=data.items.filter(item=>item.status==='FAILED');for(const item of failed)await receiptQueueStatus(token,item.payment_id,'PENDING');await load();setBusy(false);await print(failed.map(item=>item.payment_id))}catch(e){setError(friendlyError(e));setBusy(false)}}
 return <div className="receiptQueueHost"><button type="button" className="receiptQueueBadge" onClick={()=>setOpen(true)} aria-label={`${data.counts.PENDING} reçus en attente d’impression`}>Reçus · <b>{data.counts.PENDING} en attente</b>{data.counts.FAILED>0&&<em>{data.counts.FAILED} échec(s)</em>}</button>
 {/* The drawer is rendered at the root of the page (portal), the standard for dialogs: whatever the badge sits in (a
     header row, a sticky or positioned block), the drawer covers the whole page above the top bar (fix 2026-11-02). */}
 {open&&createPortal(<div className="receiptQueueBackdrop" onMouseDown={e=>e.target===e.currentTarget&&setOpen(false)}><section className="receiptQueueDrawer" role="dialog" aria-modal="true" aria-label="File des reçus"><header><div><h3>File des reçus</h3><small>Un paiement reste valide même si l’impression échoue.</small></div><button type="button" aria-label="Fermer" onClick={()=>setOpen(false)}>×</button></header>
 <form className="receiptQueueActions" role="search" onSubmit={event=>{event.preventDefault();setSelected([]);setPage(0);setFilter('ALL');setSearch(query.trim());}}>
 <input type="search" aria-label="Numéro du reçu ou nom de l’élève" placeholder="Numéro du reçu ou nom de l’élève" maxLength={120} value={query} onChange={e=>setQuery(e.target.value)}/>
 <button type="submit" disabled={busy}>Rechercher</button>{search&&<button type="button" disabled={busy} onClick={()=>{setQuery('');setSearch('');setPage(0);setSelected([])}}>Effacer</button>}
 </form>
 <nav aria-label="État des reçus">{(['PENDING','SUBMITTED','PRINTED','FAILED','ALL'] as const).map(state=><button key={state} type="button" className={filter===state?'active':''} onClick={()=>{setFilter(state);setSelected([]);setPage(0)}}>{({PENDING:'À imprimer',SUBMITTED:'Envoyés',PRINTED:'Imprimés',FAILED:'Échecs',ALL:'Tous'} as const)[state]}{state!=='ALL'&&` · ${data.counts[state]}`}</button>)}</nav>
 {error&&<p className="receiptQueueError" role="alert">{error}</p>}{notice&&<p className="receiptQueueNotice" role="status">{notice}</p>}
 {canPrint&&<div className="receiptQueueActions"><button type="button" disabled={busy||!ids.length} onClick={()=>void print(ids)}>Imprimer la sélection</button><button type="button" disabled={busy||!printable.length} onClick={()=>void print(printable.map(item=>item.payment_id))}>Imprimer les reçus affichés</button><button type="button" disabled={busy||!confirmable.length} onClick={()=>void confirmSelected(confirmable)}>Confirmer la sélection imprimée</button>{filter==='SUBMITTED'&&<button type="button" disabled={busy||!data.items.length} onClick={()=>void confirmSelected(data.items.filter(item=>item.status==='SUBMITTED').map(item=>item.payment_id))}>Confirmer la page imprimée</button>}{filter==='FAILED'&&<button type="button" disabled={busy||!data.items.length} onClick={()=>void retry()}>Réessayer les échecs</button>}</div>}
 <div className="receiptQueueList">{data.items.length===0?<p>{loadedView===viewKey?'Aucun reçu dans cette vue.':'Chargement des reçus…'}</p>:data.items.map(item=><article key={item.payment_id}><input type="checkbox" aria-label={`Sélectionner ${item.receipt_number}`} checked={selected.includes(item.payment_id)} onChange={e=>setSelected(current=>e.target.checked?[...current,item.payment_id]:current.filter(id=>id!==item.payment_id))}/><div><b>{item.receipt_number}</b><small>{item.student||'Élève'} · {formatDate(item.queued_at)} · {formatMoney(item.amount,item.currency)}</small><small>{item.status==='PENDING'?'En attente de sortie papier':item.status==='PRINTED'?'Sortie papier confirmée':item.status==='SUBMITTED'?'Envoyé à l’imprimante':'Échec à reprendre'}</small></div><div className="receiptQueueRowActions"><button type="button" disabled={busy} onClick={()=>void openItem(item)}>Ouvrir</button>{canPrint&&item.status!=='PRINTED'&&<>{item.status!=='SUBMITTED'&&<button type="button" disabled={busy} onClick={()=>void print([item.payment_id])}>Imprimer</button>}<button type="button" disabled={busy} onClick={()=>void change(item,'PRINTED')}>Confirmer imprimé</button>{item.status!=='FAILED'&&<button type="button" disabled={busy} onClick={()=>void change(item,'FAILED')}>Échec</button>}</>}</div></article>)}</div>
 {(page>0||data.has_more)&&<nav aria-label="Pagination des reçus"><button type="button" disabled={busy||page===0} onClick={()=>{setSelected([]);setPage(page-1)}}>Précédent</button><span>Page {page+1}</span><button type="button" disabled={busy||!data.has_more} onClick={()=>{setSelected([]);setPage(page+1)}}>Suivant</button></nav>}
 {preview&&<div className="receiptQueuePreview"><div><b>{preview.title}</b><button type="button" onClick={()=>setPreview(null)}>← Retour</button>{canPrint&&<button type="button" onClick={()=>frame.current?.contentWindow?.print()}>Imprimer</button>}<a href={preview.url} download={`${preview.title}.pdf`}>Télécharger</a></div><iframe ref={frame} src={preview.url} title={preview.title}/></div>}
 </section></div>,document.body)}</div>
}
