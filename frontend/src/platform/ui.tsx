import React from 'react';
import {NavGlyph} from './nav_icons';
import './ui.css';

/* EduSync UI kit (2026-10-24) — shared by the platform and the school space, meant for every module (Élèves, Finance,
   Personnel, Documents…). Colours come from the shell tokens (--es-*), so the dark theme follows. Rules:
   - a card that is entirely clickable is a <button>: no redundant « Voir » inside it, a discrete chevron instead;
   - three card levels: `priority` (needs an action), `info` (a figure to read), `secondary` (context);
   - touch targets ≥ 44 px, visible keyboard focus, motion only when the user allows it (prefers-reduced-motion);
   - entrance motion is a short fade / rise staggered with the --i custom property. */

export type Tone='ok'|'todo'|'warn'|'blocked'|'neutral'|'locked'|'brand';

export function StatusBadge({tone='neutral',children,icon}:{tone?:Tone;children:React.ReactNode;icon?:string}){
  return <span className={`ui-badge ui-badge-${tone}`}>{icon&&<NavGlyph g={icon} size={13}/>}{children}</span>;
}

type BtnProps=React.ButtonHTMLAttributes<HTMLButtonElement>&{variant?:'primary'|'secondary'|'quiet'|'danger';icon?:string;size?:'md'|'sm'};
export function Button({variant='secondary',icon,size='md',className='',children,...rest}:BtnProps){
  return <button type="button" {...rest} className={`ui-btn ui-btn-${variant} ui-btn-${size} ${className}`}>{icon&&<NavGlyph g={icon} size={size==='sm'?15:17}/>}{children&&<span>{children}</span>}</button>;
}

export function PageHeader({eyebrow,title,subtitle,actions,aside}:{eyebrow?:React.ReactNode;title:React.ReactNode;subtitle?:React.ReactNode;actions?:React.ReactNode;aside?:React.ReactNode}){
  return <header className="ui-page-head">
    <div className="ui-page-head-text">{eyebrow&&<p className="ui-eyebrow">{eyebrow}</p>}<h2>{title}</h2>{subtitle&&<p className="ui-subtitle">{subtitle}</p>}</div>
    {aside&&<div className="ui-page-head-aside">{aside}</div>}
    {actions&&<div className="ui-page-actions">{actions}</div>}
  </header>;
}

export function Section({title,subtitle,actions,children,id}:{title?:React.ReactNode;subtitle?:React.ReactNode;actions?:React.ReactNode;children:React.ReactNode;id?:string}){
  return <section className="ui-section" aria-labelledby={id}>
    {(title||actions)&&<div className="ui-section-head"><div>{title&&<h3 id={id}>{title}</h3>}{subtitle&&<p>{subtitle}</p>}</div>{actions}</div>}
    {children}
  </section>;
}

type CardProps={level?:'priority'|'info'|'secondary';icon?:string;title:React.ReactNode;value?:React.ReactNode;unit?:React.ReactNode;hint?:React.ReactNode;
  badge?:React.ReactNode;tone?:Tone;onClick?:()=>void;ariaLabel?:string;children?:React.ReactNode;wide?:boolean;index?:number;className?:string};
/** One card language for the whole product. With `onClick`, the whole card is the control. */
export function Card({level='info',icon,title,value,unit,hint,badge,tone,onClick,ariaLabel,children,wide,index=0,className=''}:CardProps){
  const cls=`ui-card ui-card-${level} ${tone?`ui-tone-${tone}`:''} ${wide?'ui-card-wide':''} ${onClick?'ui-card-action':''} ${className}`;
  const body=<>
    <div className="ui-card-top">{icon&&<span className="ui-card-icon" aria-hidden="true"><NavGlyph g={icon} size={19}/></span>}
      <span className="ui-card-title">{title}</span>{badge}{onClick&&<span className="ui-card-chevron" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span>}</div>
    {value!==undefined&&<p className="ui-card-value">{value}{unit&&<small>{unit}</small>}</p>}
    {hint&&<p className="ui-card-hint">{hint}</p>}
    {children&&<div className="ui-card-body">{children}</div>}
  </>;
  const style={'--i':index} as React.CSSProperties;
  return onClick?<button type="button" className={cls} style={style} onClick={onClick} aria-label={ariaLabel}>{body}</button>:<article className={cls} style={style}>{body}</article>;
}

export function Skeleton({lines=3,block=false}:{lines?:number;block?:boolean}){
  return <div className="ui-skel-wrap" aria-hidden="true">{block?<i className="ui-skel ui-skel-block"/>:Array.from({length:lines},(_,i)=><i key={i} className="ui-skel" style={{width:`${92-i*17}%`}}/>)}</div>;
}

export function EmptyState({icon='checkCircle',title,text,action}:{icon?:string;title:React.ReactNode;text?:React.ReactNode;action?:React.ReactNode}){
  return <div className="ui-empty"><span aria-hidden="true"><NavGlyph g={icon} size={22}/></span><b>{title}</b>{text&&<p>{text}</p>}{action}</div>;
}

export function ProgressRing({percent,size=92,label}:{percent:number;size?:number;label?:string}){
  const p=Math.max(0,Math.min(100,Math.round(percent)));const r=(size-10)/2;const c=2*Math.PI*r;
  return <div className="ui-ring" style={{width:size,height:size}} role="img" aria-label={`${label??'Progression'} : ${p} %`}>
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}><circle className="ui-ring-track" cx={size/2} cy={size/2} r={r}/>
      <circle className="ui-ring-value" cx={size/2} cy={size/2} r={r} strokeDasharray={c} strokeDashoffset={c*(1-p/100)} transform={`rotate(-90 ${size/2} ${size/2})`}/></svg>
    <b>{p}<small>%</small></b>
  </div>;
}

export type JourneyStep={key:string;label:string;detail?:string;status:'done'|'todo'|'check'|'optional';priority?:boolean;onClick?:()=>void;actionLabel?:string};
const STEP_TONE:Record<JourneyStep['status'],{tone:Tone;label:string}>={done:{tone:'ok',label:'Configuré'},todo:{tone:'todo',label:'À compléter'},check:{tone:'warn',label:'À vérifier'},optional:{tone:'neutral',label:'Facultatif'}};
/** Progress journey: the percentage becomes remaining steps with status, priority and a direct action. */
export function ProgressJourney({percent,title,subtitle,steps,showDone=false,max}:{percent:number;title:React.ReactNode;subtitle?:React.ReactNode;steps:JourneyStep[];showDone?:boolean;max?:number}){
  const remaining=steps.filter(s=>s.status==='todo'||s.status==='check');
  const ordered=[...remaining].sort((a,b)=>Number(!!b.priority)-Number(!!a.priority)||Number(b.status==='todo')-Number(a.status==='todo'));
  const done=steps.filter(s=>s.status==='done');
  const list=(showDone?[...ordered,...done]:ordered).slice(0,max??Infinity);
  return <div className="ui-journey">
    <div className="ui-journey-head"><ProgressRing percent={percent} label="Paramétrage"/>
      <div><h3>{title}</h3><p>{subtitle??(remaining.length?`${remaining.length} étape${remaining.length>1?'s':''} restante${remaining.length>1?'s':''} · ${done.length} terminée${done.length>1?'s':''}`:'Tout est prêt')}</p>
        <div className="ui-journey-bar" aria-hidden="true"><i style={{width:`${Math.max(0,Math.min(100,percent))}%`}}/></div></div></div>
    {list.length?<ol className="ui-journey-steps">{list.map((s,i)=>{const t=STEP_TONE[s.status];
      const inner=<><span className={`ui-step-dot ui-step-${s.status}`} aria-hidden="true">{s.status==='done'?<NavGlyph g="check" size={14}/>:i+1}</span>
        <span className="ui-step-text"><b>{s.label}{s.priority&&s.status!=='done'&&<StatusBadge tone="blocked">Prioritaire</StatusBadge>}</b>{s.detail&&<small>{s.detail}</small>}</span>
        <StatusBadge tone={t.tone}>{t.label}</StatusBadge>{s.onClick&&<span className="ui-step-go">{s.actionLabel??'Ouvrir'}<NavGlyph g="chevronRight" size={16}/></span>}</>;
      return <li key={s.key}>{s.onClick?<button type="button" className="ui-step" onClick={s.onClick}>{inner}</button>:<div className="ui-step">{inner}</div>}</li>})}</ol>
      :<EmptyState title="Paramétrage complet" text="Toutes les étapes essentielles sont configurées."/>}
  </div>;
}
