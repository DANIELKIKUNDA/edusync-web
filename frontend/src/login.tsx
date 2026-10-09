import React,{useEffect,useRef,useState} from 'react';
import {useForm} from 'react-hook-form';
import {z} from 'zod';
import {zodResolver} from '@hookform/resolvers/zod';
import {createFirstManager,HttpLoginError,loginAuto,loginPlatform,loginSchool,setupStatus,type LoginContext,type SchoolLoginResult,type SetupStatus} from './api';
import {friendlyError,UserFacingError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import './login.css';

const schema=z.object({email:z.string().trim().email('Saisissez une adresse e-mail valide.'),password:z.string().min(1,'Le mot de passe est obligatoire.')});
type Form=z.infer<typeof schema>;
type Saved={token:string;school:SchoolLoginResult['school'];user:SchoolLoginResult['user'];permissions:string[]};
type PlatformIdentity={full_name:string;email:string};

function Brand({light}:{light?:boolean}){return <div className={`lg-brand ${light?'lg-brand-light':''}`}><img src="/icons/edusync-mark.svg" alt="" width={36} height={36}/><span><b>EduSync</b><small>Gestion scolaire</small></span></div>}

function PasswordInput({id,autoComplete,reg,invalid}:{id:string;autoComplete:string;reg:any;invalid:boolean}){
 const [shown,setShown]=useState(false);
 return <div className="lg-pass"><input id={id} type={shown?'text':'password'} autoComplete={autoComplete} aria-invalid={invalid} aria-describedby={invalid?`${id}-err`:undefined} {...reg}/>
  <button type="button" onClick={()=>setShown(x=>!x)} aria-label={shown?'Masquer le mot de passe':'Afficher le mot de passe'} aria-pressed={shown}><NavGlyph g={shown?'eyeOff':'eye'} size={18}/></button></div>
}

function Field({id,label,error,hint,children}:{id:string;label:string;error?:string;hint?:string;children:React.ReactNode}){
 return <div className={`lg-field ${error?'lg-invalid':''}`}><label htmlFor={id}>{label}</label>{children}{error?<small id={`${id}-err`} role="alert">{error}</small>:hint?<small className="lg-hint">{hint}</small>:null}</div>
}

const setupSchema=z.object({full_name:z.string().trim().min(3,'Indiquez le nom complet.'),email:z.string().trim().email('Saisissez une adresse e-mail valide.'),password:z.string().min(12,'Au moins 12 caractères.'),confirm:z.string().min(1,'Confirmez le mot de passe.'),setup_token:z.string().optional()}).refine(v=>v.password===v.confirm,{message:'Les deux mots de passe ne correspondent pas.',path:['confirm']});
type SetupForm=z.infer<typeof setupSchema>;

function FirstRunSetup({status,onCreated}:{status:SetupStatus;onCreated:(email:string)=>void}){
 const [error,setError]=useState('');
 const f=useForm<SetupForm>({resolver:zodResolver(setupSchema),defaultValues:{full_name:'',email:'',password:'',confirm:'',setup_token:''},mode:'onTouched'});
 const submit=f.handleSubmit(async v=>{setError('');if(status.token_required&&!v.setup_token?.trim()){setError('Le code d’installation est obligatoire sur ce serveur.');return}
  try{const r=await createFirstManager({full_name:v.full_name.trim(),email:v.email.trim().toLowerCase(),password:v.password,setup_token:v.setup_token?.trim()||undefined});onCreated(r.email)}catch(e){setError(e instanceof UserFacingError?e.message:friendlyError(e))}});
 const e=f.formState.errors;
 return <form className="lg-card" onSubmit={submit} noValidate aria-labelledby="setup-title">
  <div className="lg-head"><span className="lg-step">Première installation</span><h1 id="setup-title">Créer le Manager Système</h1><p>Ce compte administre la plateforme : création des écoles et de leurs administrateurs. Cette étape n’est possible qu’une seule fois.</p></div>
  <Field id="su-name" label="Nom complet" error={e.full_name?.message}><input id="su-name" autoComplete="name" {...f.register('full_name')}/></Field>
  <Field id="su-email" label="Adresse e-mail" error={e.email?.message}><input id="su-email" type="email" autoComplete="username" {...f.register('email')}/></Field>
  <Field id="su-pass" label="Mot de passe" error={e.password?.message} hint="12 caractères minimum. Conservez-le en lieu sûr."><PasswordInput id="su-pass" autoComplete="new-password" reg={f.register('password')} invalid={!!e.password}/></Field>
  <Field id="su-confirm" label="Confirmer le mot de passe" error={e.confirm?.message}><PasswordInput id="su-confirm" autoComplete="new-password" reg={f.register('confirm')} invalid={!!e.confirm}/></Field>
  {status.token_required&&<Field id="su-token" label="Code d’installation" hint="Fourni par l’opérateur du serveur."><input id="su-token" autoComplete="off" {...f.register('setup_token')}/></Field>}
  {error&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{error}</div>}
  <button className="lg-submit" disabled={f.formState.isSubmitting}>{f.formState.isSubmitting?<><i className="lg-spin"/>Création…</>:'Créer le compte et continuer'}</button>
 </form>
}

function loginMessage(e:unknown){
 if(e instanceof TypeError||(e instanceof DOMException&&e.name==='AbortError'))return 'Le serveur ne répond pas pour le moment. Vérifiez votre connexion puis réessayez.';
 if(e instanceof HttpLoginError&&e.status===429)return 'Trop de tentatives. Pour votre sécurité, réessayez dans quelques minutes.';
 if(e instanceof HttpLoginError&&e.status>=500)return 'Service momentanément indisponible. Réessayez dans un instant.';
 return 'Adresse e-mail ou mot de passe incorrect, ou compte sans accès actif.';
}

/** After authentication, an account that opens several spaces picks one. Nothing is stored before the choice. */
function ContextChooser({contexts,busy,error,onPick,onBack}:{contexts:LoginContext[];busy:string;error:string;onPick:(c:LoginContext)=>void;onBack:()=>void}){
 const first=useRef<HTMLButtonElement>(null);
 useEffect(()=>{first.current?.focus()},[]);
 return <div className="lg-card" role="group" aria-labelledby="ctx-title">
  <div className="lg-head"><h1 id="ctx-title">Choisir un espace</h1><p>Votre compte donne accès à plusieurs espaces. Lequel voulez-vous ouvrir ?</p></div>
  <ul className="lg-ctx">{contexts.map((c,i)=>{const key=c.scope+(c.school_code||'');return <li key={key}>
   <button ref={i===0?first:undefined} type="button" disabled={!!busy} onClick={()=>onPick(c)}>
    <span className={`lg-ctx-ico ${c.scope==='PLATFORM'?'lg-ctx-pf':''}`}><NavGlyph g={c.scope==='PLATFORM'?'shield':'school'} size={18}/></span>
    <span className="lg-ctx-txt"><b>{c.scope==='PLATFORM'?'Atelier Pro':c.label}</b><small>{c.scope==='PLATFORM'?'Administration de la plateforme':`Établissement · ${c.school_code}`}</small></span>
    {busy===key?<i className="lg-spin lg-spin-dark"/>:<NavGlyph g="chevronRight" size={18}/>}
   </button></li>})}</ul>
  {error&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{error}</div>}
  <button type="button" className="lg-link" onClick={onBack} disabled={!!busy}>Utiliser un autre compte</button>
 </div>
}

export function SecureLogin({onPlatform,onSchool}:{onPlatform:(token:string,user:PlatformIdentity)=>void;onSchool:(s:Saved)=>void}){
 const [serverError,setServerError]=useState('');
 const [setup,setSetup]=useState<SetupStatus|null>(null);const [created,setCreated]=useState('');
 const [choice,setChoice]=useState<LoginContext[]|null>(null);const [busy,setBusy]=useState('');const [atelier,setAtelier]=useState(false);
 const pending=useRef<{email:string;password:string}|null>(null);
 const {register,handleSubmit,setValue,reset,formState:{errors,isSubmitting}}=useForm<Form>({resolver:zodResolver(schema),defaultValues:{email:'',password:''}});
 useEffect(()=>{let alive=true;setupStatus().then(s=>{if(alive)setSetup(s)}).catch(()=>{/* serveur injoignable : la connexion affichera l’erreur */});return()=>{alive=false}},[]);
 useEffect(()=>()=>{pending.current=null},[]);
 const finish=(r:any)=>{pending.current=null;if(r.scope==='PLATFORM')onPlatform(r.access_token,{full_name:r.user.full_name,email:r.user.email});else onSchool({token:r.access_token,school:r.school,user:r.user,permissions:r.permissions})};
 const submit=handleSubmit(async v=>{setServerError('');try{const email=v.email.trim();if(atelier){finish(await loginPlatform(email,v.password));return}const r=await loginAuto(email,v.password);
  if('choice_required' in r){pending.current={email,password:v.password};setChoice(r.contexts);return}finish(r)}catch(e){setServerError(loginMessage(e))}});
 const pick=async(c:LoginContext)=>{const cred=pending.current;if(!cred){setChoice(null);return}setServerError('');setBusy(c.scope+(c.school_code||''));
  try{finish(c.scope==='PLATFORM'?await loginPlatform(cred.email,cred.password):await loginSchool(cred.email,cred.password,c.school_code||''))}
  catch(e){setServerError(e instanceof TypeError?loginMessage(e):'Cet espace n’est plus accessible. Choisissez-en un autre ou reconnectez-vous.')}finally{setBusy('')}};
 const back=()=>{pending.current=null;setChoice(null);setServerError('');reset({email:'',password:''})};
 const showSetup=Boolean(setup?.setup_required&&setup.setup_available&&!created);
 const blockedSetup=Boolean(setup?.setup_required&&!setup.setup_available);
 return <div className="lg-page">
  <div className="lg-photo" aria-hidden="true"/>
  <div className="lg-top"><Brand light/></div>
  <div className="lg-pitch" aria-hidden="true">
   <h2>Votre établissement, piloté avec sérénité.</h2>
   <p>Inscriptions, finances, personnel et documents réunis dans un espace sécurisé, conçu pour les réseaux instables.</p>
   <ul><li><NavGlyph g="shield" size={16}/>Données isolées par établissement</li><li><NavGlyph g="wifi" size={16}/>Aucune opération en double</li><li><NavGlyph g="audit" size={16}/>Chaque action sensible tracée</li></ul>
  </div>
  <div className="lg-pane" role="main">
   {showSetup&&setup?<FirstRunSetup status={setup} onCreated={email=>{setCreated(email);setValue('email',email)}}/>:
   blockedSetup?<div className="lg-card"><div className="lg-head"><span className="lg-step">Première installation</span><h1>Installation à finaliser</h1><p>Aucun Manager Système n’existe encore. Sur ce serveur, il est créé par l’opérateur (code d’installation ou script d’administration).</p></div></div>:
   choice?<ContextChooser contexts={choice} busy={busy} error={serverError} onPick={pick} onBack={back}/>:
   <form className="lg-card" onSubmit={submit} noValidate aria-labelledby="lg-title">
    <div className="lg-head"><img className="lg-card-mark" src="/icons/edusync-mark.svg" alt="" width={44} height={44}/>{atelier&&<span className="lg-step">Atelier Pro</span>}<h1 id="lg-title">{atelier?'Accès plateforme':'Connexion'}</h1><p>{atelier?'Réservé à l’administration de la plateforme EduSync.':'Utilisez l’adresse e-mail de votre compte EduSync.'}</p></div>
    {created&&<div className="lg-ok" role="status"><NavGlyph g="checkCircle" size={16}/>Manager Système créé. Connectez-vous avec {created}.</div>}
    <Field id="lg-email" label="Adresse e-mail" error={errors.email?.message}><input id="lg-email" type="email" autoComplete="username" inputMode="email" autoFocus aria-invalid={!!errors.email} aria-describedby={errors.email?'lg-email-err':undefined} {...register('email')} placeholder="nom@ecole.cd"/></Field>
    <Field id="lg-pass" label="Mot de passe" error={errors.password?.message}><PasswordInput id="lg-pass" autoComplete="current-password" reg={register('password')} invalid={!!errors.password}/></Field>
    {serverError&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{serverError}</div>}
    <button className="lg-submit" disabled={isSubmitting}>{isSubmitting?<><i className="lg-spin"/>Vérification…</>:'Se connecter'}</button>
    <p className="lg-note"><NavGlyph g="lock" size={14}/>Connexion chiffrée. Votre établissement est reconnu automatiquement.</p>
   </form>}
   <div className="lg-foot"><span>© {new Date().getFullYear()} VolcanoTech · EduSync</span>{setup?.setup_required&&<span className="lg-foot-sep" aria-hidden="true">·</span>}{/* Shown only while no Manager système exists yet: afterwards the Manager signs in like everyone (AUTO). */Boolean(setup?.setup_required)&&!choice&&!showSetup&&<button type="button" className="lg-quiet" aria-pressed={atelier} onClick={()=>{setAtelier(x=>!x);setServerError('')}}>{atelier?'Retour à la connexion établissement':'Accès Atelier Pro (Manager système)'}</button>}</div>
  </div>
  <small className="lg-credit">Photo : Sangga Rima Roman Selia / Unsplash</small>
 </div>
}
