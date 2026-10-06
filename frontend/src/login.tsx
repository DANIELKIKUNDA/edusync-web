import React,{useEffect,useState} from 'react';
import {useForm} from 'react-hook-form';
import {z} from 'zod';
import {zodResolver} from '@hookform/resolvers/zod';
import {createFirstManager,loginPlatform,loginSchool,setupStatus,SchoolLoginResult,type SetupStatus} from './api';
import {friendlyError,UserFacingError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import './login.css';

const schema=z.object({schoolCode:z.string().max(32).optional(),email:z.string().trim().email('Saisissez une adresse e-mail valide.'),password:z.string().min(1,'Le mot de passe est obligatoire.')});
type Form=z.infer<typeof schema>;
type Saved={token:string;school:SchoolLoginResult['school'];user:SchoolLoginResult['user'];permissions:string[]};
type PlatformIdentity={full_name:string;email:string};

function Brand(){return <div className="lg-brand"><img src="/icons/edusync-mark.svg" alt="" width={40} height={40}/><span><b>EduSync</b><small>Gestion scolaire</small></span></div>}

function PasswordInput({id,autoComplete,reg,invalid}:{id:string;autoComplete:string;reg:any;invalid:boolean}){
 const [shown,setShown]=useState(false);
 return <div className="lg-pass"><input id={id} type={shown?'text':'password'} autoComplete={autoComplete} aria-invalid={invalid} {...reg}/>
  <button type="button" onClick={()=>setShown(x=>!x)} aria-label={shown?'Masquer le mot de passe':'Afficher le mot de passe'} aria-pressed={shown}><NavGlyph g={shown?'eyeOff':'eye'} size={17}/></button></div>
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
  <div className="lg-head"><span className="lg-step">Première installation</span><h2 id="setup-title">Créer le Manager Système</h2><p>Ce compte administre la plateforme : création des écoles et de leurs administrateurs. Cette étape n’est possible qu’une seule fois.</p></div>
  <Field id="su-name" label="Nom complet" error={e.full_name?.message}><input id="su-name" autoComplete="name" {...f.register('full_name')}/></Field>
  <Field id="su-email" label="Adresse e-mail" error={e.email?.message}><input id="su-email" type="email" autoComplete="username" {...f.register('email')}/></Field>
  <Field id="su-pass" label="Mot de passe" error={e.password?.message} hint="12 caractères minimum. Conservez-le en lieu sûr."><PasswordInput id="su-pass" autoComplete="new-password" reg={f.register('password')} invalid={!!e.password}/></Field>
  <Field id="su-confirm" label="Confirmer le mot de passe" error={e.confirm?.message}><PasswordInput id="su-confirm" autoComplete="new-password" reg={f.register('confirm')} invalid={!!e.confirm}/></Field>
  {status.token_required&&<Field id="su-token" label="Code d’installation" hint="Fourni par l’opérateur du serveur."><input id="su-token" autoComplete="off" {...f.register('setup_token')}/></Field>}
  {error&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{error}</div>}
  <button className="lg-submit" disabled={f.formState.isSubmitting}>{f.formState.isSubmitting?<><i className="lg-spin"/>Création…</>:'Créer le compte et continuer'}</button>
 </form>
}

export function SecureLogin({onPlatform,onSchool}:{onPlatform:(token:string,user:PlatformIdentity)=>void;onSchool:(s:Saved)=>void}){
 const [mode,setMode]=useState<'SCHOOL'|'PLATFORM'>('SCHOOL');const [serverError,setServerError]=useState('');
 const [setup,setSetup]=useState<SetupStatus|null>(null);const [created,setCreated]=useState('');
 const {register,handleSubmit,setValue,formState:{errors,isSubmitting}}=useForm<Form>({resolver:zodResolver(schema),defaultValues:{schoolCode:'',email:'',password:''}});
 useEffect(()=>{let alive=true;setupStatus().then(s=>{if(alive)setSetup(s)}).catch(()=>{/* serveur injoignable : la connexion affichera l’erreur */});return()=>{alive=false}},[]);
 const submit=handleSubmit(async v=>{setServerError(''); if(mode==='SCHOOL'&&!v.schoolCode?.trim()){setServerError('Indiquez le code de votre établissement.');return} try{if(mode==='PLATFORM'){const r=await loginPlatform(v.email.trim(),v.password);onPlatform(r.access_token,{full_name:r.user.full_name,email:r.user.email})}else{const r=await loginSchool(v.email.trim(),v.password,(v.schoolCode||'').trim().toUpperCase());const s={token:r.access_token,school:r.school,user:r.user,permissions:r.permissions};onSchool(s)}}catch(e){setServerError(e instanceof TypeError||(e instanceof DOMException&&e.name==='AbortError')?'Le serveur ne répond pas pour le moment. Vérifiez votre connexion puis réessayez.':'Connexion impossible. Vérifiez vos informations ou réessayez dans un instant.')}});
 const showSetup=Boolean(setup?.setup_required&&setup.setup_available&&!created);
 const blockedSetup=Boolean(setup?.setup_required&&!setup.setup_available);
 return <div className="lg-page">
  <section className="lg-visual" aria-hidden="true">
   <Brand/>
   <div className="lg-pitch"><h1>La gestion de votre école, fiable même quand le réseau ne l’est pas.</h1>
    <ul><li><NavGlyph g="shield" size={18}/><span>Données isolées par établissement et accès par rôle</span></li><li><NavGlyph g="wifi" size={18}/><span>Conçu pour les connexions instables, sans doublon d’opération</span></li><li><NavGlyph g="audit" size={18}/><span>Chaque opération sensible est tracée</span></li></ul></div>
   <small className="lg-sign">EduSync · par VolcanoTech</small>
  </section>
  <section className="lg-pane">
   <div className="lg-mobile-brand"><Brand/></div>
   {showSetup&&setup?<FirstRunSetup status={setup} onCreated={email=>{setCreated(email);setMode('PLATFORM');setValue('email',email)}}/>:
   blockedSetup?<div className="lg-card"><div className="lg-head"><span className="lg-step">Première installation</span><h2>Installation à finaliser</h2><p>Aucun Manager Système n’existe encore. Sur ce serveur, il est créé par l’opérateur (code d’installation ou script d’administration).</p></div></div>:
   <form className="lg-card" onSubmit={submit} noValidate aria-labelledby="lg-title">
    <div className="lg-head">{mode==='PLATFORM'&&<span className="lg-step">Atelier Pro</span>}<h2 id="lg-title">{mode==='SCHOOL'?'Connexion':'Accès plateforme'}</h2><p>{mode==='SCHOOL'?'Accédez à l’espace de travail de votre établissement.':'Réservé à l’administration de la plateforme EduSync.'}</p></div>
    {created&&<div className="lg-ok" role="status"><NavGlyph g="checkCircle" size={16}/>Manager Système créé. Connectez-vous avec {created}.</div>}
    {mode==='SCHOOL'&&<Field id="lg-code" label="Code établissement" error={errors.schoolCode?.message}><input id="lg-code" autoComplete="organization" autoCapitalize="characters" spellCheck={false} {...register('schoolCode')} onInput={e=>{e.currentTarget.value=e.currentTarget.value.toUpperCase()}} placeholder="Ex. : EXCELLENCIA"/></Field>}
    <Field id="lg-email" label="Adresse e-mail" error={errors.email?.message}><input id="lg-email" type="email" autoComplete="username" inputMode="email" {...register('email')} placeholder="nom@ecole.cd"/></Field>
    <Field id="lg-pass" label="Mot de passe" error={errors.password?.message}><PasswordInput id="lg-pass" autoComplete="current-password" reg={register('password')} invalid={!!errors.password}/></Field>
    {serverError&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{serverError}</div>}
    <button className="lg-submit" disabled={isSubmitting}>{isSubmitting?<><i className="lg-spin"/>Vérification…</>:'Se connecter'}</button>
    <p className="lg-note"><NavGlyph g="lock" size={14}/>Après plusieurs tentatives infructueuses, l’accès est temporairement protégé.</p>
    <button type="button" className="lg-switch" onClick={()=>{setMode(m=>m==='SCHOOL'?'PLATFORM':'SCHOOL');setServerError('')}}>{mode==='SCHOOL'?'Accès Atelier Pro (Manager système)':'Retour à la connexion établissement'}</button>
   </form>}
   <footer className="lg-foot">© {new Date().getFullYear()} VolcanoTech · EduSync</footer>
  </section>
 </div>
}
