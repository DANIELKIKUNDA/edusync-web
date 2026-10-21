// Browser-only fixtures for real shared components; not an application entry point.
import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AppShell} from '../src/platform/shell';
import {StepUpDialog} from '../src/platform/account';
import {PageTrail} from '../src/platform/navigation';
import '../src/styles.css';
import '../src/platform/modern.css';
function Harness(){
  const [dialog,setDialog]=useState(new URLSearchParams(location.search).get('scene')==='mfa');
  const [deep,setDeep]=useState(true);
  return <AppShell accountDock orgLabel="Plateforme" title="Messagerie" nav={[]} account={{name:'Recette locale',items:[]}}>
    {deep&&<PageTrail parents={[{label:'Messagerie',onSelect:()=>setDeep(false)}]} current="Push"/>}
    <button onClick={()=>setDialog(true)}>Action sensible de test</button>
    {dialog&&<StepUpDialog token="fixture" onDone={()=>setDialog(false)}/>}
    <div style={{height:5000}}><h2>Contenu long de test</h2></div>
  </AppShell>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
