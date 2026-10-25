import {useEffect,useState} from 'react';
import {importBatchHistory,importControlReport,ImportBatchItem} from './api';
import {exportManaged} from './document_io';
import {friendlyError} from './platform/errors';

type Kind='students'|'staff'|'finance-history';
export function ImportHistory({token,kind}:{token:string;kind:Kind}){
 const [items,setItems]=useState<ImportBatchItem[]>([]),[total,setTotal]=useState(0),[offset,setOffset]=useState(0),[err,setErr]=useState('');const limit=20;
 async function load(next=0){try{const r=await importBatchHistory(token,kind,next,limit);setItems(r.items);setTotal(r.total);setOffset(next);setErr('')}catch(e){setErr(friendlyError(e))}}
 useEffect(()=>{void load(0)},[token,kind]);
 // An analysis or an import elsewhere on the page (guided stepper) refreshes the register at once (2026-10-25).
 useEffect(()=>{const h=()=>{void load(0)};window.addEventListener('edusync:import-changed',h);return()=>window.removeEventListener('edusync:import-changed',h)},[token,kind]);
 async function report(x:ImportBatchItem){try{await exportManaged(await importControlReport(token,kind,x.id),{school:'EduSync École',module:'Import',category:'Contrôles',filename:`controle_${kind}_${x.id}.xlsx`})}catch(e){setErr(friendlyError(e))}}
 return <section className="importHistory"><div className="cardHead"><div><h3>Historique des imports</h3><p>Chaque analyse reste traçable. Le rapport Excel explique ligne par ligne les erreurs et avertissements.</p></div><button className="softBtn" onClick={()=>load(offset)}>Actualiser</button></div>{err&&<div className="error">{err}</div>}<div className="mobileTableScroll"><table className="importPreview"><thead><tr><th>Date</th><th>Fichier</th><th>Statut</th><th>Total</th><th>Valides</th><th>Avert.</th><th>Erreurs</th><th>Contrôle</th></tr></thead><tbody>{items.map(x=><tr key={x.id}><td>{new Date(x.created_at).toLocaleString('fr-FR')}</td><td><b>{x.filename}</b></td><td>{x.status}</td><td>{x.total_rows}</td><td>{x.valid_rows}</td><td>{x.warning_rows}</td><td>{x.error_rows}</td><td><button className="softBtn" onClick={()=>report(x)}>Rapport XLSX</button></td></tr>)}{!items.length&&<tr><td colSpan={8}>Aucun lot d’import.</td></tr>}</tbody></table></div>{total>limit&&<div className="pager"><button disabled={offset===0} onClick={()=>load(Math.max(0,offset-limit))}>Précédent</button><span>{offset+1}–{Math.min(offset+limit,total)} / {total}</span><button disabled={offset+limit>=total} onClick={()=>load(offset+limit)}>Suivant</button></div>}</section>
}
