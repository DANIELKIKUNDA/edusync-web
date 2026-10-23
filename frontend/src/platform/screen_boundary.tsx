import React from 'react';
import {NavGlyph} from './nav_icons';
import {reportTechnical} from './errors';

/* Local screen protection (owner decision 11, 2026-10-23): a failing screen never takes the shell, the navigation or
   the account menu down with it. The global ErrorBoundary (main.tsx) stays as the very last resort only.
   classifyScreenError gives one honest message per situation, with the action that can actually help. */

export type ScreenErrorKind='network'|'offline'|'session'|'permission'|'not_found'|'server'|'unavailable'|'render';

export function classifyScreenError(error:unknown):{kind:ScreenErrorKind;title:string;text:string;retry:boolean}{
  const e=error as {code?:string;status?:number;message?:string;name?:string}|null;
  const msg=String(e?.message??'');
  const status=Number(e?.status??(/\b(4\d\d|5\d\d)\b/.exec(msg)?.[1]??0));
  if(e?.code==='OFFLINE_NOT_CACHED'||e?.code==='OFFLINE_READ_ONLY')
    return {kind:'offline',title:'Indisponible hors connexion',text:'Cette page n’a pas encore été consultée sur cet appareil. Elle s’affichera au retour du réseau.',retry:true};
  if(typeof navigator!=='undefined'&&navigator.onLine===false)
    return {kind:'offline',title:'Hors connexion',text:'Seules les pages déjà consultées sont disponibles. Réessayez au retour du réseau.',retry:true};
  if(status===401||/session/i.test(msg))return {kind:'session',title:'Session à renouveler',text:'Votre session a expiré. Reconnectez-vous pour continuer.',retry:false};
  if(status===403||/permission|autorisation|accès refusé|refusé/i.test(msg))return {kind:'permission',title:'Accès non autorisé',text:'Vos droits actuels ne permettent pas d’afficher cette page. Demandez-les au gestionnaire des accès de votre école.',retry:false};
  if(status===404||/introuvable/i.test(msg))return {kind:'not_found',title:'Élément introuvable',text:'Cet élément n’existe plus ou a été déplacé.',retry:false};
  if(status>=500||/momentanément une difficulté/i.test(msg))return {kind:'server',title:'Service momentanément indisponible',text:'Le serveur n’a pas pu répondre. Vos données ne sont pas perdues : réessayez dans un instant.',retry:true};
  if(e?.name==='TypeError'&&/fetch|network|réseau/i.test(msg)||/network|réseau|connexion/i.test(msg))
    return {kind:'network',title:'Connexion impossible',text:'Le serveur ne répond pas. Vérifiez la connexion puis réessayez.',retry:true};
  if(e?.name==='ChunkLoadError'||/dynamically imported module|Loading chunk/i.test(msg))
    return {kind:'unavailable',title:'Nouvelle version disponible',text:'Cette partie de l’application a été mise à jour. Rechargez pour l’obtenir.',retry:true};
  return {kind:'render',title:'Cette partie n’a pas pu s’afficher',text:'Le reste d’EduSync reste disponible. Réessayez ; si le problème persiste, signalez-le avec l’heure.',retry:true};
}

export function ScreenError({error,onRetry,compact=false}:{error:unknown;onRetry?:()=>void;compact?:boolean}){
  const c=classifyScreenError(error);
  return <div className={`screenError ${compact?'compact':''} screenError-${c.kind}`} role="alert">
    <NavGlyph g={c.kind==='offline'||c.kind==='network'?'wifiOff':c.kind==='permission'?'lock':'alert'} size={compact?18:24}/>
    <div><b>{c.title}</b><p>{c.text}</p></div>
    {c.retry&&onRetry&&<button type="button" className="softBtn" onClick={onRetry}>{c.kind==='unavailable'?'Recharger':'Réessayer'}</button>}
  </div>;
}

type Props=React.PropsWithChildren<{resetKey?:string;label?:string;compact?:boolean}>;
export class ScreenBoundary extends React.Component<Props,{error:unknown;attempt:number}>{
  state={error:null as unknown,attempt:0};
  static getDerivedStateFromError(error:unknown){return {error}}
  componentDidCatch(error:unknown){reportTechnical(error,`screen:${this.props.label??'module'}`)}
  componentDidUpdate(prev:Props){if(prev.resetKey!==this.props.resetKey&&this.state.error)this.setState({error:null})}
  retry=()=>{const c=classifyScreenError(this.state.error);if(c.kind==='unavailable'){location.reload();return}this.setState(s=>({error:null,attempt:s.attempt+1}))};
  render(){
    if(this.state.error)return <ScreenError error={this.state.error} onRetry={this.retry} compact={this.props.compact}/>;
    return <React.Fragment key={this.state.attempt}>{this.props.children}</React.Fragment>;
  }
}
