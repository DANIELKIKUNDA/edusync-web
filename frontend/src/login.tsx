import React,{useEffect,useRef,useState} from 'react';
import {useForm} from 'react-hook-form';
import {z} from 'zod';
import {zodResolver} from '@hookform/resolvers/zod';
import {createFirstManager,firstPasswordChange,HttpLoginError,isMfaStep,isPasswordChangeStep,loginAuto,loginPlatform,loginSchool,MfaError,mfaEnrollConfirm,mfaEnrollStart,mfaVerify,setupStatus,type LoginContext,type MfaEnrollment as MfaEnrollmentData,type MfaStep,type SchoolLoginResult,type SetupStatus} from './api';
import {toast} from 'sonner';
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

/* ---------------------------------------------------------------- second factor (platform accounts, option B) */

function mfaMessage(e:unknown,fallback='Vérification impossible. Réessayez.'){
 if(e instanceof MfaError)return e.message;
 if(e instanceof TypeError)return 'Le serveur ne répond pas pour le moment. Vérifiez votre connexion puis réessayez.';
 return fallback;
}
const expired=(e:unknown)=>e instanceof MfaError&&e.status===401;

/** Six-digit input: digits only, paste accepted (spaces removed), numeric keypad and SMS/OTP autofill on phones. */
function CodeInput({id,value,onChange,disabled,describedBy,autoFocus=true}:{id:string;value:string;onChange:(v:string)=>void;disabled?:boolean;describedBy?:string;autoFocus?:boolean}){
 return <input id={id} className="mfa-code" value={value} disabled={disabled} autoFocus={autoFocus} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={7}
  aria-describedby={describedBy} placeholder="000000" onChange={e=>onChange(e.target.value.replace(/\D/g,'').slice(0,6))}/>
}

function MfaChallenge({step,onDone,onRestart}:{step:MfaStep;onDone:(r:any)=>void;onRestart:()=>void}){
 const [mode,setMode]=useState<'totp'|'recovery'>('totp');const [code,setCode]=useState('');const [recovery,setRecovery]=useState('');
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [dead,setDead]=useState(false);
 const sent=useRef('');
 async function submit(value=code){
  if(busy)return;setError('');
  if(mode==='totp'&&value.length!==6){setError('Saisissez les 6 chiffres affichés par votre application.');return}
  if(mode==='recovery'&&recovery.replace(/[^a-z0-9]/gi,'').length<10){setError('Saisissez un code de secours complet (10 caractères).');return}
  setBusy(true);
  try{const r=await mfaVerify(step.mfa_token,mode==='totp'?{code:value}:{recovery_code:recovery.trim()});
   if(typeof r.recovery_codes_remaining==='number')toast.warning(r.recovery_codes_remaining<=3?`Il ne vous reste que ${r.recovery_codes_remaining} code(s) de secours. Générez-en de nouveaux depuis « Sécurité et appareils ».`:`Code de secours utilisé. Il vous en reste ${r.recovery_codes_remaining}.`);
   onDone(r)}
  catch(e){setError(mfaMessage(e));if(expired(e))setDead(true);setCode('');sent.current=''}
  finally{setBusy(false)}
 }
 // The code is sent as soon as the sixth digit is typed or pasted (once per value).
 const change=(v:string)=>{setCode(v);if(v.length===6&&sent.current!==v&&!dead){sent.current=v;void submit(v)}};
 return <form className="lg-card" onSubmit={e=>{e.preventDefault();void submit()}} noValidate aria-labelledby="mfa-title">
  <div className="lg-head"><span className="lg-step">{step.scope==='SCHOOL'?'Sécurité du compte':'Atelier Pro'} · Validation en deux étapes</span><h1 id="mfa-title">{mode==='totp'?'Code de vérification':'Code de secours'}</h1>
   <p>{mode==='totp'?`Ouvrez votre application d’authentification et saisissez le code à 6 chiffres affiché pour EduSync Atelier Pro.${step.scope==='SCHOOL'?' Votre compte est protégé par un second facteur : il est demandé dans chaque espace.':''}`:'Saisissez l’un des codes de secours que vous avez conservés lors de l’activation. Chaque code ne sert qu’une fois.'}</p></div>
  {mode==='totp'
   ?<div className="lg-field"><label htmlFor="mfa-code">Code à 6 chiffres</label><CodeInput id="mfa-code" value={code} onChange={change} disabled={busy||dead} describedBy="mfa-hint"/>
     <small id="mfa-hint" className="lg-hint">Le code change toutes les 30 secondes. Si un code est refusé, vérifiez que l’heure de votre téléphone est réglée automatiquement.</small></div>
   :<div className="lg-field"><label htmlFor="mfa-recovery">Code de secours</label><input id="mfa-recovery" value={recovery} disabled={busy||dead} autoFocus autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder="XXXXX-XXXXX" onChange={e=>setRecovery(e.target.value.toUpperCase())}/></div>}
  {error&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{error}</div>}
  {dead
   ?<button type="button" className="lg-submit" onClick={onRestart}>Revenir à la connexion</button>
   :<button className="lg-submit" disabled={busy}>{busy?<><i className="lg-spin"/>Vérification…</>:'Valider'}</button>}
  {!dead&&step.methods.includes('RECOVERY_CODE')&&<button type="button" className="lg-link" onClick={()=>{setMode(m=>m==='totp'?'recovery':'totp');setError('')}}>{mode==='totp'?'Utiliser un code de secours':'Utiliser l’application d’authentification'}</button>}
  <p className="lg-note"><NavGlyph g="lock" size={14}/>Téléphone perdu et plus de code de secours ? Un autre Manager système peut réinitialiser votre validation en deux étapes.</p>
  {!dead&&<button type="button" className="lg-link" onClick={onRestart}>Utiliser un autre compte</button>}
 </form>
}

function groupKey(secret:string){return secret.replace(/(.{4})/g,'$1 ').trim()}

function MfaEnrollment({step,onDone,onRestart}:{step:MfaStep;onDone:(r:any)=>void;onRestart:()=>void}){
 const [stage,setStage]=useState<'scan'|'confirm'|'codes'>('scan');const [data,setData]=useState<MfaEnrollmentData|null>(null);
 const [code,setCode]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [dead,setDead]=useState(false);
 const [result,setResult]=useState<any>(null);const [kept,setKept]=useState(false);const [showKey,setShowKey]=useState(false);
 const started=useRef(false);const heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{if(started.current)return;started.current=true;mfaEnrollStart(step.mfa_token).then(setData).catch(e=>{setError(mfaMessage(e,'Impossible de préparer la configuration.'));if(expired(e))setDead(true)})},[step.mfa_token]);
 useEffect(()=>{heading.current?.focus()},[stage]);
 async function confirm(value=code){
  if(busy)return;setError('');if(value.length!==6){setError('Saisissez les 6 chiffres affichés par votre application.');return}
  setBusy(true);
  try{const r=await mfaEnrollConfirm(step.mfa_token,value);setResult(r);setStage('codes')}
  catch(e){setError(mfaMessage(e));if(expired(e))setDead(true);setCode('')}
  finally{setBusy(false)}
 }
 const codesText=()=>`EduSync Atelier Pro — codes de secours\nCompte : ${data?.account||''}\nChaque code ne fonctionne qu’une seule fois.\n\n${(result?.recovery_codes||[]).join('\n')}\n`;
 function download(){const url=URL.createObjectURL(new Blob([codesText()],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='edusync-codes-de-secours.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 const progress=stage==='scan'?1:stage==='confirm'?2:3;
 return <div className="lg-card mfa-card" aria-labelledby="mfa-en-title">
  <div className="lg-head"><span className="lg-step">Sécurité du compte · Étape {progress} sur 3</span>
   <div className="mfa-progress" aria-hidden="true">{[1,2,3].map(i=><i key={i} className={i<=progress?'mfa-on':''}/>)}</div>
   <h1 id="mfa-en-title" ref={heading} tabIndex={-1}>{stage==='scan'?'Activer la validation en deux étapes':stage==='confirm'?'Confirmer avec un premier code':'Conservez vos codes de secours'}</h1>
   <p>{stage==='scan'?'Les comptes de l’Atelier Pro peuvent créer, suspendre et administrer des écoles. Un code de votre téléphone sera désormais demandé à chaque nouvelle connexion, en plus du mot de passe.'
    :stage==='confirm'?'Saisissez le code à 6 chiffres que votre application affiche maintenant pour EduSync Atelier Pro.'
    :'Si vous perdez votre téléphone, ces codes vous permettront de vous connecter. Ils ne seront plus jamais affichés.'}</p></div>
  {stage==='scan'&&<>
   <ol className="mfa-steps">
    <li>Installez une application d’authentification sur votre téléphone : Google Authenticator, Microsoft Authenticator ou tout autre application compatible TOTP.</li>
    <li>Dans l’application, ajoutez un compte en scannant ce QR code.</li>
   </ol>
   {!data&&!error&&<div className="mfa-qr mfa-qr-wait" aria-busy="true"><i className="lg-spin lg-spin-dark"/></div>}
   {data&&<>
    <img className="mfa-qr" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(data.qr_svg)}`} alt="QR code à scanner avec votre application d’authentification" width={200} height={200}/>
    <a className="mfa-open" href={data.otpauth_uri}><NavGlyph g="phone" size={16}/>Sur ce téléphone ? Ouvrir directement dans l’application</a>
    <div className="mfa-key"><button type="button" className="lg-link" aria-expanded={showKey} onClick={()=>setShowKey(x=>!x)}>{showKey?'Masquer la clé':'Impossible de scanner ? Saisir la clé manuellement'}</button>
     {showKey&&<div className="mfa-key-box"><small>Compte : {data.account} · type : basé sur l’heure (TOTP)</small><code aria-label="Clé de configuration">{groupKey(data.secret)}</code>
      <button type="button" className="mfa-copy" onClick={()=>{void navigator.clipboard?.writeText(data.secret).then(()=>toast.success('Clé copiée'))}}><NavGlyph g="doc" size={15}/>Copier la clé</button></div>}</div>
   </>}
  </>}
  {stage==='confirm'&&<div className="lg-field"><label htmlFor="mfa-first">Code à 6 chiffres</label>
   <CodeInput id="mfa-first" value={code} disabled={busy||dead} describedBy="mfa-first-hint" onChange={v=>{setCode(v);if(v.length===6)void confirm(v)}}/>
   <small id="mfa-first-hint" className="lg-hint">Le code change toutes les 30 secondes : saisissez celui qui est affiché maintenant.</small></div>}
  {stage==='codes'&&result&&<>
   <ul className="mfa-codes" aria-label="Codes de secours">{result.recovery_codes.map((c:string)=><li key={c}><code>{c}</code></li>)}</ul>
   <div className="mfa-actions"><button type="button" className="mfa-copy" onClick={()=>{void navigator.clipboard?.writeText(codesText()).then(()=>toast.success('Codes copiés'))}}><NavGlyph g="doc" size={15}/>Copier</button>
    <button type="button" className="mfa-copy" onClick={download}><NavGlyph g="download" size={15}/>Télécharger (.txt)</button></div>
   <div className="lg-ok mfa-warn" role="note"><NavGlyph g="alert" size={16}/>Rangez-les hors d’EduSync : gestionnaire de mots de passe, papier sous clé… Ne les envoyez pas par message.</div>
   <label className="mfa-check"><input type="checkbox" checked={kept} onChange={e=>setKept(e.target.checked)}/>J’ai conservé ces codes en lieu sûr</label>
  </>}
  {error&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{error}</div>}
  {dead?<button type="button" className="lg-submit" onClick={onRestart}>Revenir à la connexion</button>
   :stage==='scan'?<button type="button" className="lg-submit" disabled={!data} onClick={()=>{setError('');setStage('confirm')}}>J’ai ajouté le compte, continuer</button>
   :stage==='confirm'?<><button type="button" className="lg-submit" disabled={busy} onClick={()=>void confirm()}>{busy?<><i className="lg-spin"/>Vérification…</>:'Activer'}</button><button type="button" className="lg-link" disabled={busy} onClick={()=>{setStage('scan');setError('');setCode('')}}>Revenir au QR code</button></>
   :<button type="button" className="lg-submit" disabled={!kept} onClick={()=>onDone(result)}>Accéder à l’Atelier Pro</button>}
  {stage==='scan'&&!dead&&<button type="button" className="lg-link" onClick={onRestart}>Annuler et revenir à la connexion</button>}
 </div>
}

const newPasswordSchema=z.object({password:z.string().min(10,'Au moins 10 caractères.'),confirm:z.string().min(1,'Confirmez le mot de passe.')}).refine(v=>v.password===v.confirm,{message:'Les deux mots de passe ne correspondent pas.',path:['confirm']});
type NewPasswordForm=z.infer<typeof newPasswordSchema>;

/** First sign-in with a temporary password (set by a school administrator): the person chooses their own. */
function PasswordChangeScreen({token,email,onChanged,onRestart}:{token:string;email:string;onChanged:(password:string)=>Promise<void>;onRestart:()=>void}){
 const [error,setError]=useState('');const [dead,setDead]=useState(false);
 const f=useForm<NewPasswordForm>({resolver:zodResolver(newPasswordSchema),defaultValues:{password:'',confirm:''},mode:'onTouched'});
 const submit=f.handleSubmit(async v=>{setError('');try{await firstPasswordChange(token,v.password);await onChanged(v.password)}catch(e){setError(mfaMessage(e,'Modification impossible. Réessayez.'));if(expired(e))setDead(true)}});
 const e=f.formState.errors;
 return <form className="lg-card" onSubmit={submit} noValidate aria-labelledby="pw-title">
  <div className="lg-head"><span className="lg-step">Première connexion</span><h1 id="pw-title">Choisissez votre mot de passe</h1>
   <p>Votre administrateur vous a remis un mot de passe provisoire. Remplacez-le par un mot de passe personnel que vous seul connaissez{email?` pour ${email}`:''}.</p></div>
  <Field id="pw-new" label="Nouveau mot de passe" error={e.password?.message} hint="10 caractères minimum. Évitez votre nom ou votre date de naissance."><PasswordInput id="pw-new" autoComplete="new-password" reg={f.register('password')} invalid={!!e.password}/></Field>
  <Field id="pw-confirm" label="Confirmer le mot de passe" error={e.confirm?.message}><PasswordInput id="pw-confirm" autoComplete="new-password" reg={f.register('confirm')} invalid={!!e.confirm}/></Field>
  {error&&<div className="lg-error" role="alert"><NavGlyph g="alert" size={16}/>{error}</div>}
  {dead?<button type="button" className="lg-submit" onClick={onRestart}>Revenir à la connexion</button>
   :<button className="lg-submit" disabled={f.formState.isSubmitting}>{f.formState.isSubmitting?<><i className="lg-spin"/>Enregistrement…</>:'Enregistrer et continuer'}</button>}
  {!dead&&<button type="button" className="lg-link" onClick={onRestart}>Utiliser un autre compte</button>}
 </form>
}

export function SecureLogin({onPlatform,onSchool}:{onPlatform:(token:string,user:PlatformIdentity)=>void;onSchool:(s:Saved)=>void}){
 const [serverError,setServerError]=useState('');
 const [setup,setSetup]=useState<SetupStatus|null>(null);const [created,setCreated]=useState('');
 const [choice,setChoice]=useState<LoginContext[]|null>(null);const [busy,setBusy]=useState('');const [atelier,setAtelier]=useState(false);
 const pending=useRef<{email:string;password:string}|null>(null);
 const [mfa,setMfa]=useState<MfaStep|null>(null);
 const [pwdStep,setPwdStep]=useState<{token:string;email:string}|null>(null);const lastEmail=useRef('');
 const {register,handleSubmit,setValue,reset,formState:{errors,isSubmitting}}=useForm<Form>({resolver:zodResolver(schema),defaultValues:{email:'',password:''}});
 useEffect(()=>{let alive=true;setupStatus().then(s=>{if(alive)setSetup(s)}).catch(()=>{/* serveur injoignable : la connexion affichera l’erreur */});return()=>{alive=false}},[]);
 useEffect(()=>()=>{pending.current=null},[]);
 // Platform accounts: the password step returns a second-factor step instead of a session (option B).
 const finish=(r:any)=>{pending.current=null;if(isPasswordChangeStep(r)){setChoice(null);setPwdStep({token:r.change_token,email:lastEmail.current});return}setPwdStep(null);if(isMfaStep(r)){setChoice(null);setMfa(r);return}setMfa(null);if(r.scope==='PLATFORM')onPlatform(r.access_token,{full_name:r.user.full_name,email:r.user.email});else onSchool({token:r.access_token,school:r.school,user:r.user,permissions:r.permissions})};
 const submit=handleSubmit(async v=>{setServerError('');try{const email=v.email.trim();lastEmail.current=email;if(atelier){finish(await loginPlatform(email,v.password));return}const r=await loginAuto(email,v.password);
  if('choice_required' in r){pending.current={email,password:v.password};setChoice(r.contexts);return}finish(r)}catch(e){setServerError(loginMessage(e))}});
 const pick=async(c:LoginContext)=>{const cred=pending.current;if(!cred){setChoice(null);return}setServerError('');setBusy(c.scope+(c.school_code||''));
  try{finish(c.scope==='PLATFORM'?await loginPlatform(cred.email,cred.password):await loginSchool(cred.email,cred.password,c.school_code||''))}
  catch(e){setServerError(e instanceof TypeError?loginMessage(e):'Cet espace n’est plus accessible. Choisissez-en un autre ou reconnectez-vous.')}finally{setBusy('')}};
 // After the temporary password is replaced, sign in again with the new one: the normal path follows (space, code).
 const afterPasswordChange=async(newPassword:string)=>{const email=pwdStep?.email||lastEmail.current;const r=await loginAuto(email,newPassword);
  if('choice_required' in r){pending.current={email,password:newPassword};setPwdStep(null);setChoice(r.contexts);return}finish(r)};
 const back=()=>{pending.current=null;setChoice(null);setMfa(null);setPwdStep(null);setServerError('');reset({email:'',password:''})};
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
   pwdStep?<PasswordChangeScreen token={pwdStep.token} email={pwdStep.email} onChanged={afterPasswordChange} onRestart={back}/>:
   mfa?(mfa.mfa_enrollment_required?<MfaEnrollment step={mfa} onDone={finish} onRestart={back}/>:<MfaChallenge step={mfa} onDone={finish} onRestart={back}/>):
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
   <div className="lg-foot"><span>© {new Date().getFullYear()} VolcanoTech · EduSync</span>{setup?.setup_required&&<span className="lg-foot-sep" aria-hidden="true">·</span>}{/* Shown only while no Manager système exists yet: afterwards the Manager signs in like everyone (AUTO). */!mfa&&!pwdStep&&Boolean(setup?.setup_required)&&!choice&&!showSetup&&<button type="button" className="lg-quiet" aria-pressed={atelier} onClick={()=>{setAtelier(x=>!x);setServerError('')}}>{atelier?'Retour à la connexion établissement':'Accès Atelier Pro (Manager système)'}</button>}</div>
  </div>
  <small className="lg-credit">Photo : Sangga Rima Roman Selia / Unsplash</small>
 </div>
}
