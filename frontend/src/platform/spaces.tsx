import {OnlineActionButton} from './online_action';
/* Change of space without signing out (lot 2026-10).

   One identity, several spaces (the platform console, one or more schools), one persistent session. The server is
   the source of truth: GET /auth/contexts lists the spaces open now, POST /auth/switch checks the target again,
   recomputes the permissions and replaces the device session (the previous access token dies at once). The client
   only forgets the previous space and mounts the new one from the server's answer: nothing of the previous space
   (data, permissions, menu) survives the switch. */
import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Modal} from './account';
import {NavGlyph} from './nav_icons';
import {getConnectivity,nativeFetch,subscribeConnectivity,type ConnectivityState} from './connectivity';
import {hasUnsavedForms} from './mobile_back';
import {confirmAction} from './dialogs';
import {mfaVerify,MfaError,isMfaStep,type MfaStep} from '../api';
import './spaces.css';
import {getPlatformAuthState, platformLastRead} from './offline_session';

export type Space={scope:'PLATFORM'|'SCHOOL';school_code:string|null;label:string;roles:string[];current:boolean};
export type SpacesState={contexts:Space[];current:{scope:'PLATFORM'|'SCHOOL';school_code:string|null};current_valid:boolean};
export const spaceKey=(s:{scope:string;school_code?:string|null})=>s.scope==='PLATFORM'?'PLATFORM':`SCHOOL:${(s.school_code||'').toUpperCase()}`;
const LAST_SPACE='edusync.last.space';
export function rememberSpace(key:string){try{localStorage.setItem(LAST_SPACE,key)}catch{/* préférence locale facultative */}}
export function lastSpace():string{try{return localStorage.getItem(LAST_SPACE)||''}catch{return ''}}

class SwitchError extends Error{constructor(public status:number,message:string){super(message)}}

/** Spaces open to this identity now (null: no live session in this browser). */
export async function fetchSpaces():Promise<SpacesState|null>{
  const r=await nativeFetch('/api/v1/auth/contexts',{credentials:'include',cache:'no-store'});
  if(r.status===401)return null;
  if(!r.ok)throw new SwitchError(r.status,'Liste des espaces indisponible.');
  return r.json();
}

export async function switchSpace(target:{scope:'PLATFORM'|'SCHOOL';school_code?:string|null}):Promise<any>{
  let r:Response;
  try{r=await nativeFetch('/api/v1/auth/switch',{method:'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope:target.scope,school_code:target.school_code||null})})}
  catch{throw new SwitchError(0,'Le serveur ne répond pas. Vérifiez votre connexion puis réessayez.')}
  if(r.status===401)throw new SwitchError(401,'Votre session a expiré. Reconnectez-vous.');
  if(r.status===403)throw new SwitchError(403,'Cet espace ne vous est plus ouvert. Choisissez-en un autre.');
  if(!r.ok)throw new SwitchError(r.status,'Changement d’espace impossible pour le moment. Réessayez dans un instant.');
  return r.json();
}

function useOnline(){const [s,setS]=useState<ConnectivityState>(getConnectivity().state);useEffect(()=>subscribeConnectivity(x=>setS(x.state)),[]);return s!=='OFFLINE'}

function SpaceRow({s,busy,disabled,last,onPick}:{s:Space;busy:boolean;disabled:boolean;last:boolean;onPick:()=>void}){
  const pf=s.scope==='PLATFORM';
  return <li><button type="button" className={`sp-row ${s.current?'sp-current':''}`} disabled={disabled||s.current} aria-current={s.current?'true':undefined} onClick={onPick}>
    <span className={`sp-ico ${pf?'sp-pf':''}`}><NavGlyph g={pf?'shield':'school'} size={18}/></span>
    <span className="sp-txt"><b>{pf?'Plateforme EduSync':s.label}</b>
      <small>{pf?'Administration de la plateforme':`Établissement · ${s.school_code}`}</small>
      {s.roles.length>0&&<small className="sp-roles">{s.roles.join(' · ')}</small>}</span>
    {s.current?<em className="sp-badge">Espace actuel</em>:busy?<i className="sp-spin" aria-label="Ouverture…"/>:last?<em className="sp-badge sp-badge-soft">Récent</em>:<NavGlyph g="chevronRight" size={18}/>}
  </button></li>;
}

/** "Changer d’espace": list, search when many, unsaved-changes confirmation, offline guard, second factor if the target asks for it. */
export function SpaceSwitcher({onClose,onSwitched,reason}:{onClose:()=>void;onSwitched:(r:any)=>void;reason?:string}){
  const [state,setState]=useState<SpacesState|null|undefined>(undefined);
  const [error,setError]=useState('');const [busy,setBusy]=useState('');const [q,setQ]=useState('');
  const [mfa,setMfa]=useState<MfaStep|null>(null);
  const online=useOnline();
  const last=useRef(lastSpace());
  const load=()=>{setError('');setState(undefined);fetchSpaces().then(setState).catch(e=>{setError(e.message);setState(null)})};
  useEffect(load,[]);
  const items=useMemo(()=>{const all=state?.contexts||[];const n=q.trim().toLowerCase();
    const f=n?all.filter(s=>`${s.label} ${s.school_code||''} ${s.roles.join(' ')} ${s.scope==='PLATFORM'?'plateforme edusync':''}`.toLowerCase().includes(n)):all;
    // current first, then the platform, then schools by name
    return [...f].sort((a,b)=>Number(b.current)-Number(a.current)||Number(b.scope==='PLATFORM')-Number(a.scope==='PLATFORM')||a.label.localeCompare(b.label,'fr'))},[state,q]);
  async function pick(s:Space){
    if(!online){setError('Hors connexion — le changement d’espace reprendra quand la connexion reviendra.');return}
    if(hasUnsavedForms()&&!await confirmAction({title:'Modifications non enregistrées',message:'Un formulaire contient des modifications non enregistrées. Elles seront perdues si vous changez d’espace.',confirmLabel:'Changer d’espace',danger:true}))return;
    setError('');setBusy(spaceKey(s));
    try{const r=await switchSpace(s);if(isMfaStep(r)){setMfa(r);return}rememberSpace(spaceKey(s));onSwitched(r)}
    catch(e){const err=e as SwitchError;setError(err.message);if(err.status===403)load();if(err.status===401)onSwitched(null)}
    finally{setBusy('')}
  }
  if(mfa)return <SwitchMfa step={mfa} onCancel={()=>setMfa(null)} onDone={r=>{rememberSpace(spaceKey({scope:mfa.scope,school_code:r?.school?.code}));onSwitched(r)}}/>;
  const many=(state?.contexts.length||0)>6;
  return <Modal title="Changer d’espace" subtitle={reason||'Votre compte donne accès à plusieurs espaces. Vous restez connecté : ni mot de passe ni code à ressaisir.'} onClose={onClose}>
    <div className="sp-body">
      {!online&&<div className="es-alert es-alert-warn" role="status"><NavGlyph g="wifiOff" size={16}/><span>Hors connexion — changement d’espace indisponible.</span></div>}
      {many&&<label className="sp-search"><NavGlyph g="search" size={16}/><input type="search" placeholder="Rechercher un espace" aria-label="Rechercher un espace" value={q} onChange={e=>setQ(e.target.value)}/></label>}
      {state===undefined&&<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
      {state&&<ul className="sp-list">{items.map(s=><SpaceRow key={spaceKey(s)} s={s} busy={busy===spaceKey(s)} disabled={!!busy||!online} last={!s.current&&last.current===spaceKey(s)} onPick={()=>void pick(s)}/>)}</ul>}
      {state&&items.length===0&&<p className="sp-empty">Aucun espace ne correspond à « {q} ».</p>}
      {state&&!state.current_valid&&<p className="sp-note"><NavGlyph g="info" size={14}/>L’accès à votre espace actuel n’est plus actif.</p>}
      {error&&<div className="es-alert es-alert-bad" role="alert"><NavGlyph g="alert" size={16}/><span>{error}</span></div>}
      <p className="sp-foot"><NavGlyph g="lock" size={14}/>Les droits de chaque espace sont vérifiés par le serveur : un rôle plateforme n’ouvre aucune école, un rôle d’école n’ouvre pas la plateforme.</p>
    </div>
  </Modal>;
}

/** The target space asks for the second factor (rare: the current session was opened without it). */
function SwitchMfa({step,onCancel,onDone}:{step:MfaStep;onCancel:()=>void;onDone:(r:any)=>void}){
  const [code,setCode]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);const sent=useRef('');
  if(step.mfa_enrollment_required)return <Modal title="Validation en deux étapes à configurer" onClose={onCancel}>
    <p className="sp-note">Cet espace exige la validation en deux étapes, qui n’est pas encore configurée sur votre compte. Déconnectez-vous puis ouvrez cet espace depuis l’écran de connexion pour la configurer.</p>
    <div className="es-modal-foot"><OnlineActionButton type="button" className="es-btn es-btn-primary" onClick={onCancel}>Compris</OnlineActionButton></div></Modal>;
  async function confirm(value=code){
    if(busy)return;setError('');
    if(!/^\d{6}$/.test(value)){setError('Saisissez les 6 chiffres affichés par votre application.');return}
    try{setBusy(true);onDone(await mfaVerify(step.mfa_token,{code:value}))}
    catch(e){setError(e instanceof MfaError?e.message:'Vérification impossible pour le moment.');setCode('');sent.current=''}
    finally{setBusy(false)}
  }
  return <Modal title="Confirmez avec votre code" subtitle="Cet espace demande le code à 6 chiffres de votre application d’authentification." onClose={onCancel}>
    <form className="es-form" onSubmit={e=>{e.preventDefault();void confirm()}} noValidate>
      <label className="sp-code"><span>Code de vérification</span><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} value={code} disabled={busy} aria-invalid={!!error}
        onChange={e=>{const v=e.target.value.replace(/\D/g,'').slice(0,6);setCode(v);if(v.length===6&&sent.current!==v){sent.current=v;void confirm(v)}}}/></label>
      {error&&<div className="es-alert es-alert-bad" role="alert"><NavGlyph g="alert" size={16}/><span>{error}</span></div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onCancel}>Annuler</button><OnlineActionButton className="es-btn es-btn-primary" disabled={busy}>{busy?'Vérification…':'Confirmer'}</OnlineActionButton></div>
    </form>
  </Modal>;
}

/** Full-page recovery when the space of the session was withdrawn (membership ended, school suspended, role revoked):
    the identity stays signed in and picks another space, or signs out. */
export function SpaceRecovery({spaces,onSwitched,onLogout}:{spaces:SpacesState;onSwitched:(r:any)=>void;onLogout:()=>void}){
  const [error,setError]=useState('');const [busy,setBusy]=useState('');
  const online=useOnline();
  const others=spaces.contexts.filter(s=>!s.current).sort((a,b)=>Number(b.scope==='PLATFORM')-Number(a.scope==='PLATFORM')||a.label.localeCompare(b.label,'fr'));
  async function pick(s:Space){setError('');setBusy(spaceKey(s));try{const r=await switchSpace(s);if(isMfaStep(r)){setError('Cet espace demande une nouvelle connexion.');return}rememberSpace(spaceKey(s));onSwitched(r)}
    catch(e){setError((e as Error).message)}finally{setBusy('')}}
  return <div className="sp-recovery" role="main"><div className="sp-card">
    <span className="sp-recovery-ico"><NavGlyph g="lock" size={22}/></span>
    <h1>Accès à cet espace retiré</h1>
    <p>Votre accès à l’espace que vous utilisiez n’est plus actif. Vous restez connecté : choisissez un autre espace.</p>
    {!online&&<div className="es-alert es-alert-warn" role="status"><NavGlyph g="wifiOff" size={16}/><span>Hors connexion.</span></div>}
    <ul className="sp-list">{others.map(s=><SpaceRow key={spaceKey(s)} s={s} busy={busy===spaceKey(s)} disabled={!!busy||!online} last={false} onPick={()=>void pick(s)}/>)}</ul>
    {others.length===0&&<p className="sp-note">Aucun autre espace ne vous est ouvert pour le moment.</p>}
    {error&&<div className="es-alert es-alert-bad" role="alert"><NavGlyph g="alert" size={16}/><span>{error}</span></div>}
    <button type="button" className="es-btn es-btn-ghost sp-logout" onClick={onLogout}>Se déconnecter</button>
  </div></div>;
}

/** Platform administration is online-only: an explicit banner instead of buttons that fail one by one. */
export function OfflineAdminBanner(){
  const online=useOnline();
  const [auth,setAuth]=useState(getPlatformAuthState);
  const [readAt,setReadAt]=useState(platformLastRead);
  useEffect(()=>{const authChange=()=>setAuth(getPlatformAuthState());const cache=()=>setReadAt(platformLastRead());window.addEventListener('edusync:platform-auth',authChange);window.addEventListener('edusync:platform-cache',cache);return()=>{window.removeEventListener('edusync:platform-auth',authChange);window.removeEventListener('edusync:platform-cache',cache)}},[]);
  if(online&&auth!=='OFFLINE_AUTHENTICATED_CACHED')return null;
  return <div className="es-alert es-alert-warn sp-offline" role="status"><NavGlyph g="wifiOff" size={16}/><span><b>Hors connexion — lecture seule.</b> Seules les données déjà consultées sont disponibles ; elles peuvent être anciennes. Aucune modification n’est mise en attente.{readAt&&<small>Dernière synchronisation de la donnée consultée : {new Date(readAt).toLocaleString('fr-FR')}.</small>}</span></div>;
}
