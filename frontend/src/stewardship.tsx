import {friendlyError} from './platform/errors';
import React,{useEffect,useMemo,useState} from 'react';
import {toast} from 'sonner';
import {stewardshipAssetHistory,stewardshipAssets,stewardshipCountDetail,stewardshipCounts,stewardshipDashboard,stewardshipLocations,stewardshipMovements,stewardshipSaleStock,stewardshipStock} from './api';
import './stewardship.css';

/* Intendance — consumables, durable assets, premises, physical inventories.
   Stock only ever moves through traced movements (receipt / issue / justified correction / count variance). */
type Props={token:string;permissions:string[]};
type Tab='overview'|'stock'|'assets'|'sales'|'movements'|'counts';
type MoveKind='RECEIPT'|'ISSUE'|'ADJUSTMENT';
const has=(p:string[],c:string)=>p.includes(c);
const n=(x:any)=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:3}).format(Number(x||0));
const API=import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
async function readError(r:Response){try{const b=await r.json();return typeof b.detail==='string'?b.detail:`Erreur ${r.status}`}catch{return `Erreur ${r.status}`}}
async function send(token:string,method:'POST'|'PUT',path:string,body:unknown):Promise<any>{
  const r=await fetch(`${API}/stewardship/${path}`,{method,headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
  if(!r.ok)throw new Error(await readError(r));return r.json()}

const KIND_FR:Record<string,string>={CONSUMABLE:'Consommable',SALE_PRODUCT:'Article vendu'};
const MOVE_FR:Record<string,{l:string;tone:string}>={RECEIPT:{l:'Entrée',tone:'in'},ISSUE:{l:'Sortie',tone:'out'},ADJUSTMENT:{l:'Correction',tone:'adj'},COUNT_ADJUSTMENT:{l:'Écart d’inventaire',tone:'adj'},SALE:{l:'Vente',tone:'out'}};
const COUNT_FR:Record<string,string>={DRAFT:'En cours',VALIDATED:'Validé'};
const ASSET_FR:Record<string,string>={GOOD:'Bon état',TO_REPAIR:'À réparer',IN_REPAIR:'En réparation',OUT_OF_SERVICE:'Hors service',LOST:'Perdu',DISPOSED:'Sorti du patrimoine',ACTIVE:'Actif',INACTIVE:'Inactif'};
const fr=(m:Record<string,string>,v:any)=>m[String(v)]??v;

export default function StewardshipPage({token,permissions}:Props){
  const [tab,setTab]=useState<Tab>('overview'),[data,setData]=useState<any>({}),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const [move,setMove]=useState<{item:any;kind:MoveKind}|null>(null),[newItem,setNewItem]=useState(false),[countId,setCountId]=useState<string|null>(null);
  const canStock=has(permissions,'inventory.stock.read'),canAssets=has(permissions,'inventory.assets.read'),canCounts=has(permissions,'inventory.counts.read');
  // 2026-10-28: the asset history right had no screen; each durable asset now opens its dated changes.
  const canHistory=has(permissions,'inventory.assets.history.read');const [historyOf,setHistoryOf]=useState<any|null>(null);
  const canMoves=has(permissions,'inventory.stock.movements.read'),canItem=has(permissions,'inventory.stock.item.manage');
  const can={RECEIPT:has(permissions,'inventory.stock.receive'),ISSUE:has(permissions,'inventory.stock.issue'),ADJUSTMENT:has(permissions,'inventory.stock.adjust')};
  async function load(){try{setError('');const d:any={};d.dashboard=await stewardshipDashboard(token);
    if(canStock){d.stock=await stewardshipStock(token);d.movements=canMoves?await stewardshipMovements(token):{items:[]};d.sales=await stewardshipSaleStock(token)}
    if(canAssets){d.assets=await stewardshipAssets(token);d.locations=await stewardshipLocations(token)}
    if(canCounts)d.counts=await stewardshipCounts(token);setData(d)}catch(e){setError(friendlyError(e))}finally{setLoading(false)}}
  useEffect(()=>{void load()},[token]);
  const tabs:[Tab,string,boolean][]=[['overview','Vue d’ensemble',true],['stock','Consommables',canStock],['assets','Patrimoine & locaux',canAssets],['sales','Articles vendus',canStock],['movements','Entrées & sorties',canMoves],['counts','Inventaires physiques',canCounts]];
  const items=(data.stock?.items??[]) as any[];
  async function newCount(){try{const r=await send(token,'POST','counts',{notes:'Inventaire physique'});toast.success('Inventaire ouvert : saisissez les quantités comptées');await load();setCountId(r.id)}catch(e){toast.error(e instanceof Error?e.message:friendlyError(e))}}
  return <div className="stewardship personnelPage pageEnter">
    <div className="personnelHero stewardHero"><div><span className="eyebrow">Logistique & patrimoine</span><h2>Intendance</h2><p>Consommables, patrimoine, locaux et inventaires. Chaque entrée, sortie ou correction est tracée et motivée.</p></div>
      <div className="heroActions">{canItem&&<button className="softBtn" onClick={()=>setNewItem(true)}>＋ Nouvel article</button>}{has(permissions,'inventory.counts.create')&&<button className="primaryBtn" onClick={()=>void newCount()}>Nouvel inventaire</button>}</div></div>
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="personTabs" role="tablist">{tabs.filter(x=>x[2]).map(x=><button role="tab" aria-selected={tab===x[0]} className={tab===x[0]?'active':''} onClick={()=>setTab(x[0])} key={x[0]}>{x[1]}</button>)}</div>

    {tab==='overview'&&<><div className="homeKpis"><K l="Locaux" v={(data.dashboard?.locations??[]).reduce((a:any,x:any)=>a+Number(x.n),0)}/><K l="Biens durables" v={(data.dashboard?.assets??[]).reduce((a:any,x:any)=>a+Number(x.n),0)}/><K l="Stocks faibles" v={data.dashboard?.low_stock?.length??0}/><K l="Articles vendus suivis" v={data.dashboard?.sale_stock?.length??0}/></div>
      <section className="homePanel"><h3>À votre attention</h3>{data.dashboard?.low_stock?.length?<Table heads={['Article','Disponible','Seuil']} rows={data.dashboard.low_stock.map((x:any)=>[x.label,`${n(x.quantity)} ${x.unit}`,n(x.low_threshold)])}/>:<p className="okState">✓ Aucun stock consommable sous le seuil configuré</p>}</section></>}

    {tab==='stock'&&<section className="homePanel"><div className="stewardHead"><h3>Stock consommable</h3><small>{items.length} article{items.length>1?'s':''}</small></div>
      {items.length?<div className="stockList">{items.map((x:any)=>{const low=Number(x.quantity)<=Number(x.low_threshold);return <article key={x.id} className={`stockRow ${low?'low':''}`}>
        <div className="stockIdentity"><b>{x.label}</b><small>{x.code} · {fr(KIND_FR,x.item_kind)}{x.location_label?` · ${x.location_label}`:''}</small></div>
        <div className="stockQty"><b>{n(x.quantity)}</b><small>{x.unit}{low?' · stock faible':''}</small></div>
        <div className="stockActions">{can.RECEIPT&&<button className="moveBtn in" onClick={()=>setMove({item:x,kind:'RECEIPT'})}>Entrée</button>}{can.ISSUE&&<button className="moveBtn out" onClick={()=>setMove({item:x,kind:'ISSUE'})} disabled={Number(x.quantity)<=0}>Sortie</button>}{can.ADJUSTMENT&&<button className="moveBtn adj" onClick={()=>setMove({item:x,kind:'ADJUSTMENT'})}>Corriger</button>}</div>
      </article>})}</div>:<div className="emptyState"><b>Aucun article de stock</b><span>{canItem?'Créez votre premier article (craie, papier, produits d’entretien…), puis enregistrez une entrée.':'Aucun article n’est encore enregistré.'}</span>{canItem&&<button className="primaryBtn compact" onClick={()=>setNewItem(true)}>Créer un article</button>}</div>}
    </section>}

    {tab==='assets'&&<><section className="homePanel"><h3>Patrimoine durable</h3><Table heads={['Bien','Quantité','État','Localisation',...(canHistory?['Historique']:[])]} rows={(data.assets?.items??[]).map((x:any)=>[x.asset_type,n(x.quantity),fr(ASSET_FR,x.status),x.location_label??'—',...(canHistory?[<button key="h" type="button" className="softBtn" onClick={()=>setHistoryOf(x)}>Voir l’historique</button>]:[])])}/>{!(data.assets?.items??[]).length&&<p className="okState">Aucun bien durable enregistré.</p>}</section>{historyOf&&<AssetHistory token={token} asset={historyOf} onClose={()=>setHistoryOf(null)}/>}
      <section className="homePanel"><h3>Locaux</h3><Table heads={['Local','Type','Capacité','État']} rows={(data.locations?.items??[]).map((x:any)=>[x.label,x.location_type,x.capacity??'—',fr(ASSET_FR,x.status)])}/>{!(data.locations?.items??[]).length&&<p className="okState">Aucun local enregistré.</p>}</section></>}
    {tab==='sales'&&<section className="homePanel"><h3>Articles destinés à la vente</h3><p className="muted">L’Intendance gère le stock ; le Centre financier encaisse les ventes.</p><Table heads={['Article','Disponible','Seuil','Prix courant']} rows={(data.sales?.items??[]).map((x:any)=>[x.label,n(x.quantity),n(x.low_threshold),`${n(x.unit_price)} ${x.currency}`])}/></section>}
    {tab==='movements'&&<section className="homePanel"><h3>Traçabilité des entrées et sorties</h3><Table heads={['Date','Article','Mouvement','Quantité','Destination','Motif']} rows={(data.movements?.items??[]).map((x:any)=>{const m=MOVE_FR[x.movement_type]??{l:x.movement_type,tone:'adj'};return [String(x.created_at).slice(0,16).replace('T',' '),x.item_label,<i className={`movePill ${m.tone}`}>{m.l}</i>,<b className={Number(x.quantity_delta)<0?'neg':'pos'}>{Number(x.quantity_delta)>0?'+':''}{n(x.quantity_delta)} {x.unit}</b>,x.destination??'—',x.reason]})}/>{!(data.movements?.items??[]).length&&<p className="okState">Aucun mouvement enregistré.</p>}</section>}
    {tab==='counts'&&<section className="homePanel"><div className="stewardHead"><h3>Inventaires physiques</h3>{has(permissions,'inventory.counts.create')&&<button className="primaryBtn compact" onClick={()=>void newCount()}>Nouvel inventaire</button>}</div><p className="muted">Comptez le stock réel, justifiez chaque écart, puis validez. Une validation est définitive et tracée.</p>
      <Table heads={['Référence','Date','État','Lignes','Écart cumulé','']} rows={(data.counts?.items??[]).map((x:any)=>[x.code,String(x.counted_on??x.created_at??'').slice(0,10),<i className={`countPill ${String(x.status).toLowerCase()}`}>{fr(COUNT_FR,x.status)}</i>,x.line_count,n(x.total_variance),<button className="textBtn" onClick={()=>setCountId(x.id)}>{x.status==='DRAFT'&&has(permissions,'inventory.counts.record')?'Compter':'Voir'}</button>])}/>{!(data.counts?.items??[]).length&&<p className="okState">Aucun inventaire physique enregistré.</p>}</section>}
    {loading&&<div className="thinLoader"><i/></div>}
    {move&&<MoveDialog token={token} item={move.item} kind={move.kind} onClose={()=>setMove(null)} onDone={async()=>{setMove(null);await load()}}/>}
    {newItem&&<ItemDialog token={token} onClose={()=>setNewItem(false)} onDone={async()=>{setNewItem(false);setTab('stock');await load()}}/>}
    {countId&&<CountSheet token={token} id={countId} items={items} canRecord={has(permissions,'inventory.counts.record')} canValidate={has(permissions,'inventory.counts.validate')} onClose={async()=>{setCountId(null);await load()}}/>}
  </div>;
}

function MoveDialog({token,item,kind,onClose,onDone}:{token:string;item:any;kind:MoveKind;onClose:()=>void;onDone:()=>Promise<void>}){
  const [qty,setQty]=useState(''),[reason,setReason]=useState(''),[dest,setDest]=useState(''),[dir,setDir]=useState<'INCREASE'|'DECREASE'>('DECREASE'),[busy,setBusy]=useState(false);
  const q=Number(qty.replace(',','.'))||0;const cur=Number(item.quantity);
  const after=kind==='RECEIPT'?cur+q:kind==='ISSUE'?cur-q:dir==='INCREASE'?cur+q:cur-q;
  const title={RECEIPT:'Entrée de stock',ISSUE:'Sortie de stock',ADJUSTMENT:'Correction de stock'}[kind];
  const ok=q>0&&after>=0&&reason.trim().length>=3;
  async function save(){if(!ok)return;try{setBusy(true);
    await send(token,'POST','stock/movements',{item_id:item.id,movement_type:kind,quantity:String(q),reason:reason.trim(),destination:kind==='ISSUE'&&dest.trim()?dest.trim():null,adjustment_direction:kind==='ADJUSTMENT'?dir:null});
    toast.success(`${title} enregistrée · ${item.label} : ${n(after)} ${item.unit}`);await onDone()}catch(e){toast.error(e instanceof Error?e.message:friendlyError(e))}finally{setBusy(false)}}
  return <div className="wizardBackdrop" onClick={onClose}><div className="accountSecurityDialog stewardDialog" role="dialog" aria-modal="true" aria-label={title} onClick={e=>e.stopPropagation()}>
    <div className="modalHead"><div><h3>{title}</h3><p>{item.label} · stock actuel <b>{n(cur)} {item.unit}</b></p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    {kind==='ADJUSTMENT'&&<div className="fieldGroup"><span>Sens de la correction</span><div className="stewardSegmented" role="radiogroup"><button type="button" role="radio" aria-checked={dir==='INCREASE'} className={dir==='INCREASE'?'on':''} onClick={()=>setDir('INCREASE')}>Augmenter</button><button type="button" role="radio" aria-checked={dir==='DECREASE'} className={dir==='DECREASE'?'on':''} onClick={()=>setDir('DECREASE')}>Diminuer</button></div></div>}
    <label>Quantité ({item.unit}) *<input inputMode="decimal" value={qty} onChange={e=>setQty(e.target.value)} autoFocus aria-label="Quantité"/></label>
    {kind==='ISSUE'&&<label>Destination<input value={dest} onChange={e=>setDest(e.target.value)} placeholder="Ex. classe de 3e année, secrétariat…" aria-label="Destination"/></label>}
    <label>Motif *<textarea rows={2} value={reason} onChange={e=>setReason(e.target.value)} placeholder={kind==='RECEIPT'?'Ex. livraison fournisseur du jour':kind==='ISSUE'?'Ex. distribution aux enseignants':'Ex. erreur de saisie constatée'} aria-label="Motif"/></label>
    <div className={`afterPreview ${after<0?'bad':''}`}>Stock après mouvement : <b>{n(Math.max(after,0))} {item.unit}</b>{after<0&&<span> — impossible : le stock ne peut pas devenir négatif</span>}</div>
    <div className="modalActions"><button className="ghost" onClick={onClose}>Annuler</button><button disabled={busy||!ok} onClick={()=>void save()}>{busy?'Enregistrement…':'Enregistrer'}</button></div>
  </div></div>;
}

function ItemDialog({token,onClose,onDone}:{token:string;onClose:()=>void;onDone:()=>Promise<void>}){
  const [code,setCode]=useState(''),[label,setLabel]=useState(''),[unit,setUnit]=useState(''),[threshold,setThreshold]=useState('0'),[busy,setBusy]=useState(false);
  const ok=code.trim()&&label.trim().length>=2&&unit.trim();
  async function save(){if(!ok)return;try{setBusy(true);await send(token,'POST','items',{code:code.trim(),label:label.trim(),unit:unit.trim(),low_threshold:String(Number(threshold.replace(',','.'))||0)});toast.success('Article créé — enregistrez maintenant une entrée de stock');await onDone()}catch(e){toast.error(e instanceof Error?e.message:friendlyError(e))}finally{setBusy(false)}}
  return <div className="wizardBackdrop" onClick={onClose}><div className="accountSecurityDialog stewardDialog" role="dialog" aria-modal="true" aria-label="Nouvel article" onClick={e=>e.stopPropagation()}>
    <div className="modalHead"><div><h3>Nouvel article de stock</h3><p>Le stock démarre à zéro ; il augmente ensuite par une entrée tracée.</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    <div className="stewardGrid"><label>Code *<input value={code} onChange={e=>setCode(e.target.value)} placeholder="Ex. CRAIE-B" aria-label="Code article" autoFocus/></label><label>Unité *<input value={unit} onChange={e=>setUnit(e.target.value)} placeholder="boîte, rame, litre…" aria-label="Unité"/></label></div>
    <label>Désignation *<input value={label} onChange={e=>setLabel(e.target.value)} placeholder="Ex. Craie blanche" aria-label="Désignation"/></label>
    <label>Seuil d’alerte<input inputMode="decimal" value={threshold} onChange={e=>setThreshold(e.target.value)} aria-label="Seuil d’alerte"/></label>
    <div className="modalActions"><button className="ghost" onClick={onClose}>Annuler</button><button disabled={busy||!ok} onClick={()=>void save()}>{busy?'Création…':'Créer l’article'}</button></div>
  </div></div>;
}

function CountSheet({token,id,items,canRecord,canValidate,onClose}:{token:string;id:string;items:any[];canRecord:boolean;canValidate:boolean;onClose:()=>void}){
  const [count,setCount]=useState<any>(null),[entries,setEntries]=useState<Record<string,{q:string;r:string}>>({}),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false);
  async function load(){try{const d=await stewardshipCountDetail(token,id);setCount(d);const e:Record<string,{q:string;r:string}>={};(d.items??[]).forEach((l:any)=>{e[l.item_id]={q:String(Number(l.counted_quantity)),r:l.reason??''}});setEntries(x=>({...e,...x}))}catch(err){toast.error(friendlyError(err))}}
  useEffect(()=>{void load()},[id]);
  const head=count?.count;
  const draft=head?.status==='DRAFT';
  const rows=useMemo(()=>items.map(it=>{const e=entries[it.id];const counted=e&&e.q!==''?Number(e.q.replace(',','.')):null;const variance=counted===null?null:counted-Number(it.quantity);return {it,e,counted,variance}}),[items,entries]);
  const missingReason=rows.some(r=>r.variance!==null&&r.variance!==0&&!(r.e?.r??'').trim());
  async function saveAll(){try{setBusy(true);for(const r of rows){if(r.counted===null)continue;await send(token,'POST',`counts/${id}/lines`,{item_id:r.it.id,counted_quantity:String(r.counted),reason:(r.e?.r??'').trim()||null})}toast.success('Comptage enregistré');await load()}catch(e){toast.error(e instanceof Error?e.message:friendlyError(e))}finally{setBusy(false)}}
  async function validate(){try{setBusy(true);await saveAll();await send(token,'POST',`counts/${id}/validate`,{});toast.success('Inventaire validé — écarts appliqués au stock');setConfirm(false);onClose()}catch(e){toast.error(e instanceof Error?e.message:friendlyError(e))}finally{setBusy(false)}}
  const set=(itemId:string,k:'q'|'r',v:string)=>setEntries(x=>({...x,[itemId]:{q:x[itemId]?.q??'',r:x[itemId]?.r??'',[k]:v}}));
  return <div className="wizardBackdrop" onClick={onClose}><div className="accountSecurityDialog countSheet" role="dialog" aria-modal="true" aria-label="Inventaire physique" onClick={e=>e.stopPropagation()}>
    <div className="modalHead"><div><h3>Inventaire {head?.code??''}</h3><p>{draft?'Saisissez la quantité réellement comptée. Tout écart doit être justifié.':'Inventaire validé — lecture seule.'}</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    <div className="countTable"><div className="countRow head"><span>Article</span><span>Théorique</span><span>Compté</span><span>Écart</span><span>Justification</span></div>
      {(draft?rows:(count?.items??[]).map((l:any)=>({it:{id:l.item_id,label:l.item_label,unit:l.unit,quantity:l.theoretical_quantity},e:{q:String(Number(l.counted_quantity)),r:l.reason??''},counted:Number(l.counted_quantity),variance:Number(l.variance)}))).map((r:any)=><div key={r.it.id} className="countRow">
        <span className="countItem"><b>{r.it.label}</b><small>{r.it.unit}</small></span><span>{n(r.it.quantity)}</span>
        <span>{draft&&canRecord?<input inputMode="decimal" value={r.e?.q??''} onChange={e=>set(r.it.id,'q',e.target.value)} aria-label={`Quantité comptée — ${r.it.label}`}/>:n(r.counted)}</span>
        <span className={r.variance===null||r.variance===0?'':r.variance<0?'neg':'pos'}>{r.variance===null?'—':`${r.variance>0?'+':''}${n(r.variance)}`}</span>
        <span>{draft&&canRecord?<input value={r.e?.r??''} onChange={e=>set(r.it.id,'r',e.target.value)} placeholder={r.variance?'Obligatoire':'—'} aria-label={`Justification — ${r.it.label}`} className={r.variance&&!(r.e?.r??'').trim()?'needed':''}/>:(r.e?.r||'—')}</span>
      </div>)}
    </div>
    {draft&&missingReason&&<p className="afterPreview bad">Justifiez chaque écart avant de valider.</p>}
    <div className="modalActions">{draft&&canRecord&&<button className="ghost" disabled={busy} onClick={()=>void saveAll()}>Enregistrer le comptage</button>}{draft&&canValidate&&<button disabled={busy||missingReason||!rows.some(r=>r.counted!==null)} onClick={()=>setConfirm(true)}>Valider l’inventaire</button>}{!draft&&<button onClick={onClose}>Fermer</button>}</div>
    {confirm&&<div className="confirmStrip" role="alertdialog" aria-label="Confirmer la validation"><span>La validation applique les écarts au stock et ne peut pas être annulée.</span><button className="ghost" onClick={()=>setConfirm(false)}>Revenir</button><button disabled={busy} onClick={()=>void validate()}>{busy?'Validation…':'Confirmer la validation'}</button></div>}
  </div></div>;
}
function K({l,v}:{l:string;v:any}){return <div className="homeKpi"><small>{l}</small><b>{n(v)}</b></div>}
function Table({heads,rows}:{heads:string[];rows:any[][]}){return <div className="compactTable"><div className="tr th" style={{gridTemplateColumns:`repeat(${heads.length},minmax(0,1fr))`}}>{heads.map((h,i)=><span key={i}>{h}</span>)}</div>{rows.map((r,i)=><div className="tr" style={{gridTemplateColumns:`repeat(${heads.length},minmax(0,1fr))`}} key={i}>{r.map((v,j)=><span key={j}>{v}</span>)}</div>)}</div>}

const EVENT_FR:Record<string,string>={CREATED:'Bien enregistré',STATUS_CHANGED:'Changement d’état',MOVED:'Changement de localisation',REPAIR:'Réparation',DISPOSED:'Sortie du patrimoine'};
function AssetHistory({token,asset,onClose}:{token:string;asset:any;onClose:()=>void}){
  const [items,setItems]=useState<any[]|null>(null),[error,setError]=useState('');
  useEffect(()=>{stewardshipAssetHistory(token,asset.id).then(r=>setItems(r.items)).catch(e=>setError(friendlyError(e)))},[token,asset]);
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
  return <div className="wizardBackdrop" onClick={onClose}><aside className="sj-drawer" role="dialog" aria-modal="true" aria-label={`Historique : ${asset.asset_type}`} onClick={e=>e.stopPropagation()}>
    <header><div><small>Patrimoine durable</small><h3>{asset.asset_type}</h3><p>Chaque changement d’état ou de localisation, du plus récent au plus ancien.</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></header>
    {error&&<div className="error" role="alert">{error}</div>}
    {!items&&!error&&<p>Chargement…</p>}
    {items&&items.length===0&&<p className="okState">Aucun changement enregistré pour ce bien.</p>}
    {items&&items.length>0&&<ol className="sj-timeline">{items.map(i=><li key={i.id}><b>{EVENT_FR[i.event_type]??i.event_type}</b>
      <small>{new Date(i.created_at).toLocaleString('fr-FR',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})}</small>
      {(i.from_status||i.to_status)&&<small>État : {fr(ASSET_FR,i.from_status)||'—'} → {fr(ASSET_FR,i.to_status)||'—'}</small>}
      {i.reason&&<small>Motif : « {i.reason} »</small>}</li>)}</ol>}
  </aside></div>;
}
