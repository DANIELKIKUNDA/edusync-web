import React, {useEffect, useState} from 'react';
import {getPlatformAuthState, knownContext} from './offline_session';
import {getConnectivity} from './connectivity';

function readOnly(){return !!knownContext() && (navigator.onLine===false || getPlatformAuthState()==='OFFLINE_AUTHENTICATED_CACHED' || getConnectivity().state==='OFFLINE');}

/** A disabled affordance as well as the API guard: never queue a sensitive action. */
export function OnlineActionButton(props:React.ComponentProps<'button'>){
  const [offline,setOffline]=useState(readOnly);
  useEffect(()=>{const update=()=>setOffline(readOnly());const events=['online','offline','edusync:platform-auth','edusync:connectivity'];events.forEach(e=>window.addEventListener(e,update));return()=>events.forEach(e=>window.removeEventListener(e,update));},[]);
  return <button {...props} disabled={props.disabled||offline} title={offline?'Hors connexion — cette action nécessite le serveur.':props.title}/>;
}
