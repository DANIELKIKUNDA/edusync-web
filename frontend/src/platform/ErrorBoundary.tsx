import React from 'react';
import { reportTechnical } from './errors';
import { dismissBoot } from './boot';
export class ErrorBoundary extends React.Component<React.PropsWithChildren,{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return{failed:true}}componentDidCatch(error:unknown){dismissBoot();reportTechnical(error,'render')}render(){if(this.state.failed)return <main className="safeError"><h1>EduSync reste disponible</h1><p>Cette page a rencontré une difficulté d’affichage. Vos données enregistrées ne sont pas supprimées.</p><button onClick={()=>location.reload()}>Recharger la page</button></main>;return this.props.children}}
