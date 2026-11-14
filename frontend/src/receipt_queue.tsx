import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {receiptQueue,receiptQueuePdf,receiptQueueStatus,type ReceiptQueueData,type ReceiptQueueItem} from './api';
import {friendlyError} from './platform/errors';
import {formatDate,formatMoney} from './platform/format';
import './checkout.css';
import {useLive} from './platform/live';

const EMPTY:ReceiptQueueData={counts:{PENDING:0,PRINTED:0,FAILED:0},items:[]};
type Filter='PENDING'|'PRINTED'|'FAILED'|'ALL';

/** A browser can open its print dialog; only a cashier can confirm that paper was produced. */
function browserPrint(blob:Blob,onError:()=>void){
 const url=URL.createObjectURL(blob),frame=document.createElement('iframe');
 frame.title='Reçus à imprimer';frame.style.cssText='position:fixed;width:1px;height:1px;left:-10000px';
 document.body.appendChild(frame);
 const cleanup=()=>window.setTimeout(()=>{frame.remove();URL.revokeObjectURL(url)},1000);
 const timer=window.setTimeout(cleanup,120000);
 frame.onload=()=>{try{frame.contentWindow?.addEventListener('afterprint',()=>{window.clearTimeout(timer);cleanup()},{once:true});frame.contentWindow?.focus();frame.contentWindow?.print()}catch{window.clearTimeout(timer);cleanup();onError()}};
 frame.onerror=()=>{window.clearTimeout(timer);cleanup();onError()};frame.src=url;
}

export default function ReceiptQueue({token,canPrint}:{token:string;canPrint:boolean}){
 const [open,setOpen]=useState(false),[filter,setFilter]=useState<Filter>('PENDING');
 const [data,setData]=useState<ReceiptQueueData>(EMPTY),[selected,setSelected]=useState<string[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [preview,setPreview]=useState<{url:string;title:string}|null>(null);const frame=useRef<HTMLIFrameElement>(null);
 useLive(['finance'],()=>load());   // live: what another member records here appears without reloading (2026-11-01)
 async function load(){try{setData(await receiptQueue(token,filter));setError('')}catch(e){setError(friendlyError(e))}}
 useEffect(()=>{void load();const update=()=>void load();window.addEventListener('edusync:receipt-created',update);window.addEventListener('focus',update);const timer=window.setInterval(update,60000);return()=>{window.removeEventListener('edusync:receipt-created',update);window.removeEventListener('focus',update);window.clearInterval(timer)}},[token,filter]);
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url)},[preview?.url]);
 useEffect(()=>{if(!open)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape'){if(preview)setPreview(null);else setOpen(false)}};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[open,preview]);
 const ids=selected.filter(id=>data.items.some(item=>item.payment_id===id));
 async function print(idsToPrint:string[]){if(!idsToPrint.length)return;try{setBusy(true);setError('');const pdf=await receiptQueuePdf(token,idsToPrint);browserPrint(pdf,()=>setError('Le dialogue d’impression ne s’est pas ouvert. Utilisez « Ouvrir » pour imprimer.'));setNotice('Après sortie papier, confirmez chaque reçu. Si l’imprimante est indisponible, laissez-le en attente ou marquez l’échec.')}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
 async function openItem(item:ReceiptQueueItem){try{setBusy(true);const pdf=await receiptQueuePdf(token,[item.payment_id]);setPreview({url:URL.createObjectURL(pdf),title:`Reçu ${item.receipt_number}`})}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
 async function change(item:ReceiptQueueItem,status:'PENDING'|'PRINTED'|'FAILED'){try{setBusy(true);await receiptQueueStatus(token,item.payment_id,status,status==='FAILED'?'Imprimante indisponible ou impression interrompue':undefined);setSelected(ids=>ids.filter(id=>id!==item.payment_id));await load();setNotice(status==='PRINTED'?'Sortie papier confirmée par le caissier.':status==='FAILED'?'Échec conservé pour reprise.':'Reçu remis en attente.')}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
 async function retry(){try{setBusy(true);const failed=data.items.filter(item=>item.status==='FAILED');for(const item of failed)await receiptQueueStatus(token,item.payment_id,'PENDING');await load();setBusy(false);await print(failed.map(item=>item.payment_id))}catch(e){setError(friendlyError(e));setBusy(false)}}
 return <div className="receiptQueueHost"><button type="button" className="receiptQueueBadge" onClick={()=>setOpen(true)} aria-label={`${data.counts.PENDING} reçus en attente d’impression`}>Reçus · <b>{data.counts.PENDING} en attente</b>{data.counts.FAILED>0&&<em>{data.counts.FAILED} échec(s)</em>}</button>
 {/* The drawer is rendered at the root of the page (portal), the standard for dialogs: whatever the badge sits in (a
     header row, a sticky or positioned block), the drawer covers the whole page above the top bar (fix 2026-11-02). */}
 {open&&createPortal(<div className="receiptQueueBackdrop" onMouseDown={e=>e.target===e.currentTarget&&setOpen(false)}><section className="receiptQueueDrawer" role="dialog" aria-modal="true" aria-label="File des reçus"><header><div><h3>File des reçus</h3><small>Un paiement reste valide même si l’impression échoue.</small></div><button type="button" aria-label="Fermer" onClick={()=>setOpen(false)}>×</button></header>
 <nav aria-label="État des reçus">{(['PENDING','PRINTED','FAILED','ALL'] as const).map(state=><button key={state} type="button" className={filter===state?'active':''} onClick={()=>{setFilter(state);setSelected([])}}>{({PENDING:'À imprimer',PRINTED:'Imprimés',FAILED:'Échecs',ALL:'Tous'} as const)[state]}{state!=='ALL'&&` · ${data.counts[state]}`}</button>)}</nav>
 {error&&<p className="receiptQueueError" role="alert">{error}</p>}{notice&&<p className="receiptQueueNotice" role="status">{notice}</p>}
 {canPrint&&<div className="receiptQueueActions"><button type="button" disabled={busy||!ids.length} onClick={()=>void print(ids)}>Imprimer la sélection</button><button type="button" disabled={busy||!data.items.some(item=>item.status!=='PRINTED')} onClick={()=>void print(data.items.filter(item=>item.status!=='PRINTED').map(item=>item.payment_id))}>Imprimer les reçus affichés</button>{filter==='FAILED'&&<button type="button" disabled={busy||!data.items.length} onClick={()=>void retry()}>Réessayer les échecs</button>}</div>}
 <div className="receiptQueueList">{data.items.length===0?<p>Aucun reçu dans cette vue.</p>:data.items.map(item=><article key={item.payment_id}><input type="checkbox" aria-label={`Sélectionner ${item.receipt_number}`} checked={ids.includes(item.payment_id)} onChange={e=>setSelected(current=>e.target.checked?[...current,item.payment_id]:current.filter(id=>id!==item.payment_id))}/><div><b>{item.receipt_number}</b><small>{item.student||'Élève'} · {formatDate(item.queued_at)} · {formatMoney(item.amount,item.currency)}</small><small>{item.status==='PENDING'?'En attente de sortie papier':item.status==='PRINTED'?'Confirmé par le caissier':'Échec à reprendre'}</small></div><div className="receiptQueueRowActions"><button type="button" disabled={busy} onClick={()=>void openItem(item)}>Ouvrir</button>{canPrint&&item.status!=='PRINTED'&&<><button type="button" disabled={busy} onClick={()=>void print([item.payment_id])}>Imprimer</button><button type="button" disabled={busy} onClick={()=>void change(item,'PRINTED')}>Confirmer imprimé</button>{item.status!=='FAILED'&&<button type="button" disabled={busy} onClick={()=>void change(item,'FAILED')}>Échec</button>}</>}</div></article>)}</div>
 {preview&&<div className="receiptQueuePreview"><div><b>{preview.title}</b><button type="button" onClick={()=>setPreview(null)}>← Retour</button>{canPrint&&<button type="button" onClick={()=>frame.current?.contentWindow?.print()}>Imprimer</button>}<a href={preview.url} download={`${preview.title}.pdf`}>Télécharger</a></div><iframe ref={frame} src={preview.url} title={preview.title}/></div>}
 </section></div>,document.body)}</div>
}
