import React,{useEffect,useMemo,useState} from 'react';
import {createPortal} from 'react-dom';
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
type Member={membership_id:string;active:boolean;full_name:string;email:string;roles:MemberRole[];is_me:boolean;must_change_password?:boolean;shared_account?:boolean};
type JournalItem={created_at:string;action:string;reason:string|null;new_data:any;old_data:any;actor:string|null};
type ScopeOptions={sections:{code:string;label:string}[];classes:{code:string;label:string;section:string}[]};

const API=import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const headers=(token:string,extra:Record<string,string>={})=>({'Authorization':`Bearer ${token}`,'Content-Type':'application/json',...extra});
async function readError(r:Response){try{const b=await r.json();return typeof b.detail==='string'?b.detail:`Erreur ${r.status}`}catch{return `Erreur ${r.status}`}}
async function get<T>(token:string,path:string):Promise<T>{const r=await fetch(`${API}/access/${path}`,{headers:headers(token)});if(!r.ok)throw new Error(await readError(r));return r.json()}
async function send<T>(token:string,method:'POST'|'PUT'|'PATCH',path:string,body:unknown,extra:Record<string,string>={}):Promise<T>{
  const r=await fetch(`${API}/access/${path}`,{method,headers:headers(token,{'Idempotency-Key':crypto.randomUUID(),...extra}),body:JSON.stringify(body)});
  if(!r.ok)throw new Error(await readError(r));return r.json()}

const has=(p:string[],c:string)=>p.includes(c);
const RISK_LABEL:Record<string,string>={LOW:'Faible',MEDIUM:'Modéré',HIGH:'Élevé',CRITICAL:'Critique'};
const ACTION_LABEL:Record<string,string>={ACCESS_ROLE_CREATED:'Rôle créé',ACCESS_ROLE_UPDATED:'Rôle modifié',ACCESS_ROLE_ARCHIVED:'Rôle archivé',ACCESS_ROLE_ASSIGNED:'Rôle attribué',ACCESS_ROLE_REVOKED:'Rôle retiré',
  ACCESS_MEMBER_CREATED:'Membre créé',ACCESS_MEMBER_ATTACHED:'Compte existant rattaché',ACCESS_MEMBER_UPDATED:'Membre modifié',ACCESS_MEMBER_DEACTIVATED:'Membre désactivé',ACCESS_MEMBER_ACTIVATED:'Membre réactivé',ACCESS_MEMBER_CREDENTIALS_RESET:'Mot de passe réinitialisé'};
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
    chevron:<><path d="m9 6 6 6-6 6"/></>,
    userPlus:<><path d="M15 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M20 8v6M23 11h-6"/></>,
    power:<><path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/></>,
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
  const canCreate=has(permissions,'access.users.create'),canUpdate=has(permissions,'access.users.update'),canActivate=has(permissions,'access.users.activate'),canReset=has(permissions,'access.users.credentials.reset');
  const [tab,setTab]=useState<Tab>(canRead?'members':'journal');
  const [loading,setLoading]=useState(true),[error,setError]=useState('');
  const [catalog,setCatalog]=useState<Domain[]>([]),[roles,setRoles]=useState<Role[]>([]),[members,setMembers]=useState<Member[]>([]);
  const [journal,setJournal]=useState<JournalItem[]>([]),[scopes,setScopes]=useState<ScopeOptions>({sections:[],classes:[]});
  const [q,setQ]=useState('');
  const [editor,setEditor]=useState<{mode:'create'|'edit';role?:Role;base?:Role}|null>(null);
  const [assignFor,setAssignFor]=useState<Member|null>(null);
  const [confirm,setConfirm]=useState<{title:string;text:string;cta:string;run:(reason:string)=>Promise<void>}|null>(null);
  const [openId,setOpenId]=useState<string|null>(null),[adding,setAdding]=useState(false),[secret,setSecret]=useState<{title:string;name:string;email:string;password:string}|null>(null);
  const [status,setStatus]=useState<'all'|'active'|'inactive'>('active'),[limit,setLimit]=useState(30);

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
  const filtered=members.filter(m=>(status==='all'||(status==='active'?m.active:!m.active))&&(!q.trim()||`${m.full_name} ${m.email} ${m.roles.map(r=>r.role_label).join(' ')}`.toLowerCase().includes(q.trim().toLowerCase())));
  const opened=members.find(m=>m.membership_id===openId)||null;
  const inactiveCount=members.filter(m=>!m.active).length;

  async function revoke(m:Member,r:MemberRole){
    setConfirm({title:`Retirer « ${r.role_label} »`,text:`${m.full_name} perdra immédiatement les droits de ce rôle, sans reconnexion.`,cta:'Retirer le rôle',
      run:async reason=>{await send(token,'POST',`assignments/${r.assignment_id}/revoke`,{reason});toast.success('Rôle retiré — effet immédiat');await load()}});
  }
  function memberAction(m:Member,kind:'deactivate'|'activate'|'reset'){
    if(kind==='reset'){setConfirm({title:'Réinitialiser le mot de passe',text:`${m.full_name} recevra un nouveau mot de passe provisoire, à remplacer à sa prochaine connexion. Toutes ses sessions sont coupées.`,cta:'Réinitialiser',
      run:async reason=>{const r=await send<{temporary_password:string}>(token,'POST',`members/${m.membership_id}/credentials-reset`,{reason});setSecret({title:'Nouveau mot de passe provisoire',name:m.full_name,email:m.email,password:r.temporary_password});await load()}});return}
    const off=kind==='deactivate';
    setConfirm({title:off?`Désactiver ${m.full_name}`:`Réactiver ${m.full_name}`,text:off?'Son accès à cette école est coupé immédiatement (sessions comprises). Ses rôles et son historique sont conservés ; son compte reste valable dans ses autres écoles.':'Son accès à cette école est rétabli avec ses rôles actuels.',cta:off?'Désactiver':'Réactiver',
      run:async reason=>{await send(token,'POST',`members/${m.membership_id}/${kind}`,{reason});toast.success(off?'Membre désactivé — effet immédiat':'Membre réactivé');await load()}});
  }
  async function archive(role:Role){
    setConfirm({title:`Archiver « ${role.label} »`,text:'Le rôle ne pourra plus être attribué. Il doit d’abord être retiré à toutes les personnes qui le détiennent.',cta:'Archiver',
      run:async reason=>{await send(token,'POST',`roles/${role.id}/archive`,{reason});toast.success('Rôle archivé');await load()}});
  }

  return <div className="personnelPage accessPage pageEnter">
    <div className="personnelHero">
      <div><span className="eyebrow"><Icon name="shield" size={14}/> Gouvernance des accès</span><h2>Accès & rôles</h2>
        <p>Votre école décide de sa propre politique d’accès. Les garde-fous de sécurité s’appliquent automatiquement, et chaque changement est inscrit au journal.</p></div>
      <div className="heroActions">{canCreate&&<button className="primaryBtn" onClick={()=>setAdding(true)}><Icon name="userPlus" size={16}/> Ajouter un membre</button>}{canManageRoles&&<button className={canCreate?'softBtn':'primaryBtn'} onClick={()=>setEditor({mode:'create'})}><Icon name="plus" size={16}/> Nouveau rôle</button>}</div>
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
      <div className="cardHeading"><div><h3>Membres de l’école</h3><p>Touchez un membre pour voir ses rôles et agir. Chaque attribution précise un périmètre et, si besoin, une date de fin.</p></div>
        <label className="searchBox accessSearch"><Icon name="search" size={16}/><input value={q} onChange={e=>{setQ(e.target.value);setLimit(30)}} placeholder="Nom, e-mail ou rôle" aria-label="Rechercher un membre" type="search" enterKeyHint="search"/></label></div>
      <div className="memberFilters" role="radiogroup" aria-label="Filtrer par statut">
        {([['active','Actifs',members.length-inactiveCount],['inactive','Désactivés',inactiveCount],['all','Tous',members.length]] as const).map(([k,l,n])=><button key={k} type="button" role="radio" aria-checked={status===k} className={status===k?'on':''} onClick={()=>{setStatus(k);setLimit(30)}}>{l} <span>{n}</span></button>)}
      </div>
      <ul className="memberList" aria-label="Membres">
        {filtered.slice(0,limit).map(m=><li key={m.membership_id}><button type="button" className={`memberRow ${m.active?'':'inactive'}`} onClick={()=>setOpenId(m.membership_id)} aria-label={`Ouvrir la fiche de ${m.full_name}`}>
          <span className="avatar">{initials(m.full_name)}</span>
          <span className="memberIdentity"><b>{m.full_name}{m.is_me&&<em className="meBadge">Vous</em>}</b><small>{m.email}</small></span>
          <span className="memberSummary">{m.roles.length===0?<span className="noRole">Aucun rôle</span>:<><span className={`roleChip ${m.roles[0].role_kind==='SCHOOL_CUSTOM'?'custom':''}`}><b>{m.roles[0].role_label}</b></span>{m.roles.length>1&&<span className="moreRoles">+{m.roles.length-1}</span>}</>}</span>
          <span className="memberState">{!m.active?<em className="statePill off">Désactivé</em>:m.must_change_password?<em className="statePill wait" title="Doit choisir son mot de passe à la prochaine connexion">Mot de passe provisoire</em>:null}</span>
          <Icon name="chevron" size={18}/>
        </button></li>)}
      </ul>
      {filtered.length>limit&&<button type="button" className="softBtn moreBtn" onClick={()=>setLimit(n=>n+30)}>Afficher plus ({filtered.length-limit} restants)</button>}
      {!loading&&!filtered.length&&<div className="personEmpty"><span><Icon name="users" size={26}/></span><b>{q.trim()?'Aucun membre trouvé':status==='inactive'?'Aucun membre désactivé':'Aucun membre'}</b><small>{q.trim()?'Modifiez la recherche.':canCreate?'Ajoutez le premier membre de votre équipe.':''}</small>{canCreate&&!q.trim()&&status!=='inactive'&&<button className="primaryBtn" onClick={()=>setAdding(true)}><Icon name="userPlus" size={16}/> Ajouter un membre</button>}</div>}
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

    {/* Overlays live at the end of <body>: the page's entry animation (a transform) would otherwise pin them to the page, not the screen. */}
    {createPortal(<>
    {editor&&<RoleEditor token={token} catalog={catalog} capIndex={capIndex} editor={editor} readOnly={editor.mode==='edit'&&(!editor.role?.editable||!canManageRoles)}
      onClose={()=>setEditor(null)} onSaved={async()=>{setEditor(null);await load()}}/>}
    {opened&&<MemberSheet member={opened} canAssign={canAssign} canUpdate={canUpdate} canActivate={canActivate} canReset={canReset} token={token}
      onClose={()=>setOpenId(null)} onAssign={()=>setAssignFor(opened)} onRevoke={r=>void revoke(opened,r)} onAction={k=>memberAction(opened,k)} onRenamed={load}/>}
    {assignFor&&<AssignDialog token={token} member={assignFor} roles={activeRoles} scopes={scopes} canScope={canScope}
      onClose={()=>setAssignFor(null)} onSaved={async()=>{setAssignFor(null);await load()}}/>}
    {adding&&<AddMemberDialog token={token} roles={activeRoles} canAssign={canAssign} onClose={()=>setAdding(false)}
      onDone={async r=>{setAdding(false);if(r.temporary_password)setSecret({title:'Compte créé',name:r.full_name,email:r.email,password:r.temporary_password});else if(r.invitation_sent)toast.success(`Invitation envoyée à ${r.email} : lien valable 48 heures, utilisable une seule fois.`);else toast.success(r.attached_existing_account?`${r.full_name} a déjà un compte EduSync : il est rattaché à votre école et se connecte avec ses identifiants habituels.`:'Membre ajouté');await load()}}/>}
    {secret&&<SecretDialog {...secret} onClose={()=>setSecret(null)}/>}
    {confirm&&<ReasonDialog {...confirm} onClose={()=>setConfirm(null)}/>}
    </>,document.body)}
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

/* ------------------------------------------------------------------ members (N2, owner decisions 2026-10-14) */

function MemberSheet({member,canAssign,canUpdate,canActivate,canReset,token,onClose,onAssign,onRevoke,onAction,onRenamed}:{member:Member;canAssign:boolean;canUpdate:boolean;canActivate:boolean;canReset:boolean;token:string;
  onClose:()=>void;onAssign:()=>void;onRevoke:(r:MemberRole)=>void;onAction:(k:'deactivate'|'activate'|'reset')=>void;onRenamed:()=>Promise<void>}){
  const [renaming,setRenaming]=useState(false),[name,setName]=useState(member.full_name),[reason,setReason]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
  const locked=member.is_me;
  async function rename(){if(name.trim().length<3||reason.trim().length<3)return;try{setBusy(true);await send(token,'PATCH',`members/${member.membership_id}`,{full_name:name.trim(),reason:reason.trim()});toast.success('Nom modifié');setRenaming(false);await onRenamed()}catch(e){toast.error(friendlyError(e))}finally{setBusy(false)}}
  return <div className="sheetBackdrop" onClick={onClose}><aside className="memberSheet" role="dialog" aria-modal="true" aria-label={`Fiche de ${member.full_name}`} onClick={e=>e.stopPropagation()}>
    <header className="sheetHead"><div className="memberSheetWho"><span className="avatar lg">{initials(member.full_name)}</span><div><h3>{member.full_name}{member.is_me&&<em className="meBadge">Vous</em>}</h3><small>{member.email}</small></div></div>
      <button className="iconAction" aria-label="Fermer" onClick={onClose}><Icon name="x" size={16}/></button></header>
    <div className="sheetBody">
      <div className="memberFacts">
        <span className={`statePill ${member.active?'ok':'off'}`}>{member.active?'Actif':'Désactivé'}</span>
        {member.must_change_password&&<span className="statePill wait">Mot de passe provisoire à remplacer</span>}
        {member.shared_account&&<span className="statePill info" title="Ce compte sert aussi dans une autre école ou dans l’Atelier Pro">Compte partagé</span>}
      </div>
      {locked&&<p className="sheetNote"><Icon name="lock" size={14}/> C’est votre compte : vos droits ne se modifient pas ici, et votre mot de passe se change dans « Sécurité et appareils ».</p>}
      <section className="sheetSection"><div className="sheetSectionHead"><h4>Rôles</h4>{canAssign&&!locked&&member.active&&<button className="softBtn" onClick={onAssign}><Icon name="plus" size={15}/> Attribuer un rôle</button>}</div>
        {member.roles.length===0?<p className="noRole">Aucun rôle : ce membre ne voit encore rien de l’école.</p>:
        <ul className="sheetRoles">{member.roles.map(r=><li key={r.assignment_id}><span><b>{r.role_label}</b><small>{r.scopes.map(scopeText).join(' · ')}{r.valid_until?` · jusqu’au ${dateFr(r.valid_until)}`:''}</small></span>
          {canAssign&&!locked&&<button className="textBtn danger" onClick={()=>onRevoke(r)} aria-label={`Retirer le rôle ${r.role_label}`}>Retirer</button>}</li>)}</ul>}
      </section>
      {!locked&&(canUpdate||canReset||canActivate)&&<section className="sheetSection"><div className="sheetSectionHead"><h4>Compte</h4></div>
        {renaming?<div className="renameBox"><label>Nom complet *<input value={name} onChange={e=>setName(e.target.value)} autoComplete="name" maxLength={180}/></label><label>Motif *<input value={reason} onChange={e=>setReason(e.target.value)} placeholder="Ex. faute de frappe"/></label>
          <div className="modalActions"><button className="ghost" onClick={()=>setRenaming(false)}>Annuler</button><button disabled={busy||name.trim().length<3||reason.trim().length<3} onClick={()=>void rename()}>{busy?'Enregistrement…':'Enregistrer'}</button></div></div>:
        <div className="accountActions">
          {canUpdate&&<button className="actionRow" disabled={member.shared_account} onClick={()=>setRenaming(true)}><Icon name="edit" size={17}/><span><b>Modifier le nom</b><small>{member.shared_account?'Compte partagé : seul son titulaire peut le modifier.':'Corrige le nom affiché partout dans l’école.'}</small></span></button>}
          {canReset&&member.active&&<button className="actionRow" disabled={member.shared_account} onClick={()=>onAction('reset')}><Icon name="key" size={17}/><span><b>Réinitialiser le mot de passe</b><small>{member.shared_account?'Compte partagé avec un autre espace : réinitialisation par son titulaire ou la plateforme.':'Mot de passe oublié : un provisoire est généré, ses sessions sont coupées.'}</small></span></button>}
          {canActivate&&<button className={`actionRow ${member.active?'danger':''}`} onClick={()=>onAction(member.active?'deactivate':'activate')}><Icon name="power" size={17}/><span><b>{member.active?'Désactiver l’accès':'Réactiver l’accès'}</b><small>{member.active?'Départ, suspension : coupe immédiatement l’accès à cette école.':'Rétablit l’accès avec ses rôles actuels.'}</small></span></button>}
        </div>}
      </section>}
    </div>
  </aside></div>;
}

type CreatedMember={membership_id:string;email:string;full_name:string;created:boolean;attached_existing_account:boolean;temporary_password:string|null;invitation_sent?:boolean};

function AddMemberDialog({token,roles,canAssign,onClose,onDone}:{token:string;roles:Role[];canAssign:boolean;onClose:()=>void;onDone:(r:CreatedMember)=>Promise<void>}){
  const [email,setEmail]=useState(''),[name,setName]=useState(''),[roleId,setRoleId]=useState(''),[reason,setReason]=useState('Arrivée dans l’équipe'),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [delivery,setDelivery]=useState<'TEMPORARY_PASSWORD'|'INVITATION'>('TEMPORARY_PASSWORD');
  const [touched,setTouched]=useState(false);
  const emailOk=/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim()),nameOk=name.trim().length>=3,reasonOk=reason.trim().length>=3;
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[onClose]);
  async function save(e:React.FormEvent){e.preventDefault();setTouched(true);setError('');if(!emailOk||!nameOk||!reasonOk)return;
    try{setBusy(true);const r=await send<CreatedMember>(token,'POST','members',{email:email.trim().toLowerCase(),full_name:name.trim(),role_id:roleId||null,reason:reason.trim(),delivery});await onDone(r)}
    catch(err){setError(err instanceof Error?err.message:friendlyError(err))}finally{setBusy(false)}}
  return <div className="wizardBackdrop" onClick={onClose}><form className="accountSecurityDialog addMemberDialog" role="dialog" aria-modal="true" aria-label="Ajouter un membre" onClick={e=>e.stopPropagation()} onSubmit={save} noValidate>
    <div className="modalHead"><div><h3>Ajouter un membre</h3><p>Un compte est créé avec un mot de passe provisoire, affiché une seule fois. Si l’adresse a déjà un compte EduSync, il est simplement rattaché à votre école.</p></div><button type="button" aria-label="Fermer" onClick={onClose}>×</button></div>
    <label>Adresse e-mail *<input type="email" inputMode="email" autoComplete="off" value={email} onChange={e=>setEmail(e.target.value)} aria-invalid={touched&&!emailOk} placeholder="prenom.nom@ecole.cd" autoFocus/>{touched&&!emailOk&&<small className="fieldError">Saisissez une adresse e-mail valide.</small>}</label>
    <label>Nom complet *<input autoComplete="off" value={name} onChange={e=>setName(e.target.value)} aria-invalid={touched&&!nameOk} maxLength={180}/>{touched&&!nameOk&&<small className="fieldError">Indiquez le nom complet (3 caractères minimum).</small>}</label>
    {canAssign&&<label>Premier rôle<select value={roleId} onChange={e=>setRoleId(e.target.value)}><option value="">Aucun pour l’instant</option>
      <optgroup label="Rôles propres à l’école">{roles.filter(r=>r.kind==='SCHOOL_CUSTOM').map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</optgroup>
      <optgroup label="Rôles standards EduSync">{roles.filter(r=>r.kind==='SCHOOL_STANDARD').map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</optgroup></select>
      <small className="fieldHint">Attribué sur toute l’école. Vous pourrez le limiter à une section ou une classe ensuite.</small></label>}
    <label>Motif *<input value={reason} onChange={e=>setReason(e.target.value)} aria-invalid={touched&&!reasonOk}/></label>
    <fieldset className="memberDelivery"><legend>Accès du nouveau compte</legend>
      <label className="toggleLine"><input type="radio" name="delivery" checked={delivery==='TEMPORARY_PASSWORD'} onChange={()=>setDelivery('TEMPORARY_PASSWORD')}/> Mot de passe provisoire, affiché une seule fois</label>
      <label className="toggleLine"><input type="radio" name="delivery" checked={delivery==='INVITATION'} onChange={()=>setDelivery('INVITATION')}/> Invitation par e-mail (lien valable 48 h, aucun mot de passe envoyé)</label>
    </fieldset>
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="modalActions"><button type="button" className="ghost" onClick={onClose}>Annuler</button><button disabled={busy}>{busy?'Création…':'Ajouter'}</button></div>
  </form></div>;
}

/** Temporary password shown once (creation or reset). It must be handed over through a safe channel. */
function SecretDialog({title,name,email,password,onClose}:{title:string;name:string;email:string;password:string;onClose:()=>void}){
  const [kept,setKept]=useState(false);
  return <div className="wizardBackdrop"><div className="accountSecurityDialog secretDialog" role="alertdialog" aria-modal="true" aria-label={title}>
    <div className="modalHead"><div><h3>{title}</h3><p>{name} · {email}</p></div></div>
    <p className="secretLead">Mot de passe provisoire — il ne sera plus jamais affiché :</p>
    <div className="secretBox"><code>{password}</code><button type="button" className="softBtn" onClick={()=>{void navigator.clipboard?.writeText(password).then(()=>toast.success('Copié'))}}><Icon name="copy" size={15}/> Copier</button></div>
    <p className="secretHint"><Icon name="alert" size={14}/> Remettez-le en main propre ou par un canal sûr. {name.split(' ')[0]} devra choisir son propre mot de passe à sa première connexion.</p>
    <label className="toggleLine"><input type="checkbox" checked={kept} onChange={e=>setKept(e.target.checked)}/> J’ai noté ou transmis ce mot de passe</label>
    <div className="modalActions"><button disabled={!kept} onClick={onClose}>Terminer</button></div>
  </div></div>;
}
