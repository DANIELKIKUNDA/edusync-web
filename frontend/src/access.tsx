import React,{useEffect,useMemo,useState} from 'react';
import {toast} from 'sonner';
import {friendlyError} from './platform/errors';
import './access.css';

/* Accès & rôles — each school sets its own access policy (owner decision 2026-10-02).
   No approval workflow: automatic guardrails + full transparency (rights journal). */

type Props={token:string;permissions:string[];userName:string};
type Tab='members'|'roles'|'journal';
type Capability={code:string;label:string;group:string;risk:'LOW'|'MEDIUM'|'HIGH'|'CRITICAL'|string};
type Domain={domain:string;capabilities:Capability[]};
type Role={id:string;code:string;label:string;description:string;kind:'SCHOOL_STANDARD'|'SCHOOL_CUSTOM';status:string;version:number;holders:number;capabilities:string[];editable:boolean};
type Scope={type:'SCHOOL'|'SECTION'|'CLASS';value:string|null};
type MemberRole={assignment_id:string;role_id:string;role_label:string;role_kind:string;valid_until:string|null;scopes:Scope[]};
type Member={membership_id:string;active:boolean;full_name:string;email:string;roles:MemberRole[];is_me:boolean};
type JournalItem={created_at:string;action:string;reason:string|null;new_data:any;old_data:any;actor:string|null};
type ScopeOptions={sections:{code:string;label:string}[];classes:{code:string;label:string;section:string}[]};

const API=import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const headers=(token:string,extra:Record<string,string>={})=>({'Authorization':`Bearer ${token}`,'Content-Type':'application/json',...extra});
async function readError(r:Response){try{const b=await r.json();return typeof b.detail==='string'?b.detail:`Erreur ${r.status}`}catch{return `Erreur ${r.status}`}}
async function get<T>(token:string,path:string):Promise<T>{const r=await fetch(`${API}/access/${path}`,{headers:headers(token)});if(!r.ok)throw new Error(await readError(r));return r.json()}
async function send<T>(token:string,method:'POST'|'PUT',path:string,body:unknown,extra:Record<string,string>={}):Promise<T>{
  const r=await fetch(`${API}/access/${path}`,{method,headers:headers(token,{'Idempotency-Key':crypto.randomUUID(),...extra}),body:JSON.stringify(body)});
  if(!r.ok)throw new Error(await readError(r));return r.json()}

const has=(p:string[],c:string)=>p.includes(c);
const RISK_LABEL:Record<string,string>={LOW:'Faible',MEDIUM:'Modéré',HIGH:'Élevé',CRITICAL:'Critique'};
const ACTION_LABEL:Record<string,string>={ACCESS_ROLE_CREATED:'Rôle créé',ACCESS_ROLE_UPDATED:'Rôle modifié',ACCESS_ROLE_ARCHIVED:'Rôle archivé',ACCESS_ROLE_ASSIGNED:'Rôle attribué',ACCESS_ROLE_REVOKED:'Rôle retiré'};
const initials=(n:string)=>n.split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]?.toUpperCase()).join('')||'U';
const dateFr=(v:string|null)=>v?new Date(v).toLocaleDateString('fr-FR',{day:'2-digit',month:'short',year:'numeric'}):'';
const dateTimeFr=(v:string)=>new Date(v).toLocaleString('fr-FR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const scopeText=(s:Scope)=>s.type==='SCHOOL'?'Toute l’école':`${s.type==='SECTION'?'Section':'Classe'} ${s.value}`;

function Icon({name,size=20}:{name:string;size?:number}){
  const p:Record<string,React.ReactNode>={
    shield:<><path d="M12 3 4 6v6c0 5 3.4 8.5 8 9 4.6-.5 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></>,
    users:<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    key:<><circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3M17 6l3 3M14 9l2 2"/></>,
    layers:<><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/></>,
    clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    history:<><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></>,
    plus:<><path d="M12 5v14M5 12h14"/></>,
    copy:<><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
    edit:<><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></>,
    archive:<><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/></>,
    x:<><path d="M18 6 6 18M6 6l12 12"/></>,
    search:<><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></>,
    lock:<><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></>,
    eye:<><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
    check:<><path d="m5 12 5 5L20 7"/></>,
    alert:<><path d="M12 3 2 21h20L12 3Z"/><path d="M12 10v4M12 17.5v.5"/></>,
  };
  return <svg className="uiIcon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{p[name]??p.shield}</svg>;
}

function Metric({icon,value,label,tone}:{icon:string;value:React.ReactNode;label:string;tone?:string}){
  return <div className={`personMetric ${tone?`tone-${tone}`:''}`}><span className="metricIcon"><Icon name={icon}/></span><b className="metricNumber">{value}</b><span className="metricLabel">{label}</span></div>;
}

export default function AccessPage({token,permissions,userName}:Props){
  const canRead=has(permissions,'access.roles.read');
  const canManageRoles=has(permissions,'access.roles.manage');
  const canAssign=has(permissions,'access.permissions.assign');
  const canScope=has(permissions,'access.scopes.assign');
  const canJournal=canRead||has(permissions,'audit.school.read');
  const [tab,setTab]=useState<Tab>(canRead?'members':'journal');
  const [loading,setLoading]=useState(true),[error,setError]=useState('');
  const [catalog,setCatalog]=useState<Domain[]>([]),[roles,setRoles]=useState<Role[]>([]),[members,setMembers]=useState<Member[]>([]);
  const [journal,setJournal]=useState<JournalItem[]>([]),[scopes,setScopes]=useState<ScopeOptions>({sections:[],classes:[]});
  const [q,setQ]=useState('');
  const [editor,setEditor]=useState<{mode:'create'|'edit';role?:Role;base?:Role}|null>(null);
  const [assignFor,setAssignFor]=useState<Member|null>(null);
  const [confirm,setConfirm]=useState<{title:string;text:string;cta:string;run:(reason:string)=>Promise<void>}|null>(null);

  async function load(){
    try{setError('');setLoading(true);
      const jobs:Promise<void>[]=[];
      if(canRead){
        jobs.push(get<{domains:Domain[]}>(token,'catalog').then(d=>setCatalog(d.domains)));
        jobs.push(get<{items:Role[]}>(token,'roles').then(d=>setRoles(d.items)));
        jobs.push(get<{items:Member[]}>(token,'members').then(d=>setMembers(d.items)));
        jobs.push(get<ScopeOptions>(token,'scope-options').then(setScopes));
      }
      if(canJournal)jobs.push(get<{items:JournalItem[]}>(token,'journal?limit=100').then(d=>setJournal(d.items)));
      await Promise.all(jobs);
    }catch(e){setError(friendlyError(e))}finally{setLoading(false)}
  }
  useEffect(()=>{void load()},[token]);

  const capIndex=useMemo(()=>{const m=new Map<string,Capability>();catalog.forEach(d=>d.capabilities.forEach(c=>m.set(c.code,{...c,group:`${d.domain} · ${c.group}`})));return m},[catalog]);
  const activeRoles=roles.filter(r=>r.status==='ACTIVE');
  const customCount=activeRoles.filter(r=>r.kind==='SCHOOL_CUSTOM').length;
  const temporary=members.reduce((n,m)=>n+m.roles.filter(r=>r.valid_until).length,0);
  const recent=journal.filter(j=>Date.now()-new Date(j.created_at).getTime()<30*864e5).length;
  const filtered=members.filter(m=>!q.trim()||`${m.full_name} ${m.email} ${m.roles.map(r=>r.role_label).join(' ')}`.toLowerCase().includes(q.trim().toLowerCase()));

  async function revoke(m:Member,r:MemberRole){
    setConfirm({title:`Retirer « ${r.role_label} »`,text:`${m.full_name} perdra immédiatement les droits de ce rôle, sans reconnexion.`,cta:'Retirer le rôle',
      run:async reason=>{await send(token,'POST',`assignments/${r.assignment_id}/revoke`,{reason});toast.success('Rôle retiré — effet immédiat');await load()}});
  }
  async function archive(role:Role){
    setConfirm({title:`Archiver « ${role.label} »`,text:'Le rôle ne pourra plus être attribué. Il doit d’abord être retiré à toutes les personnes qui le détiennent.',cta:'Archiver',
      run:async reason=>{await send(token,'POST',`roles/${role.id}/archive`,{reason});toast.success('Rôle archivé');await load()}});
  }

  return <div className="personnelPage accessPage pageEnter">
    <div className="personnelHero">
      <div><span className="eyebrow"><Icon name="shield" size={14}/> Gouvernance des accès</span><h2>Accès & rôles</h2>
        <p>Votre école décide de sa propre politique d’accès. Les garde-fous de sécurité s’appliquent automatiquement, et chaque changement est inscrit au journal.</p></div>
      <div className="heroActions">{canManageRoles&&<button className="primaryBtn" onClick={()=>setEditor({mode:'create'})}><Icon name="plus" size={16}/> Nouveau rôle</button>}</div>
    </div>
    {error&&<div className="error" role="alert">{error}</div>}

    {canRead&&<div className="accessMetrics">
      {loading?[0,1,2,3].map(i=><div key={i} className="personMetric skeleton"><i/><b/><small/></div>):<>
        <Metric icon="users" value={members.filter(m=>m.active).length} label="Membres actifs"/>
        <Metric icon="layers" value={activeRoles.length} label={`Rôles · ${customCount} propre${customCount>1?'s':''} à l’école`} tone="violet"/>
        <Metric icon="clock" value={temporary} label="Droits temporaires" tone="amber"/>
        <Metric icon="history" value={recent} label="Changements · 30 jours" tone="green"/>
      </>}
    </div>}

    <div className="guardrails" aria-label="Garde-fous actifs">
      <span className="guardTitle"><Icon name="lock" size={15}/> Garde-fous actifs</span>
      <span><Icon name="check" size={13}/> Personne ne s’attribue de droits</span>
      <span><Icon name="check" size={13}/> Aucun droit plateforme</span>
      <span><Icon name="check" size={13}/> Toujours un gestionnaire des accès</span>
      <span><Icon name="check" size={13}/> Tout est journalisé</span>
    </div>

    <div className="personTabs" role="tablist">
      {canRead&&<button role="tab" aria-selected={tab==='members'} className={tab==='members'?'active':''} onClick={()=>setTab('members')}><Icon name="users" size={15}/> Membres <span>{members.length}</span></button>}
      {canRead&&<button role="tab" aria-selected={tab==='roles'} className={tab==='roles'?'active':''} onClick={()=>setTab('roles')}><Icon name="key" size={15}/> Rôles <span>{activeRoles.length}</span></button>}
      {canJournal&&<button role="tab" aria-selected={tab==='journal'} className={tab==='journal'?'active':''} onClick={()=>setTab('journal')}><Icon name="history" size={15}/> Journal des droits <span>{journal.length}</span></button>}
    </div>

    {tab==='members'&&canRead&&<section className="premiumCard">
      <div className="cardHeading"><div><h3>Qui peut faire quoi</h3><p>Chaque attribution précise un périmètre et, si besoin, une date de fin.</p></div>
        <label className="searchBox accessSearch"><Icon name="search" size={16}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Nom, e-mail ou rôle" aria-label="Rechercher un membre"/></label></div>
      <div className="memberList">
        {filtered.map(m=><article key={m.membership_id} className={`memberRow ${m.active?'':'inactive'}`}>
          <div className="memberIdentity"><span className="avatar">{initials(m.full_name)}</span><div><b>{m.full_name}{m.is_me&&<em className="meBadge">Vous</em>}</b><small>{m.email}{!m.active&&' · désactivé'}</small></div></div>
          <div className="roleChips">
            {m.roles.length===0&&<span className="noRole">Aucun rôle</span>}
            {m.roles.map(r=><span key={r.assignment_id} className={`roleChip ${r.role_kind==='SCHOOL_CUSTOM'?'custom':''}`}>
              <b>{r.role_label}</b>
              {r.scopes.filter(s=>s.type!=='SCHOOL').map(s=><i key={`${s.type}${s.value}`} className="scopePill">{scopeText(s)}</i>)}
              {r.valid_until&&<i className="untilPill"><Icon name="clock" size={11}/> {dateFr(r.valid_until)}</i>}
              {canAssign&&!m.is_me&&<button className="chipX" aria-label={`Retirer ${r.role_label}`} onClick={()=>void revoke(m,r)}><Icon name="x" size={12}/></button>}
            </span>)}
          </div>
          <div className="memberActions">{canAssign&&(m.is_me
            ?<span className="selfLock" title="Personne ne modifie ses propres droits"><Icon name="lock" size={14}/></span>
            :<button className="softBtn" disabled={!m.active} onClick={()=>setAssignFor(m)}><Icon name="plus" size={15}/> Attribuer</button>)}</div>
        </article>)}
        {!loading&&!filtered.length&&<div className="personEmpty"><span><Icon name="users" size={26}/></span><b>Aucun membre trouvé</b><small>Modifiez la recherche.</small></div>}
      </div>
    </section>}

    {tab==='roles'&&canRead&&<section className="roleGrid">
      {activeRoles.map(r=>{const caps=r.capabilities.map(c=>capIndex.get(c)).filter(Boolean) as Capability[];const critical=caps.filter(c=>c.risk==='CRITICAL').length;const high=caps.filter(c=>c.risk==='HIGH').length;
        return <article key={r.id} className={`roleCard ${r.kind==='SCHOOL_CUSTOM'?'custom':''}`}>
          <div className="roleCardTop"><span className={`kindBadge ${r.kind==='SCHOOL_CUSTOM'?'custom':''}`}>{r.kind==='SCHOOL_CUSTOM'?'Propre à l’école':'Standard EduSync'}</span><span className="holders"><Icon name="users" size={13}/> {r.holders}</span></div>
          <h4>{r.label}</h4><p>{r.description||'—'}</p>
          <div className="riskMeter" aria-label={`${r.capabilities.length} permissions dont ${critical} critiques`}>
            <span><b>{r.capabilities.length}</b> permissions</span>{critical>0&&<i className="risk critical">{critical} critique{critical>1?'s':''}</i>}{high>0&&<i className="risk high">{high} élevée{high>1?'s':''}</i>}
          </div>
          <div className="roleCardActions">
            {r.kind==='SCHOOL_STANDARD'
              ?<>{canManageRoles&&<button className="softBtn" onClick={()=>setEditor({mode:'create',base:r})}><Icon name="copy" size={15}/> Cloner pour adapter</button>}<button className="textBtn" onClick={()=>setEditor({mode:'edit',role:r})}><Icon name="eye" size={15}/> Voir</button></>
              :<>{canManageRoles&&<button className="softBtn" onClick={()=>setEditor({mode:'edit',role:r})}><Icon name="edit" size={15}/> Modifier</button>}{canManageRoles&&<button className="textBtn danger" onClick={()=>void archive(r)}><Icon name="archive" size={15}/> Archiver</button>}</>}
          </div>
        </article>})}
    </section>}

    {tab==='journal'&&canJournal&&<section className="premiumCard">
      <div className="cardHeading"><div><h3>Journal des droits</h3><p>Lecture seule. Aucune validation n’est demandée : chaque changement est simplement visible, daté et attribué.</p></div></div>
      <div className="timeline">{journal.map((j,i)=><div key={i} className="timelineItem"><span className="timelineDot"><Icon name={j.action==='ACCESS_ROLE_REVOKED'?'x':j.action==='ACCESS_ROLE_ASSIGNED'?'plus':'key'} size={15}/></span>
        <div><b>{ACTION_LABEL[j.action]??j.action} · {j.new_data?.role_label??j.new_data?.label??''}</b>
          <small>{dateTimeFr(j.created_at)} · par {j.actor??'—'}</small>
          {j.new_data?.added?.length>0&&<p className="diffAdd">+ {j.new_data.added.map((c:string)=>capIndex.get(c)?.label??c).join(', ')}</p>}
          {j.new_data?.removed?.length>0&&<p className="diffDel">− {j.new_data.removed.map((c:string)=>capIndex.get(c)?.label??c).join(', ')}</p>}
          {j.new_data?.scopes&&<p>{(j.new_data.scopes as Scope[]).map(scopeText).join(' · ')}{j.new_data.valid_until?` · jusqu’au ${dateFr(j.new_data.valid_until)}`:''}</p>}
          {j.reason&&<p className="reason">« {j.reason} »</p>}</div></div>)}
        {!loading&&!journal.length&&<div className="personEmpty"><span><Icon name="history" size={26}/></span><b>Aucun changement de droits</b><small>Les créations, attributions et retraits apparaîtront ici.</small></div>}
      </div>
    </section>}

    {editor&&<RoleEditor token={token} catalog={catalog} capIndex={capIndex} editor={editor} readOnly={editor.mode==='edit'&&(!editor.role?.editable||!canManageRoles)}
      onClose={()=>setEditor(null)} onSaved={async()=>{setEditor(null);await load()}}/>}
    {assignFor&&<AssignDialog token={token} member={assignFor} roles={activeRoles} scopes={scopes} canScope={canScope}
      onClose={()=>setAssignFor(null)} onSaved={async()=>{setAssignFor(null);await load()}}/>}
    {confirm&&<ReasonDialog {...confirm} onClose={()=>setConfirm(null)}/>}
  </div>;
}

function RoleEditor({token,catalog,capIndex,editor,readOnly,onClose,onSaved}:{token:string;catalog:Domain[];capIndex:Map<string,Capability>;editor:{mode:'create'|'edit';role?:Role;base?:Role};readOnly:boolean;onClose:()=>void;onSaved:()=>Promise<void>}){
  const source=editor.role??editor.base;
  const original=useMemo(()=>new Set(source?.capabilities??[]),[source]);
  const [label,setLabel]=useState(editor.role?.label??(editor.base?`${editor.base.label} — adapté`:''));
  const [description,setDescription]=useState(editor.role?.description??(editor.base?`Adapté depuis le rôle standard « ${editor.base.label} »`:''));
  const [selected,setSelected]=useState<Set<string>>(new Set(source?.capabilities??[]));
  const [q,setQ]=useState(''),[busy,setBusy]=useState(false),[onlySelected,setOnlySelected]=useState(false);
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
  const added=[...selected].filter(c=>!original.has(c)),removed=[...original].filter(c=>!selected.has(c));
  const critical=[...selected].filter(c=>capIndex.get(c)?.risk==='CRITICAL').length;
  const toggle=(c:string)=>{if(readOnly)return;setSelected(s=>{const n=new Set(s);n.has(c)?n.delete(c):n.add(c);return n})};
  const domains=catalog.map(d=>({...d,capabilities:d.capabilities.filter(c=>(!onlySelected||selected.has(c.code))&&(!q.trim()||`${c.label} ${c.code} ${c.group}`.toLowerCase().includes(q.toLowerCase())))})).filter(d=>d.capabilities.length);
  const title=readOnly?(source?.label??'Rôle'):editor.mode==='create'?(editor.base?'Adapter un rôle standard':'Nouveau rôle de l’école'):'Modifier le rôle';
  async function save(){
    if(label.trim().length<3){toast.error('Donnez un nom d’au moins 3 caractères');return}
    try{setBusy(true);
      if(editor.mode==='create')await send(token,'POST','roles',{label:label.trim(),description:description.trim(),capabilities:[...selected]});
      else await send(token,'PUT',`roles/${editor.role!.id}`,{label:label.trim(),description:description.trim(),capabilities:[...selected]},{'If-Match':String(editor.role!.version)});
      toast.success(editor.mode==='create'?'Rôle créé':'Rôle mis à jour — effet immédiat pour ses titulaires');await onSaved();
    }catch(e){toast.error(friendlyError(e))}finally{setBusy(false)}
  }
  return <div className="sheetBackdrop" onClick={onClose}><aside className="roleSheet" role="dialog" aria-modal="true" aria-label={title} onClick={e=>e.stopPropagation()}>
    <header className="sheetHead"><div><span className="eyebrow"><Icon name="key" size={13}/> {readOnly?'Lecture seule':'Éditeur de rôle'}</span><h3>{title}</h3></div><button className="iconAction" aria-label="Fermer" onClick={onClose}><Icon name="x" size={16}/></button></header>
    <div className="sheetBody">
      <div className="sheetFields">
        <label>Nom du rôle<input value={label} disabled={readOnly} onChange={e=>setLabel(e.target.value)} maxLength={120} placeholder="Ex. Gestionnaire sans sortie d’agent"/></label>
        <label>Description<textarea value={description} disabled={readOnly} onChange={e=>setDescription(e.target.value)} rows={2} maxLength={600}/></label>
      </div>
      <div className="capToolbar">
        <label className="searchBox"><Icon name="search" size={15}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Rechercher une permission" aria-label="Rechercher une permission"/></label>
        <label className="toggleLine"><input type="checkbox" checked={onlySelected} onChange={e=>setOnlySelected(e.target.checked)}/> Sélection seulement</label>
      </div>
      <div className="capDomains">{domains.map(d=>{const all=d.capabilities.every(c=>selected.has(c.code));
        return <section key={d.domain} className="capDomain"><div className="capDomainHead"><b>{d.domain}</b><small>{d.capabilities.filter(c=>selected.has(c.code)).length}/{d.capabilities.length}</small>
          {!readOnly&&<button className="textBtn" onClick={()=>setSelected(s=>{const n=new Set(s);d.capabilities.forEach(c=>all?n.delete(c.code):n.add(c.code));return n})}>{all?'Tout retirer':'Tout cocher'}</button>}</div>
          {d.capabilities.map(c=><label key={c.code} className={`capRow ${selected.has(c.code)?'on':''} ${readOnly?'ro':''}`}>
            <input type="checkbox" checked={selected.has(c.code)} disabled={readOnly} onChange={()=>toggle(c.code)}/>
            <span className="capText"><b>{c.label}</b><small>{c.group}</small></span>
            <i className={`risk ${String(c.risk).toLowerCase()}`}>{RISK_LABEL[c.risk]??c.risk}</i>
          </label>)}</section>})}
        {!domains.length&&<div className="personEmpty"><span><Icon name="search" size={24}/></span><b>Aucune permission</b><small>Aucun résultat pour cette recherche.</small></div>}
      </div>
    </div>
    <footer className="sheetFoot">
      <div className="sheetSummary"><b>{selected.size}</b> permissions{critical>0&&<i className="risk critical">{critical} critique{critical>1?'s':''}</i>}
        {(added.length>0||removed.length>0)&&<span className="diffBadge">{added.length>0&&<em className="add">+{added.length}</em>}{removed.length>0&&<em className="del">−{removed.length}</em>}</span>}</div>
      <div className="sheetButtons"><button className="softBtn" onClick={onClose}>{readOnly?'Fermer':'Annuler'}</button>{!readOnly&&<button className="primaryBtn" disabled={busy} onClick={()=>void save()}>{busy?'Enregistrement…':editor.mode==='create'?'Créer le rôle':'Enregistrer'}</button>}</div>
    </footer>
  </aside></div>;
}

const DURATIONS=[{k:'none',l:'Permanent'},{k:'7',l:'1 semaine'},{k:'30',l:'1 mois'},{k:'90',l:'3 mois'},{k:'date',l:'Date…'}] as const;

function AssignDialog({token,member,roles,scopes,canScope,onClose,onSaved}:{token:string;member:Member;roles:Role[];scopes:ScopeOptions;canScope:boolean;onClose:()=>void;onSaved:()=>Promise<void>}){
  const held=new Set(member.roles.map(r=>r.role_id));
  const available=roles.filter(r=>!held.has(r.id));
  const [roleId,setRoleId]=useState(available[0]?.id??''),[scopeType,setScopeType]=useState<'SCHOOL'|'SECTION'|'CLASS'>('SCHOOL'),[scopeValue,setScopeValue]=useState('');
  const [duration,setDuration]=useState<string>('none'),[until,setUntil]=useState(''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false);
  const options=scopeType==='SECTION'?scopes.sections.map(s=>({v:s.code,l:s.label})):scopes.classes.map(c=>({v:c.code,l:`${c.label} · ${c.section}`}));
  const validUntil=duration==='none'?null:duration==='date'?(until?new Date(`${until}T23:59:59`).toISOString():null):new Date(Date.now()+Number(duration)*864e5).toISOString();
  const ready=roleId&&reason.trim().length>=3&&(scopeType==='SCHOOL'||scopeValue)&&(duration!=='date'||until);
  async function save(){if(!ready)return;try{setBusy(true);
    await send(token,'POST',`members/${member.membership_id}/roles`,{role_id:roleId,scopes:[scopeType==='SCHOOL'?{type:'SCHOOL'}:{type:scopeType,value:scopeValue}],valid_until:validUntil,reason:reason.trim()});
    toast.success(`Rôle attribué à ${member.full_name} — effet immédiat`);await onSaved()}catch(e){toast.error(friendlyError(e))}finally{setBusy(false)}}
  return <div className="wizardBackdrop" onClick={onClose}><div className="accountSecurityDialog assignDialog" role="dialog" aria-modal="true" aria-label="Attribuer un rôle" onClick={e=>e.stopPropagation()}>
    <div className="modalHead"><div><h3>Attribuer un rôle</h3><p><span className="avatar sm">{initials(member.full_name)}</span> {member.full_name}</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    <label>Rôle<select value={roleId} onChange={e=>setRoleId(e.target.value)}>
      <optgroup label="Rôles propres à l’école">{available.filter(r=>r.kind==='SCHOOL_CUSTOM').map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</optgroup>
      <optgroup label="Rôles standards EduSync">{available.filter(r=>r.kind==='SCHOOL_STANDARD').map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</optgroup>
    </select></label>
    <div className="fieldGroup"><span>Périmètre</span><div className="segmented" role="radiogroup">
      {(['SCHOOL','SECTION','CLASS'] as const).map(t=><button key={t} type="button" role="radio" aria-checked={scopeType===t} disabled={t!=='SCHOOL'&&!canScope} className={scopeType===t?'on':''} onClick={()=>{setScopeType(t);setScopeValue('')}}>{t==='SCHOOL'?'Toute l’école':t==='SECTION'?'Une section':'Une classe'}</button>)}
    </div>{scopeType!=='SCHOOL'&&<select value={scopeValue} onChange={e=>setScopeValue(e.target.value)} aria-label="Choisir le périmètre"><option value="">Choisir…</option>{options.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}</select>}</div>
    <div className="fieldGroup"><span>Durée</span><div className="segmented wrap" role="radiogroup">
      {DURATIONS.map(d=><button key={d.k} type="button" role="radio" aria-checked={duration===d.k} className={duration===d.k?'on':''} onClick={()=>setDuration(d.k)}>{d.l}</button>)}
    </div>{duration==='date'&&<input type="date" value={until} min={new Date(Date.now()+864e5).toISOString().slice(0,10)} onChange={e=>setUntil(e.target.value)} aria-label="Date de fin"/>}
      {validUntil&&<small className="fieldHint"><Icon name="clock" size={12}/> Expire automatiquement le {dateFr(validUntil)}</small>}</div>
    <label>Motif *<textarea rows={2} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Ex. Remplacement du gestionnaire pendant son congé"/></label>
    <div className="modalActions"><button className="ghost" onClick={onClose}>Annuler</button><button disabled={busy||!ready} onClick={()=>void save()}>{busy?'Attribution…':'Attribuer'}</button></div>
  </div></div>;
}

function ReasonDialog({title,text,cta,run,onClose}:{title:string;text:string;cta:string;run:(reason:string)=>Promise<void>;onClose:()=>void}){
  const [reason,setReason]=useState(''),[busy,setBusy]=useState(false);
  async function go(){try{setBusy(true);await run(reason.trim());onClose()}catch(e){toast.error(friendlyError(e))}finally{setBusy(false)}}
  return <div className="wizardBackdrop" onClick={onClose}><div className="accountSecurityDialog" role="alertdialog" aria-modal="true" aria-label={title} onClick={e=>e.stopPropagation()}>
    <div className="modalHead"><div><h3>{title}</h3><p>{text}</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    <label>Motif *<textarea rows={3} value={reason} onChange={e=>setReason(e.target.value)} autoFocus/></label>
    <div className="modalActions"><button className="ghost" onClick={onClose}>Annuler</button><button className="dangerBtn" disabled={busy||reason.trim().length<3} onClick={()=>void go()}>{busy?'…':cta}</button></div>
  </div></div>;
}
