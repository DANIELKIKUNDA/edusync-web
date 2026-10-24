import {clearPlatformContext, getPlatformAuthState, knownContext, knownPlatform, OFFLINE_PLATFORM_TOKEN, OFFLINE_SCHOOL_TOKEN, rememberPlatformContext, rememberSchoolContext, restoreOfflineContext, setPlatformAuthState} from './platform/offline_session';
import React,{lazy,Suspense,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {SecureLogin} from './login';
import {takeAccountLink,type AccountLink} from './account_links';
import {dismissBoot} from './platform/boot';
const PersonnelPage=lazy(()=>import('./personnel'));
const SchoolingPage=lazy(()=>import('./schooling'));
import EffectifsPage from './effectifs';
const DocumentsPage=lazy(()=>import('./documents'));
const FinancePage=lazy(()=>import('./finance'));
const HomePage=lazy(()=>import('./home'));
const CommunicationsPage=lazy(()=>import('./communications'));
const PlatformMessaging=lazy(()=>import('./platform/messaging'));
const StewardshipPage=lazy(()=>import('./stewardship'));
const SyncAdminPage=lazy(()=>import('./sync_admin'));
const AccessPage=lazy(()=>import('./access'));
import {
  AcademicYear,createAcademicYear,putEnrollmentWindow,activateAcademicYear,transitionAcademicYear,createClass,createFeeType,updateFeeType,createSchool,FeeType,getReferenceCatalog,
  getSettingsOverview,listAcademicYears,listYearSelector,listClasses,listFeeTypes,listSchools,listSections,listTariffs,loginPlatform,loginSchool,
  putSection,ReferenceCatalog,School,SchoolClass,SchoolLoginResult,SchoolSection,SettingsOverview,Tariff,createTariff,updateSchoolIdentity,listSettingsContributions,createSettingsContribution,listSettingsProducts,createSettingsProduct,SettingsContribution,SettingsProduct,platformSchoolsPage,platformAccess,platformAudit,platformDiagnostics,platformSuspendSchool,platformReactivateSchool,platformBootstrapAdmin,platformSystemNotifications,sendPlatformSystemNotification,platformSchoolDetail,platformRbacRoles,platformMembershipState,platformAssignRole,platformRevokeRole,platformGrantCollaborator,platformRevokeCollaborator
} from './api';
import { friendlyError } from './platform/errors';
import { toast } from 'sonner';
import {useForm} from 'react-hook-form';
import {z} from 'zod';
import {zodResolver} from '@hookform/resolvers/zod';
import {FormField,formDefaults} from './platform/forms';
import {NavGlyph} from './platform/nav_icons';
import {auditActionLabel,resultLabel,schoolStatusLabel,severityLabel,yearStatusLabel} from './platform/labels';
import {AppShell,StatusChip,type ShellAccount,type ShellNavItem} from './platform/shell';
import {NotificationBell,PreferencesDialog,ProfileDialog,SecurityDialog,StepUpDialog} from './platform/account';
import {PlatformDashboard,type DashboardTarget} from './platform/dashboard';
import {SchoolsModule,type SchoolsPreset} from './platform/schools';
import {AccessDirectory,ACCESS_URL_KEYS,type AccessPreset} from './platform/identities';
import {SchoolFormDialog} from './platform/school_sheet';
import {usePlatformTheme,type ThemePref} from './platform/theme';
import {setStepUpHandler} from './platform/connectivity';
import {fetchSpaces,OfflineAdminBanner,rememberSpace,SpaceRecovery,spaceKey,SpaceSwitcher,type SpacesState} from './platform/spaces';
const TeamPage=lazy(()=>import('./platform/team').then(m=>({default:m.TeamPage})));
type TeamPreset={openMember?:string;addExisting?:{id:string;full_name:string;email:string};nonce:number};
const HealthPanel=lazy(()=>import('./platform/health').then(m=>({default:m.HealthPanel})));
const AuditPanel=lazy(()=>import('./platform/audit').then(m=>({default:m.AuditPanel})));
const CampaignsPanel=lazy(()=>import('./platform/campaigns').then(m=>({default:m.CampaignsPanel})));
import {platformMe,platformAvatarBlob,uploadPlatformAvatar,deletePlatformAvatar,getAccessMe,type AccessMe,type PlatformMe} from './api';
import {ScreenBoundary,ScreenError} from './platform/screen_boundary';
import {Card,PageHeader,ProgressJourney,Section,Skeleton,StatusBadge,type Tone} from './platform/ui';
import {readinessSteps,SETTINGS_TARGET_KEY} from './home';
import {autoCode,yearCode as yearCodeOf,ClassBatchDialog,CONTRIBUTION_PRESETS,FEE_PRESETS,OptionCatalog,OPTIONS_SECTION,PRODUCT_PRESETS,SetupAssistant} from './settings_wizards';
import {Button as UIButton} from './platform/ui';
import {PageTrail} from './platform/navigation';
import {installMobileBackCoordinator,installUnsavedFormGuard,pushMobileScreen,replaceMobileRoot} from './platform/mobile_back';
import {confirmAction,promptText} from './platform/dialogs';
import {formatDate,formatMoney,PERIODICITY_LABEL,suggestNextYear} from './platform/format';
import {getPolicy,listOptions,putOption,putPolicy,schoolLogoBlob,setClassStatus,updateClass,uploadSchoolLogo,type SchoolOption} from './api';
import './settings.css';
import {TariffsSettings,TARIFF_GROUPS} from './settings_tariffs';
import {BenefitsSettings} from './settings_benefits';
import {DocumentSettingsPanel, MaintenanceSettings, NumberingCard} from './settings_maintenance';
import {ProductsSettings} from './settings_products';
import {AdmissionConditionsSettings} from './settings_admission';
import {PaymentPolicySettings} from './settings_payment';
import {AnticipationPlansSettings} from './settings_anticipation';

const BLOCKING_LABEL:Record<string,string>={ENROLL_STUDENT:'les inscriptions',GENERATE_FEES:'la génération des frais',CONFIGURE_TARIFF:'la saisie des tarifs',SEND_SMS:'l’envoi de SMS'};
const PLATFORM_TOKEN='edusync.platform.token';
const SCHOOL_SESSION='edusync.school.session';

type SavedSchoolSession={token:string;school:SchoolLoginResult['school'];user:SchoolLoginResult['user'];permissions:string[]};

/** A reloaded or shared link to the schools or accounts screen (?school=<id>, ?user=<id>, filters) opens that screen, not the dashboard. */
const schoolsDeepLink=():'dashboard'|'schools'|'access'|'team'|'notifications'|'audit'|'diagnostics'|'messaging'=>/[?&]msg=/.test(window.location.search)?'messaging':/[?&]service=/.test(window.location.search)?'diagnostics':/[?&](aevent|aq|acat|aact|asch|aactor|ares|afrom|ato|asort)=/.test(window.location.search)?'audit':/[?&]campaign=/.test(window.location.search)?'notifications':/[?&]member=/.test(window.location.search)?'team':ACCESS_URL_KEYS.test(window.location.search)?'access':/[?&](school|q|status|config|sort|page|needs_admin)=/.test(window.location.search)?'schools':'dashboard';
function AtelierPro({token,user,onLogout,onSwitchSpace}:{token:string;user:PlatformUser;onLogout:()=>void;onSwitchSpace?:()=>void}){
  const [tab,setTab]=useState<'dashboard'|'schools'|'access'|'team'|'notifications'|'audit'|'diagnostics'|'messaging'>(schoolsDeepLink);
  // Server-computed identity and menu: a PLATFORM_CUSTOM account only sees (and only loads) what its roles open.
  const [me,setMe]=useState<PlatformMe|null>(()=>knownPlatform()?.me||null);
  const can=(key:string)=>!!me?.menu.some(m=>m.key===key);
  const has=(cap:string)=>!!me?.permissions.includes(cap);
  useEffect(()=>{replaceMobileRoot('platform',schoolsDeepLink());const h=(e:Event)=>{const d=(e as CustomEvent).detail;if(d?.edusyncScope==='platform'&&d.edusyncScreen)setTab(current=>knownPlatform()?.me.menu.some(x=>x.key===d.edusyncScreen)?d.edusyncScreen:current)};window.addEventListener('edusync:android-back',h);return()=>window.removeEventListener('edusync:android-back',h)},[]);
  const goTab=(next:typeof tab)=>{if(tab==='dashboard'&&next!=='dashboard')dashScroll.current=window.scrollY;if(next!==tab){pushMobileScreen('platform',next);/* the new screen starts with a clean URL; the left one keeps its own (back restores it) */if(window.location.search)history.replaceState(history.state,'',window.location.pathname)}setTab(next)};
  const [systemNotifications,setSystemNotifications]=useState<any>({items:[]});
  const [error,setError]=useState('');
  const [dashKey,setDashKey]=useState(0);const dashScroll=useRef(0);
  const [notificationOpen,setNotificationOpen]=useState(false);
  const [schoolsPreset,setSchoolsPreset]=useState<SchoolsPreset|null>(null);const [schoolsVisited,setSchoolsVisited]=useState(false);
  const [creatingSchool,setCreatingSchool]=useState(false);
  const [accessPreset,setAccessPreset]=useState<AccessPreset|null>(null);const [teamPreset,setTeamPreset]=useState<TeamPreset|null>(null);const [accessVisited,setAccessVisited]=useState(false);
  // Step-up (decision 2026-10-13): sensitive actions ask for a fresh code through this dialog, then resume by themselves.
  const [stepUp,setStepUp]=useState<((ok:boolean)=>void)|null>(null);
  useEffect(()=>{setStepUpHandler(()=>new Promise<boolean>(resolve=>setStepUp(()=>resolve)));return()=>setStepUpHandler(null)},[]);
  const schoolSchema=z.object({name:z.string().trim().min(2,'Le nom de l’école est obligatoire.'),code:z.string().trim().min(2,'Le code établissement est obligatoire.').max(24,'Le code est trop long.')});type SchoolCreateForm=z.infer<typeof schoolSchema>;const schoolForm=useForm<SchoolCreateForm>({resolver:zodResolver(schoolSchema),defaultValues:{name:'',code:''},...formDefaults});
  // Lists load when their screen opens (the dashboard has its own single request): no request burst at start-up.
  async function refresh(){setDashKey(k=>k+1)}
  useEffect(()=>{let alive=true;platformMe(token).then(m=>{if(!alive)return;if(getPlatformAuthState()!=='OFFLINE_AUTHENTICATED_CACHED')rememberPlatformContext(m);setMe(m);setTab(t=>m.menu.some(x=>x.key===t)?t:(m.menu[0]?.key||'dashboard') as typeof tab)}).catch(e=>alive&&setError(friendlyError(e)));return()=>{alive=false}},[token]);
  useEffect(()=>{if(!me)return;if(tab==='schools')setSchoolsVisited(true);if(tab==='access')setAccessVisited(true)},[tab,me]);
  // Dashboard -> filtered view -> back: the dashboard stays mounted (data and scroll position kept).
  function openTarget(t:DashboardTarget){
    if(t.tab==='schools')setSchoolsPreset({status:t.status,filter:t.filter,nonce:Date.now()});
    if(t.tab==='access')setAccessPreset({activeOnly:Boolean(t.activeOnly),nonce:Date.now()});
    goTab(t.tab);window.scrollTo(0,0)}
  useLayoutEffect(()=>{if(tab==='dashboard')window.scrollTo(0,dashScroll.current)},[tab]);
  const [theme,setTheme]=usePlatformTheme(user.email);
  // Profile photo: fetched with the access token (private), shown through an object URL, initials as fallback.
  const [avatarUrl,setAvatarUrl]=useState<string|undefined>();
  async function loadAvatar(){try{const b=await platformAvatarBlob(token);setAvatarUrl(prev=>{if(prev)URL.revokeObjectURL(prev);return b?URL.createObjectURL(b):undefined})}catch{setAvatarUrl(undefined)}}
  useEffect(()=>{if(me?.avatar_version)void loadAvatar()},[me?.avatar_version]);
  useEffect(()=>()=>{if(avatarUrl)URL.revokeObjectURL(avatarUrl)},[avatarUrl]);
  const photo={url:avatarUrl,upload:async(f:File)=>{await uploadPlatformAvatar(token,f);await loadAvatar()},remove:async()=>{await deletePlatformAvatar(token);setAvatarUrl(undefined)}};
  const NAV_DEF:[typeof tab,string,string][]=[['dashboard','cockpit','Tableau de bord'],['schools','school','Écoles'],['access','lock','Utilisateurs & accès'],['team','users','Équipe plateforme'],['notifications','bell','Notifications système'],['audit','audit','Journal d’audit'],['diagnostics','pulse','État du service'],['messaging','bell','Messagerie']];
  const roleLabel=me?.roles.map(r=>r.label.replace(/^Manager syst[eè]me$/i,'Manager Système')).join(' · ');
  const nav:any[]=NAV_DEF.filter(([k])=>can(k)).map(([k,icon,label])=>[icon,label,tab===k,()=>goTab(k),k]);
  return <Shell title="Plateforme EduSync" subtitle="Pilotage et administration de la plateforme EduSync" onLogout={onLogout} onSwitchSpace={onSwitchSpace} nav={nav} user={user} token={token} roleLabel={roleLabel} theme={theme} onTheme={setTheme} photo={photo}>
    <OfflineAdminBanner/>
    {error&&<div className="error">{error}</div>}
    {me&&typeof me.active_managers==='number'&&me.active_managers<(me.recommended_managers||2)&&<div className="es-alert es-alert-warn" role="status"><NavGlyph g="alert" size={16}/><span><b>Un seul Manager Système actif.</b> Ajoutez un second Manager depuis « Équipe plateforme » : en cas de téléphone perdu, il pourra rétablir votre accès sans intervention technique.</span></div>}
    {stepUp&&<StepUpDialog token={token} onDone={ok=>{stepUp(ok);setStepUp(null)}}/>}
    {!me&&!error&&<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
    {creatingSchool&&<SchoolFormDialog token={token} has={has} onClose={()=>setCreatingSchool(false)} onCreated={id=>{setCreatingSchool(false);void refresh();setSchoolsPreset({nonce:Date.now(),openId:id});goTab('schools')}}/>}
    {tab==='team'&&can('team')&&<ScreenBoundary resetKey={tab} label={tab}><Suspense fallback={<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}><TeamPage token={token} preset={teamPreset} onChanged={()=>{void platformMe(token).then(setMe).catch(()=>undefined)}}/></Suspense></ScreenBoundary>}
    {me&&can('dashboard')&&<div hidden={tab!=='dashboard'}><ScreenBoundary label='dashboard'><PlatformDashboard key={dashKey} token={token} userName={me?.user.full_name||user.full_name} can={can} has={has} onOpen={openTarget} onCreateSchool={()=>setCreatingSchool(true)}/></ScreenBoundary></div>}
    {can('schools')&&(schoolsVisited||tab==='schools')&&<div hidden={tab!=='schools'}><ScreenBoundary label="schools"><SchoolsModule token={token} has={has} preset={schoolsPreset} active={tab==='schools'} onChanged={()=>setDashKey(k=>k+1)}/></ScreenBoundary></div>}
    {can('access')&&(accessVisited||tab==='access')&&<div hidden={tab!=='access'}><ScreenBoundary label="access"><AccessDirectory token={token} has={has} preset={accessPreset} active={tab==='access'} onOpenSchool={id=>{setSchoolsPreset({nonce:Date.now(),openId:id});goTab('schools')}} onOpenTeam={t=>{setTeamPreset({...t,nonce:Date.now()});goTab('team')}}/></ScreenBoundary></div>}
    {tab==='notifications'&&can('notifications')&&<ScreenBoundary resetKey={tab} label={tab}><Suspense fallback={<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}><CampaignsPanel token={token} canTeam={has('platform.collaborators.manage')}/></Suspense></ScreenBoundary>}
    {tab==='audit'&&can('audit')&&<ScreenBoundary resetKey={tab} label={tab}><Suspense fallback={<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}><AuditPanel token={token} canExport={has('platform.audit.export')} links={{canSchools:can('schools'),canTeam:can('team'),canAccess:can('access'),canNotify:can('notifications'),
      onOpenSchool:id=>{setSchoolsPreset({nonce:Date.now(),openId:id});goTab('schools')},onOpenMember:id=>{setTeamPreset({openMember:id,nonce:Date.now()});goTab('team')},
      onOpenUser:id=>{setAccessPreset({openUser:id,nonce:Date.now()});goTab('access')},onOpenCampaign:id=>{goTab('notifications');history.replaceState(history.state,'',`${window.location.pathname}?campaign=${id}`)}}}/></Suspense></ScreenBoundary>}
    {tab==='messaging'&&can('messaging')&&<ScreenBoundary resetKey={tab} label={tab}><Suspense fallback={<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}><PlatformMessaging token={token} canCredit={has('platform.sms_wallet.credit')} canAdjust={has('platform.sms_wallet.adjust')} canRetry={has('platform.messaging.retry')}/></Suspense></ScreenBoundary>}
    {tab==='diagnostics'&&can('diagnostics')&&<ScreenBoundary resetKey={tab} label={tab}><Suspense fallback={<div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}><HealthPanel token={token} canMessaging={can('messaging')} onOpenMessaging={()=>goTab('messaging')}/></Suspense></ScreenBoundary>}
    {notificationOpen&&<PlatformNotificationDialog token={token} schools={[]} onClose={()=>setNotificationOpen(false)} onDone={async()=>{setNotificationOpen(false);setSystemNotifications(await platformSystemNotifications(token,0));await refresh()}}/>}
  </Shell>
}


function PlatformNotificationDialog({token,schools,onClose,onDone}:{token:string;schools:any[];onClose:()=>void;onDone:()=>Promise<void>}){
 const schema=z.object({title:z.string().trim().min(2,'Titre obligatoire').max(180),body:z.string().trim().min(2,'Message obligatoire').max(2000),severity:z.enum(['INFO','WARNING','CRITICAL']),target_scope:z.enum(['ALL_ACTIVE_SCHOOLS','SCHOOL']),target_school_id:z.string().optional()}).superRefine((v,c)=>{if(v.target_scope==='SCHOOL'&&!v.target_school_id)c.addIssue({code:'custom',path:['target_school_id'],message:'Choisissez une école active.'})});type F=z.infer<typeof schema>;const f=useForm<F>({resolver:zodResolver(schema),defaultValues:{title:'',body:'',severity:'INFO',target_scope:'ALL_ACTIVE_SCHOOLS',target_school_id:''},...formDefaults});const [error,setError]=useState('');const scope=f.watch('target_scope');const submit=f.handleSubmit(async v=>{try{setError('');const r=await sendPlatformSystemNotification(token,{title:v.title.trim(),body:v.body.trim(),severity:v.severity,target_scope:v.target_scope,target_school_id:v.target_scope==='SCHOOL'?v.target_school_id:null});toast.success(`Notification distribuée à ${r.recipient_count} destinataire(s)`);await onDone()}catch(e){setError(friendlyError(e))}});return <div className="wizardBackdrop"><form className="accountSecurityDialog platformNotificationDialog" onSubmit={submit} noValidate><div className="modalHead"><div><h3>Notification système</h3><p>Diffusion interne auditable. Aucun SMS ou WhatsApp n’est envoyé par cette action.</p></div><button type="button" onClick={onClose}>×</button></div><FormField label="Titre *" error={f.formState.errors.title?.message}><input {...f.register('title')}/></FormField><FormField label="Niveau *" error={f.formState.errors.severity?.message}><select {...f.register('severity')}><option value="INFO">Information</option><option value="WARNING">Avertissement</option><option value="CRITICAL">Critique</option></select></FormField><FormField label="Cible *" error={f.formState.errors.target_scope?.message}><select {...f.register('target_scope')}><option value="ALL_ACTIVE_SCHOOLS">Toutes les écoles actives</option><option value="SCHOOL">Une école</option></select></FormField>{scope==='SCHOOL'&&<FormField label="École active *" error={f.formState.errors.target_school_id?.message}><select {...f.register('target_school_id')}><option value="">Choisir…</option>{schools.filter(x=>x.status==='ACTIVE').map(x=><option key={x.id} value={x.id}>{x.name} · {x.code}</option>)}</select></FormField>}<FormField label="Message *" error={f.formState.errors.body?.message}><textarea rows={6} {...f.register('body')}/></FormField>{error&&<div className="loginFriendlyError" role="alert">{error}</div>}<div className="modalActions"><button type="button" className="ghost" onClick={onClose}>Annuler</button><button disabled={f.formState.isSubmitting}>{f.formState.isSubmitting?'Diffusion…':'Envoyer la notification'}</button></div></form></div>}


const parameterTabs=[
 ['checkCircle','Mise en service','overview'],['school','École & identité','identity'],['calendar','Années scolaires','years'],['layers','Structure & classes','structure'],['users','Inscriptions','enrollment'],['star','Avantages','benefits'],['receipt','Encaissement','payment'],['calendar','Plans anticipés','anticipation'],['receipt','Types de frais','fees'],['tag','Tarifs & barèmes','tariffs'],['box','Contributions en nature','contributions'],['cart','Articles scolaires','products'],['doc','Documents & signature','signature'],['database','Sauvegardes & diagnostic','maintenance'],
] as const;

type TabKey=typeof parameterTabs[number][2];
const parameterHints:Record<TabKey,string>={overview:'Ce qui est prêt et ce qui reste à faire',identity:'Nom, coordonnées et logo',years:'Préparer, activer, clôturer une année',structure:'Sections et classes ouvertes',enrollment:'Conditions et règles de saisie',benefits:'Famille nombreuse, enfants du personnel',payment:'Acomptes, mois futurs, modes de paiement',anticipation:'Mois payés à l’avance selon un plan',fees:'Catalogue des frais',tariffs:'Montants par année et par classe',contributions:'Biens attendus des familles',products:'Articles vendus par l’école',signature:'Signataire et logo des documents',maintenance:'Copie des données, test, diagnostic'};
const phoneLayout=()=>typeof window!=='undefined'&&window.matchMedia('(max-width:720px)').matches;

function SettingsPage({session,onHome,links=[],onNavigate}:{session:SavedSchoolSession;onHome:()=>void;links?:{key:string;label:string;icon:string}[];onNavigate:(module:string)=>void}){
  const token=session.token;const [tab,setTab]=useState<TabKey>('overview');const [overview,setOverview]=useState<SettingsOverview|null>(null);const [years,setYears]=useState<AcademicYear[]>([]);const [sections,setSections]=useState<SchoolSection[]>([]);const [classes,setClasses]=useState<SchoolClass[]>([]);const [fees,setFees]=useState<FeeType[]>([]);const [tariffs,setTariffs]=useState<Tariff[]>([]);const [contributions,setContributions]=useState<SettingsContribution[]>([]);const [products,setProducts]=useState<SettingsProduct[]>([]);const [refs,setRefs]=useState<ReferenceCatalog|null>(null);const [error,setError]=useState('');
  const can=(p:string)=>session.permissions.includes(p);
  // Phone: the section list is the home of the settings, a section opens as its own screen (Android back returns to the list).
  const [detail,setDetail]=useState(false);
  const open=(key:TabKey)=>{setTab(key);if(phoneLayout()){history.pushState({...(history.state||{}),edusyncSettingsDetail:key},'');setDetail(true);window.scrollTo(0,0)}};
  // A closed dialog may leave its own history entry above the section: unwind until the list entry.
  const back=()=>{if(!history.state?.edusyncSettingsDetail){setDetail(false);return}const unwind=()=>{if(history.state?.edusyncSettingsDetail)history.back();else window.removeEventListener('popstate',unwind)};window.addEventListener('popstate',unwind);history.back()};
  useEffect(()=>{const h=(e:Event)=>{if(!(e as CustomEvent).detail?.edusyncSettingsDetail)setDetail(false)};const r=()=>{if(!phoneLayout())setDetail(false)};window.addEventListener('edusync:android-back',h);window.addEventListener('resize',r);return()=>{window.removeEventListener('edusync:android-back',h);window.removeEventListener('resize',r)}},[]);
  // After a save, only the list that changed and the readiness are reloaded (premium pass 2026-10-24): a full reload of
  // the nine settings lists made every save wait several seconds. A call without parts reloads everything.
  type Part='overview'|'years'|'sections'|'classes'|'fees'|'tariffs'|'contributions'|'products'|'refs';
  async function refresh(parts?:Part[]){try{setError('');const want=(k:Part)=>!parts||k==='overview'||parts.includes(k);
    const load=<T,>(k:Part,allowed:boolean,fn:()=>Promise<T>,set:(v:T)=>void)=>want(k)&&allowed?fn().then(set):Promise.resolve();
    await Promise.all([load('overview',can('settings.school_identity.read'),()=>getSettingsOverview(token),setOverview),load('years',can('settings.academic_year.read'),()=>listAcademicYears(token),setYears),
      load('sections',can('settings.structure.read'),()=>listSections(token),setSections),load('classes',can('settings.structure.read'),()=>listClasses(token),setClasses),
      load('fees',can('settings.fee_types.read'),()=>listFeeTypes(token),setFees),load('tariffs',can('settings.tariffs.read'),()=>listTariffs(token),setTariffs),
      load('contributions',can('settings.contributions.read'),()=>listSettingsContributions(token),setContributions),load('products',can('settings.products.read'),()=>listSettingsProducts(token),setProducts),
      load('refs',can('settings.structure.read'),()=>getReferenceCatalog(token),setRefs)])}catch(e){setError(friendlyError(e))}}
  useEffect(()=>{void refresh()},[token]);
  const allowed=(key:TabKey)=>key==='overview'||key==='identity'?can('settings.school_identity.read'):key==='years'?can('settings.academic_year.read'):key==='structure'?can('settings.structure.read'):key==='enrollment'?can('settings.enrollment_policy.read'):key==='benefits'?can('settings.benefits.read'):key==='payment'?can('settings.payment_policy.read'):key==='anticipation'?can('finance.anticipation_plans.read'):key==='fees'?can('settings.fee_types.read'):key==='tariffs'?can('settings.tariffs.read'):key==='contributions'?can('settings.contributions.read'):key==='products'?can('settings.products.read'):key==='signature'?can('settings.documents.read'):key==='maintenance'?can('settings.backups.read')||can('settings.diagnostics.read'):false;
  const label=(key:TabKey)=>parameterTabs.find(([, ,k])=>k===key)?.[1]??'Paramètres';
  const status=(key:TabKey)=>sectionStatus(key,{overview,years,classes,fees,tariffs,contributions,products});
  // A readiness step on the home opens its section directly (one-shot hand-over through sessionStorage).
  useEffect(()=>{let target='';try{target=sessionStorage.getItem(SETTINGS_TARGET_KEY)||'';sessionStorage.removeItem(SETTINGS_TARGET_KEY)}catch{/* facultatif */}
    if(target&&target!=='overview'&&parameterTabs.some(([, ,k])=>k===target)&&allowed(target as TabKey))open(target as TabKey)},[]);
  // Phone: the overview (journey + section cards) is the home of the settings; a section opens as its own screen.
  const shown:TabKey=!detail&&phoneLayout()?'overview':tab;
  const toOverview=()=>{if(detail)back();else setTab('overview')};
  const remaining=overview?overview.readiness.items.filter(i=>i.state==='TO_COMPLETE'||i.state==='TO_CONFIRM').length:0;
  const [assistant,setAssistant]=useState(false);
  return <div className="ui-page sp-page">
    <PageTrail parents={shown==='overview'?[{label:'Accueil',onSelect:onHome}]:[{label:'Accueil',onSelect:onHome},{label:'Paramètres',onSelect:toOverview}]} current={shown==='overview'?'Paramètres':label(shown)}/>
    <div className={`settingsHeader ${detail?'phoneDetailHead':''}`}><PageHeader eyebrow="Centre de configuration" title={shown==='overview'?'Paramètres de l’établissement':label(shown)}
      subtitle={shown==='overview'?'Ce qui est prêt, ce qui manque et où agir. Le paramétrage est progressif : rien ne bloque EduSync globalement.':parameterHints[shown]}
      aside={overview&&<div className="sp-progress" aria-label={`Paramétrage ${overview.readiness.percent} %`}><b>{overview.readiness.percent}%</b><span>{remaining?`${remaining} étape${remaining>1?'s':''} restante${remaining>1?'s':''}`:'Paramétrage complet'}</span></div>}/></div>
    {error&&<div className="error">{error}</div>}
    <div className={`settingsLayout ${detail?'phoneDetail':'phoneHome'}`}><nav className="settingsNav sp-nav" aria-label="Sections des paramètres">{SETTINGS_GROUPS.map(g=>{const items=g.keys.filter(allowed);return items.length?<div key={g.title} className="sp-nav-group"><p>{g.title}</p>
      {items.map(key=>{const st=status(key);const icon=parameterTabs.find(([, ,k])=>k===key)![0];return <button key={key} className={tab===key?'active':''} aria-current={tab===key?'page':undefined} onClick={()=>open(key)}><span aria-hidden="true"><NavGlyph g={icon} size={17}/></span><span className="settingsNavText"><b>{label(key)}</b><small>{parameterHints[key]}</small></span><i className={`sp-dot sp-dot-${st.tone}`} title={st.label} aria-label={st.label}/></button>})}</div>:null})}</nav><div className="settingsContent">
    {shown==='overview'&&<SettingsHome overview={overview} allowed={allowed} status={status} open={k=>open(k)} links={links} onNavigate={onNavigate} onAssistant={refs&&can('settings.school_identity.read')?()=>setAssistant(true):undefined}/>}{assistant&&refs&&<SetupAssistant token={token} overview={overview} refs={refs} can={can} onClose={()=>setAssistant(false)} onDone={refresh}/>} {shown==='identity'&&<><IdentitySettings token={token} overview={overview} can={can} onDone={()=>refresh([])}/><NumberingCard token={token}/></>} {shown==='years'&&<Years token={token} years={years} can={can} onDone={()=>refresh(['years','classes'])}/>} {shown==='structure'&&<Structure token={token} sections={sections} classes={classes} years={years} refs={refs} can={can} onDone={refresh}/>} {shown==='enrollment'&&<><EnrollmentPolicySettings token={token} can={can}/><AdmissionConditionsSettings token={token} years={years} fees={fees} sections={sections} classes={classes} refs={refs} can={can}/></>} {shown==='benefits'&&<BenefitsSettings token={token} years={years} fees={fees} can={can} onOpenFinance={can('finance.decisions.read')?()=>onNavigate('finance'):undefined}/>} {shown==='payment'&&<PaymentPolicySettings token={token} can={can}/>} {shown==='anticipation'&&<AnticipationPlansSettings token={token} years={years} fees={fees} classes={classes} sections={sections} refs={refs} can={can}/>} {shown==='fees'&&<Fees token={token} fees={fees} refs={refs} can={can} onDone={()=>refresh(['fees'])}/>} {shown==='tariffs'&&<TariffsSettings token={token} tariffs={tariffs} years={years} fees={fees} classes={classes} sections={sections} refs={refs} can={can} onDone={refresh}/>} {shown==='contributions'&&<ContributionsSettings token={token} items={contributions} can={can} onDone={()=>refresh(['contributions'])}/>} {shown==='products'&&<ProductsSettings token={token} items={products} can={can} onDone={()=>refresh(['products'])}/>} {shown==='signature'&&<DocumentSettingsPanel token={token} can={can}/>} {shown==='maintenance'&&<MaintenanceSettings token={token} can={can}/>}
  </div></div></div>
}

// Settings home (premium pass 2026-10-24): one progress journey + every section as a card with its status.
const SETTINGS_GROUPS:{title:string;keys:TabKey[]}[]=[
  {title:'Établissement',keys:['overview','identity','years','structure']},
  {title:'Inscriptions',keys:['enrollment','benefits']},
  {title:'Frais & tarification',keys:['fees','tariffs','payment','anticipation']},
  {title:'Catalogue',keys:['contributions','products']},
  {title:'Documents & sécurité',keys:['signature','maintenance']},
];
const READINESS_OF:Partial<Record<TabKey,string>>={identity:'IDENTITY',years:'ACADEMIC_YEAR',structure:'STRUCTURE',fees:'FEE_TYPES',tariffs:'TARIFFS',payment:'PAYMENT_POLICY',enrollment:'ENROLLMENT_POLICY'};
type SectionData={overview:SettingsOverview|null;years:AcademicYear[];classes:SchoolClass[];fees:FeeType[];tariffs:Tariff[];contributions:SettingsContribution[];products:SettingsProduct[]};
function sectionStatus(key:TabKey,d:SectionData):{tone:Tone;label:string}{
  const item=READINESS_OF[key]&&d.overview?.readiness.items.find(i=>i.code===READINESS_OF[key]);
  if(item)return item.state==='READY'?{tone:'ok',label:'Configuré'}:item.state==='TO_COMPLETE'?{tone:'todo',label:'À compléter'}:item.state==='TO_CONFIRM'?{tone:'warn',label:'À vérifier'}:{tone:'neutral',label:'Non concerné'};
  if(key==='overview')return d.overview&&d.overview.readiness.percent>=100?{tone:'ok',label:'Complet'}:{tone:'brand',label:'En cours'};
  if(key==='years')return d.years.some(y=>y.status==='ACTIVE')?{tone:'ok',label:'Configuré'}:{tone:'todo',label:'À compléter'};
  if(key==='structure')return d.classes.length?{tone:'ok',label:'Configuré'}:{tone:'todo',label:'À compléter'};
  if(key==='fees')return d.fees.length?{tone:'ok',label:'Configuré'}:{tone:'todo',label:'À compléter'};
  if(key==='tariffs')return d.tariffs.length?{tone:'ok',label:'Configuré'}:{tone:'todo',label:'À compléter'};
  if(key==='contributions')return d.contributions.length?{tone:'ok',label:'Configuré'}:{tone:'neutral',label:'Facultatif'};
  if(key==='products')return d.products.length?{tone:'ok',label:'Configuré'}:{tone:'neutral',label:'Facultatif'};
  return {tone:'neutral',label:'Facultatif'};
}
const LINK_HINT:Record<string,string>={access:'Comptes, rôles, approbations',sync:'Appareils et synchronisation',documents:'Modèles, reçus, historique'};
function SettingsHome({overview,allowed,status,open,links,onNavigate,onAssistant}:{overview:SettingsOverview|null;allowed:(k:TabKey)=>boolean;status:(k:TabKey)=>{tone:Tone;label:string};open:(k:TabKey)=>void;links:{key:string;label:string;icon:string}[];onNavigate:(m:string)=>void;onAssistant?:()=>void}){
  const tabs=new Set(parameterTabs.map(([, ,k])=>k as string));
  let index=0;
  const others=links.filter(l=>LINK_HINT[l.key]);
  return <div className="sp-home">
    {onAssistant&&<div className="sw-cta sw-cta-hero"><div><b>Assistant de mise en service</b><small>École et année, sections, options des Humanités, classes et parallèles en quelques minutes : EduSync génère les codes pour vous.</small></div><UIButton variant="primary" icon="star" onClick={onAssistant}>Lancer l’assistant</UIButton></div>}
    {allowed('overview')&&<Card level="priority" wide title="Mise en service" icon="checkCircle" className="sh-readiness">{overview?<ProgressJourney showDone percent={overview.readiness.percent}
      title={overview.readiness.percent>=100?'Paramétrage complet':'Votre parcours de paramétrage'} steps={readinessSteps(overview,section=>{if(tabs.has(section))open(section as TabKey)})}/>:<Skeleton lines={4}/>}</Card>}
    {SETTINGS_GROUPS.map(g=>{const items=g.keys.filter(k=>k!=='overview'&&allowed(k));return items.length?<Section key={g.title} title={g.title} id={`sp-${g.title}`}><div className="ui-grid">{items.map(k=>{const st=status(k);
      return <Card key={k} level={st.tone==='todo'?'priority':st.tone==='neutral'?'secondary':'info'} tone={st.tone==='todo'?'todo':st.tone==='warn'?'warn':st.tone==='ok'?'ok':undefined}
        icon={parameterTabs.find(([, ,x])=>x===k)![0]} title={parameterTabs.find(([, ,x])=>x===k)![1]} badge={<StatusBadge tone={st.tone}>{st.label}</StatusBadge>} hint={parameterHints[k]} index={index++} onClick={()=>open(k)} ariaLabel={`${parameterTabs.find(([, ,x])=>x===k)![1]} — ${st.label}`}/>})}</div></Section>:null})}
    {others.length>0&&<Section title="Ailleurs dans EduSync" subtitle="Réglages gérés dans leur propre module" id="sp-elsewhere"><div className="ui-grid">{others.map(l=><Card key={l.key} level="secondary" icon={l.icon} title={l.label} hint={LINK_HINT[l.key]} index={index++} onClick={()=>onNavigate(l.key)}/>)}</div></Section>}
  </div>;
}

// Guided start: each item that is not ready opens the section that settles it; the first one is proposed as the next step.
const READINESS_TARGET:Record<string,TabKey>={IDENTITY:'identity',ACADEMIC_YEAR:'years',STRUCTURE:'structure',FEE_TYPES:'fees',TARIFFS:'tariffs'};
function Readiness({overview,onOpen}:{overview:SettingsOverview|null;onOpen:(k:TabKey)=>void}){if(!overview)return <Loading/>;const next=overview.readiness.items.find(i=>i.state!=='READY'&&i.state!=='NOT_APPLICABLE'&&READINESS_TARGET[i.code]);return <Panel title="École immédiatement exploitable" subtitle="Le pourcentage est informatif. Seule l’action qui manque d’un prérequis est bloquée.">{next?<div className="nextStep"><span>Prochaine étape</span><b>{next.label}</b><p>{next.detail}</p><button type="button" className="primaryBtn" onClick={()=>onOpen(READINESS_TARGET[next.code])}>Continuer</button></div>:<div className="nextStep done"><span>Mise en service</span><b>L’essentiel est prêt.</b><p>Vous pouvez compléter les autres paramètres à tout moment.</p></div>}<div className="readinessGrid">{overview.readiness.items.map(i=><div className="readinessItem" key={i.code}><em className={`status ${i.state.toLowerCase()}`}>{i.state==='READY'?'Prêt':i.state==='NOT_APPLICABLE'?'Non applicable':i.state==='TO_CONFIRM'?'À confirmer':'À compléter'}</em><b>{i.label}</b><p>{i.detail}</p>{i.blocking_only_for.length>0&&<small>Nécessaire pour : {i.blocking_only_for.map((c:string)=>BLOCKING_LABEL[c]??c.toLowerCase()).join(' · ')}</small>}{i.state!=='READY'&&READINESS_TARGET[i.code]&&<button type="button" className="linkBtn" onClick={()=>onOpen(READINESS_TARGET[i.code])}>Ouvrir <span aria-hidden="true">›</span></button>}</div>)}</div></Panel>}

// Enrollment period of a year (2026-10-24): informative and editable at any time while the year is prepared or active;
// an enrollment after the period (late enrollment, transfer) stays possible and is flagged to the secretary.
function EnrollmentWindow({token,year,editable,onDone}:{token:string;year:AcademicYear;editable:boolean;onDone:()=>Promise<void>}){
  const [edit,setEdit]=useState(false);const [start,setStart]=useState(year.enrollment_start??'');const [end,setEnd]=useState(year.enrollment_end??'');const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  useEffect(()=>{setStart(year.enrollment_start??'');setEnd(year.enrollment_end??'')},[year.enrollment_start,year.enrollment_end]);
  const today=new Date().toISOString().slice(0,10);const open=!!year.enrollment_start&&!!year.enrollment_end&&today>=year.enrollment_start&&today<=year.enrollment_end;
  async function save(){if(start&&end&&end<start){setError('La fin des inscriptions doit suivre leur début.');return}
    try{setBusy(true);setError('');await putEnrollmentWindow(token,year.id,{enrollment_start:start||null,enrollment_end:end||null});toast.success(`Période d’inscription de ${year.label} enregistrée`);setEdit(false);await onDone()}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
  if(edit)return <span className="enrollWindowEdit"><label>Inscriptions du<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>au<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label>
    <button type="button" className="primaryBtn" disabled={busy} onClick={()=>void save()}>{busy?'…':'Enregistrer'}</button><button type="button" className="ghost" onClick={()=>setEdit(false)}>Annuler</button>{error&&<small className="error" role="alert">{error}</small>}</span>;
  return <small className="enrollWindow">{year.enrollment_start||year.enrollment_end?<>Inscriptions : {year.enrollment_start?formatDate(year.enrollment_start):'…'} → {year.enrollment_end?formatDate(year.enrollment_end):'…'}{year.status==='ACTIVE'&&<em className={`pill ${open?'ready':''}`}>{open?'ouvertes':'hors période'}</em>}</>:'Période d’inscription non définie'}
    {editable&&<button type="button" className="linkBtn" onClick={()=>setEdit(true)}>{year.enrollment_start||year.enrollment_end?'Modifier':'Définir'}</button>}</small>;
}

function Years({token,years,can,onDone}:{token:string;years:AcademicYear[];can:(x:string)=>boolean;onDone:()=>Promise<void>}){
  const [error,setError]=useState('');const [creating,setCreating]=useState(false);const [busy,setBusy]=useState('');const next=useMemo(()=>suggestNextYear(years.map(y=>y.code)),[years]);
  const yearCode=(label:string)=>yearCodeOf(label,years.map(y=>y.code));
  const yearSchema=z.object({label:z.string().trim().min(4,'Indiquez le libellé affiché, par exemple 2027-2028.'),start_date:z.string().min(1,'Choisissez la date de rentrée.'),end_date:z.string().min(1,'Choisissez la date de fin d’année.'),enrollment_start:z.string(),enrollment_end:z.string()}).refine(v=>v.end_date>v.start_date,{message:'La fin d’année doit venir après la rentrée.',path:['end_date']}).refine(v=>!v.enrollment_start||!v.enrollment_end||v.enrollment_end>=v.enrollment_start,{message:'La fin des inscriptions doit suivre leur début.',path:['enrollment_end']}).refine(v=>!years.some(y=>y.code.toLowerCase()===yearCode(v.label).toLowerCase()),{message:'Cette année existe déjà.',path:['label']});type YearForm=z.infer<typeof yearSchema>;const yearForm=useForm<YearForm>({resolver:zodResolver(yearSchema),values:{...next,enrollment_start:'',enrollment_end:''},...formDefaults});
  const create=yearForm.handleSubmit(async form=>{try{setError('');await createAcademicYear(token,{...form,code:yearCode(form.label),enrollment_start:form.enrollment_start||null,enrollment_end:form.enrollment_end||null});toast.success(`Année ${form.label} préparée`);setCreating(false);await onDone()}catch(e){setError(friendlyError(e))}});
  const active=years.find(y=>y.status==='ACTIVE');
  const confirmText:Record<'activate'|'close'|'archive'|'reopen',(y:AcademicYear)=>{title:string;message:string;confirmLabel:string;danger?:boolean}>={
    activate:y=>({title:`Activer ${y.label} ?`,message:'Elle devient l’année en cours de l’école : les écrans et les nouvelles opérations s’y rattachent.',confirmLabel:'Activer l’année'}),
    close:y=>({title:`Clôturer ${y.label} ?`,message:'Elle ne sera plus l’année en cours. Son historique reste consultable et elle pourra être rouverte si nécessaire.',confirmLabel:'Clôturer l’année',danger:true}),
    archive:y=>({title:`Archiver ${y.label} ?`,message:'L’année passe aux archives. Rien n’est supprimé : elle reste consultable et peut être rouverte.',confirmLabel:'Archiver'}),
    reopen:y=>({title:`Rouvrir ${y.label} ?`,message:'Elle repasse en préparation. Il faudra l’activer de nouveau pour qu’elle redevienne l’année en cours.',confirmLabel:'Rouvrir'}),
  };
  async function act(y:AcademicYear,action:'activate'|'close'|'archive'|'reopen'){if(!await confirmAction(confirmText[action](y)))return;try{setBusy(y.id);setError('');if(action==='activate')await activateAcademicYear(token,y);else await transitionAcademicYear(token,y,action);toast.success(action==='activate'?`${y.label} est l’année en cours`:action==='close'?`${y.label} clôturée`:action==='archive'?`${y.label} archivée`:`${y.label} rouverte`);await onDone()}catch(e){setError(friendlyError(e))}finally{setBusy('')}}
  return <Panel title="Années scolaires" subtitle="Une année est préparée, mise en cours, clôturée puis archivée. Une année rouverte repasse en préparation.">{error&&<div className="error" role="alert">{error}</div>}
    {years.length===0&&<div className="emptyGuide"><b>Aucune année scolaire</b><p>Préparez la première année, puis activez-la : les classes, les tarifs et les inscriptions s’y rattachent.</p></div>}
    {can('settings.academic_year.create')&&(creating?<form className="gridForm validatedGridForm yearCreate" onSubmit={create} noValidate><FormField label="Libellé *" error={yearForm.formState.errors.label?.message}><input autoComplete="off" {...yearForm.register('label')}/></FormField><FormField label="Rentrée *" error={yearForm.formState.errors.start_date?.message}><input type="date" {...yearForm.register('start_date')}/></FormField><FormField label="Fin d’année *" error={yearForm.formState.errors.end_date?.message}><input type="date" {...yearForm.register('end_date')}/></FormField><FormField label="Début des inscriptions" hint="Facultatif, modifiable à tout moment."><input type="date" {...yearForm.register('enrollment_start')}/></FormField><FormField label="Fin des inscriptions" error={yearForm.formState.errors.enrollment_end?.message} hint="Après cette date, l’inscription reste possible (inscription tardive, transfert) : elle est simplement signalée."><input type="date" {...yearForm.register('enrollment_end')}/></FormField><div className="formActions"><button type="button" className="ghost" onClick={()=>setCreating(false)}>Annuler</button><button className="primaryBtn" disabled={yearForm.formState.isSubmitting}>Préparer l’année</button></div></form>:<button type="button" className="softBtn addLine" onClick={()=>setCreating(true)}>+ Préparer une nouvelle année <small>proposition : {next.label}</small></button>)}
    <div className="cardsList yearList">{years.map(y=><article key={y.id} className={y.status==='ACTIVE'?'current':''}><div><b>{y.label}</b><small>{formatDate(y.start_date)} → {formatDate(y.end_date)}</small><EnrollmentWindow token={token} year={y} editable={can('settings.academic_year.update')&&(y.status==='PREPARED'||y.status==='ACTIVE')} onDone={onDone}/></div><em className={`pill ${y.status==='ACTIVE'?'ready':''}`}>{yearStatusLabel(y.status)}</em><div className="rowActions">{y.status==='PREPARED'&&can('settings.academic_year.activate')&&(active?<small className="hint">Clôturez d’abord {active.label} pour l’activer.</small>:<button disabled={busy===y.id} onClick={()=>void act(y,'activate')}>Activer</button>)}{y.status==='ACTIVE'&&can('settings.academic_year.close')&&<button className="dangerSoft" disabled={busy===y.id} onClick={()=>void act(y,'close')}>Clôturer</button>}{y.status==='CLOSED'&&can('settings.academic_year.archive')&&<button disabled={busy===y.id} onClick={()=>void act(y,'archive')}>Archiver</button>}{(y.status==='CLOSED'||y.status==='ARCHIVED')&&can('settings.academic_year.reopen')&&<button className="ghost" disabled={busy===y.id} onClick={()=>void act(y,'reopen')}>Rouvrir</button>}</div></article>)}</div></Panel>
}

function Structure({token,sections,classes,years,refs,can,onDone}:{token:string;sections:SchoolSection[];classes:SchoolClass[];years:AcademicYear[];refs:ReferenceCatalog|null;can:(x:string)=>boolean;onDone:()=>Promise<void>}){
  const [error,setError]=useState('');const [sectionId,setSectionId]=useState('');const [referenceCode,setReferenceCode]=useState('');const [optionId,setOptionId]=useState('');const [options,setOptions]=useState<SchoolOption[]>([]);const [optionDraft,setOptionDraft]=useState<{section_id:string;label:string}|null>(null);const [batch,setBatch]=useState(false);
  async function loadOptions(){try{setOptions(await listOptions(token))}catch{setOptions([])}}
  useEffect(()=>{void loadOptions()},[token]);
  const optionCode=(label:string)=>label.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,48);
  async function saveOption(o:{section_id:string;code:string;label:string;enabled:boolean;expected_version?:number|null;tariff_group_code?:string|null},done:string){try{setError('');await putOption(token,o);toast.success(done);setOptionDraft(null);await loadOptions()}catch(e){setError(friendlyError(e))}}
  async function setOptionGroup(o:SchoolOption,group:string){if(!group)return;await saveOption({section_id:o.section_id,code:o.code,label:o.label,enabled:o.enabled,expected_version:o.version,tariff_group_code:group},`${o.label} : ${TARIFF_GROUPS.find(g=>g[0]===group)?.[1]}`)}
  async function toggleOption(o:SchoolOption){if(o.enabled&&!await confirmAction({title:`Désactiver l’option ${o.label} ?`,message:'Rien n’est supprimé : les classes déjà rattachées la conservent. Elle n’est plus proposée pour ouvrir de nouvelles classes.',confirmLabel:'Désactiver',danger:true}))return;await saveOption({section_id:o.section_id,code:o.code,label:o.label,enabled:!o.enabled,expected_version:o.version},o.enabled?`Option ${o.label} désactivée`:`Option ${o.label} réactivée`)}
  const active=years.find(y=>y.status==='ACTIVE')??years.find(y=>y.status==='PREPARED');
  async function addSection(code:string,label:string){try{await putSection(token,{code,label,enabled:true});await onDone()}catch(e){setError(friendlyError(e))}}
  async function rename(c:SchoolClass){const label=await promptText({title:`Renommer ${c.label}`,message:'Le libellé affiché change partout ; les élèves, l’historique et le statut de la classe ne changent pas.',label:'Nouveau libellé',confirmLabel:'Renommer',minLength:2});if(!label||label===c.label)return;try{setError('');await updateClass(token,c,{code:c.code,label});toast.success(`Classe renommée : ${label}`);await onDone()}catch(e){setError(friendlyError(e))}}
  // Desktop set_class_status: pause keeps the students (counted, visible, attached); archive only once the class is empty.
  async function changeStatus(c:SchoolClass,status:'ACTIVE'|'INACTIVE'|'ARCHIVED'){const n=c.student_count??0;const ask=status==='INACTIVE'?{title:`Mettre ${c.label} en pause ?`,message:`${n>0?`Ses ${n} élève(s) restent inscrits, comptés dans les effectifs et visibles. `:''}La classe n’est plus proposée pour de nouvelles inscriptions ni comme destination d’un changement de classe. Elle pourra être réactivée.`,confirmLabel:'Mettre en pause',danger:true}:status==='ARCHIVED'?{title:`Archiver ${c.label} ?`,message:'La classe est vide. Archivée, elle reste dans l’historique mais ne pourra plus être modifiée ni réactivée.',confirmLabel:'Archiver',danger:true}:{title:`Réactiver ${c.label} ?`,message:'La classe est de nouveau proposée pour les inscriptions et les changements de classe.',confirmLabel:'Réactiver'};if(!await confirmAction(ask))return;try{setError('');await setClassStatus(token,c,status);toast.success(status==='INACTIVE'?`${c.label} en pause`:status==='ARCHIVED'?`${c.label} archivée`:`${c.label} réactivée`);await onDone()}catch(e){setError(friendlyError(e))}}
  async function addClass(){try{const section=sections.find(x=>x.id===sectionId);const ref=refs?.classes.find(x=>x.code===referenceCode);if(!active||!section||!ref)throw new Error('Choisissez une année, une section et une classe de référence');if(ref.section_code!==section.code)throw new Error('La classe de référence ne correspond pas à la section choisie');await createClass(token,{academic_year_id:active.id,section_id:section.id,reference_code:ref.code,code:ref.code,label:ref.label,option_id:optionId||null});setReferenceCode('');setOptionId('');await onDone()}catch(e){setError(friendlyError(e))}}
  const existing=new Set(sections.map(s=>s.code));const classCodes=new Set(classes.filter(c=>c.academic_year_id===active?.id).map(c=>c.code));
  return <Panel title="Structure & classes" subtitle="Le référentiel RDC propose la structure, mais l’école confirme seulement ce qu’elle organise réellement.">{error&&<div className="error">{error}</div>}<div className="suggestions">{refs?.sections.map(r=><button disabled={existing.has(r.code)||!can('settings.sections.manage')} key={r.code} onClick={()=>void addSection(r.code,r.label)}>{existing.has(r.code)?'✓ ': '+ '}{r.label}</button>)}</div>{sections.length===0&&<div className="emptyGuide"><b>Aucune section</b><p>Touchez les sections que l’école organise réellement ci-dessus. Vous ouvrirez ensuite les classes de chaque section.</p></div>}<div className="cardsList sectionList">{sections.map(s=>{const opts=options.filter(o=>o.section_id===s.id);return <article key={s.id}><div><b>{s.label}</b><small>{classes.filter(c=>c.section_id===s.id&&c.academic_year_id===active?.id&&c.enabled).length} classe(s) ouverte(s){active?` en ${active.label}`:''}</small>{s.code===OPTIONS_SECTION&&s.enabled&&<OptionCatalog token={token} section={s} options={options} canManage={can('settings.options.manage')} onChanged={loadOptions}/>}{s.code!==OPTIONS_SECTION&&<small className="sw-hint">Pas d’options en {s.label} : elles n’existent qu’en Humanités.</small>}</div><em className={`pill ${s.enabled?'ready':''}`}>{s.enabled?'Active':'Inactive'}</em></article>})}</div>
    {!active&&<div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Préparez une année scolaire avant d’ouvrir des classes : chaque classe appartient à une année.</p></div>}
    {can('settings.classes.create')&&active&&sections.length>0&&refs&&<div className="sw-cta"><div><b>Ouvrir des classes pour {active.label}</b><small>Plusieurs classes d’un coup, classes parallèles (A, B, C…) et une classe par option en Humanités : noms et codes générés automatiquement.</small></div><UIButton variant="primary" icon="plus" onClick={()=>setBatch(true)}>Ouvrir des classes</UIButton></div>}
    {batch&&active&&refs&&<ClassBatchDialog token={token} year={active} sections={sections} refs={refs} options={options} classes={classes} onClose={()=>setBatch(false)} onDone={onDone}/>}
    {classes.length>0&&<div className="classGroups">{sections.map(s=>{const list=classes.filter(c=>c.section_id===s.id);if(!list.length)return null;return <section key={s.id} aria-label={s.label}><h4>{s.label}</h4><ul className="classList">{list.map(c=>{const st=c.status??(c.enabled?'ACTIVE':'INACTIVE');const n=c.student_count??0;const locked=c.academic_year_status==='CLOSED'||c.academic_year_status==='ARCHIVED';return <li key={c.id} className={st==='ACTIVE'?'':'off'}><div><b>{c.label}</b><small>{c.academic_year_code??''} · {n} élève(s){st==='INACTIVE'?' · en pause':st==='ARCHIVED'?' · archivée':''}</small></div>{!locked&&st!=='ARCHIVED'&&(can('settings.classes.activate')||can('settings.classes.rename'))&&<div className="classActions">{can('settings.classes.rename')&&<button type="button" className="ghost" onClick={()=>void rename(c)}>Renommer</button>}{can('settings.classes.activate')&&<>{st==='ACTIVE'?<button type="button" className="ghost" onClick={()=>void changeStatus(c,'INACTIVE')}>Mettre en pause</button>:<button type="button" className="softBtn" onClick={()=>void changeStatus(c,'ACTIVE')}>Réactiver</button>}{n===0&&<button type="button" className="ghost dangerText" onClick={()=>void changeStatus(c,'ARCHIVED')}>Archiver</button>}</>}</div>}</li>})}</ul></section>})}</div>}</Panel>
}

function Fees({token,fees,refs,can,onDone}:{token:string;fees:FeeType[];refs:ReferenceCatalog|null;can:(x:string)=>boolean;onDone:()=>Promise<void>}){
  const [error,setError]=useState('');const [busy,setBusy]=useState('');const existing=new Set(fees.map(f=>f.code));const labels=new Set(fees.map(f=>f.label.toLowerCase()));
  const presets=[...FEE_PRESETS,...(refs?.fee_types??[]).filter(r=>!FEE_PRESETS.some(p=>p.code===r.code)).map(r=>({code:r.code,label:r.label,periodicity:r.periodicity,regulatory:false,hint:''}))];
  const [custom,setCustom]=useState<{label:string;periodicity:FeeType['periodicity'];currency:'CDF'|'USD'}>({label:'',periodicity:'ONE_TIME',currency:'CDF'});
  async function add(code:string,label:string,periodicity:FeeType['periodicity'],currency:'CDF'|'USD',regulatory=false){try{setBusy(code);setError('');await createFeeType(token,{code,label,periodicity,default_currency:currency,regulatory});toast.success(`${label} ajouté`);await onDone()}catch(e){setError(friendlyError(e))}finally{setBusy('')}}
  const manage=can('settings.fee_types.manage');
  return <Panel title="Types de frais" subtitle="Choisissez un modèle courant ou créez un frais propre à l’école : le code interne est généré automatiquement. Aucun frais n’engendre de dette tant qu’un tarif n’est pas défini.">{error&&<div className="error" role="alert">{error}</div>}
    <div className="sw-field"><span>Modèles courants</span><div className="sw-chips">{presets.map(f=>{const have=existing.has(f.code);return <button key={f.code} type="button" className={`sw-chip ${have?'on':''}`} aria-pressed={have} disabled={have||!manage||busy===f.code} title={f.hint} onClick={()=>void add(f.code,f.label,f.periodicity,'CDF',!!f.regulatory)}>{have?'✓ ':'+ '}{f.label}</button>})}</div></div>
    {manage&&<form className="sw-inline sw-custom-fee" onSubmit={e=>{e.preventDefault();const label=custom.label.trim();if(label.length<2){setError('Indiquez le nom du frais, par exemple Frais de laboratoire.');return}if(labels.has(label.toLowerCase())){setError('Un type de frais porte déjà ce nom.');return}void add(autoCode(label,existing),label,custom.periodicity,custom.currency).then(()=>setCustom(c=>({...c,label:''})))}}>
      <input aria-label="Nom du frais personnalisé" placeholder="Frais propre à l’école (ex. Frais de laboratoire)" value={custom.label} onChange={e=>setCustom(c=>({...c,label:e.target.value}))}/>
      <select aria-label="Périodicité" value={custom.periodicity} onChange={e=>setCustom(c=>({...c,periodicity:e.target.value as FeeType['periodicity']}))}>{(['ONE_TIME','MONTHLY','PERIODIC','OPTIONAL'] as const).map(p=><option key={p} value={p}>{PERIODICITY_LABEL[p]??p}</option>)}</select>
      <select aria-label="Devise" value={custom.currency} onChange={e=>setCustom(c=>({...c,currency:e.target.value as 'CDF'|'USD'}))}><option value="CDF">CDF</option><option value="USD">USD</option></select>
      <UIButton variant="secondary" size="sm" icon="plus" type="submit">Créer</UIButton></form>}
    <div className="cardsList">{fees.map(f=><FeeRow key={f.id} token={token} fee={f} labels={labels} canEdit={manage} canToggle={f.enabled?can('settings.fee_types.activate'):manage} onDone={onDone} onError={setError}/>)}</div></Panel>}

// Desktop « modification depuis la ligne » (settings parity pass 2): rename, periodicity, currency, regulatory flag; a
// disabled fee keeps its history and its existing charges, it is only no longer proposed for new tariffs.
function FeeRow({token,fee,labels,canEdit,canToggle,onDone,onError}:{token:string;fee:FeeType;labels:Set<string>;canEdit:boolean;canToggle:boolean;onDone:()=>Promise<void>;onError:(m:string)=>void}){
  const [edit,setEdit]=useState(false);const [busy,setBusy]=useState(false);
  const [d,setD]=useState({label:fee.label,periodicity:fee.periodicity,currency:fee.default_currency,regulatory:fee.regulatory});
  useEffect(()=>setD({label:fee.label,periodicity:fee.periodicity,currency:fee.default_currency,regulatory:fee.regulatory}),[fee.version]);
  async function save(enabled:boolean,patch=d){const label=patch.label.trim();if(label.length<2){onError('Le nom du frais doit compter au moins deux caractères.');return}
    if(label.toLowerCase()!==fee.label.toLowerCase()&&labels.has(label.toLowerCase())){onError('Un autre type de frais porte déjà ce nom.');return}
    try{setBusy(true);onError('');await updateFeeType(token,fee,{label,periodicity:patch.periodicity,default_currency:patch.currency,regulatory:patch.regulatory,enabled});
      toast.success(enabled===fee.enabled?`${label} modifié`:enabled?`${label} réactivé`:`${label} désactivé (historique et frais existants conservés)`);setEdit(false);await onDone()}
    catch(e){onError(friendlyError(e))}finally{setBusy(false)}}
  return <article className={fee.enabled?'':'muted'}>
    {edit?<form className="feeEdit" onSubmit={e=>{e.preventDefault();void save(fee.enabled)}}>
      <input aria-label="Nom du frais" value={d.label} maxLength={140} onChange={e=>setD(x=>({...x,label:e.target.value}))}/>
      <select aria-label="Périodicité" value={d.periodicity} onChange={e=>setD(x=>({...x,periodicity:e.target.value as FeeType['periodicity']}))}>{(['ONE_TIME','MONTHLY','PERIODIC','OPTIONAL'] as const).map(p=><option key={p} value={p}>{PERIODICITY_LABEL[p]??p}</option>)}</select>
      <select aria-label="Devise" value={d.currency} onChange={e=>setD(x=>({...x,currency:e.target.value as 'CDF'|'USD'}))}><option value="CDF">CDF</option><option value="USD">USD</option></select>
      <label className="checkField"><input type="checkbox" checked={d.regulatory} onChange={e=>setD(x=>({...x,regulatory:e.target.checked}))}/> Réglementaire</label>
      <div className="formActions"><button type="button" className="ghost" disabled={busy} onClick={()=>setEdit(false)}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy?'Enregistrement…':'Enregistrer'}</button></div>
      {d.periodicity!==fee.periodicity&&<small className="policyHint">Changer la périodicité ne modifie pas les échéances déjà créées : réappliquez les barèmes pour les classes concernées.</small>}
    </form>:<><div><b>{fee.label}</b><small>{PERIODICITY_LABEL[fee.periodicity]??fee.periodicity} · {fee.default_currency}{fee.regulatory?' · réglementaire':''}</small></div>
      <div className="feeRowActions"><em className={`pill ${fee.enabled?'ready':''}`}>{fee.enabled?'Actif':'Inactif'}</em>
        {canEdit&&fee.enabled&&<button type="button" className="linkBtn" onClick={()=>setEdit(true)}>Modifier</button>}
        {canToggle&&<button type="button" className="linkBtn" disabled={busy} onClick={()=>void save(!fee.enabled,{label:fee.label,periodicity:fee.periodicity,currency:fee.default_currency,regulatory:fee.regulatory})}>{fee.enabled?'Désactiver':'Réactiver'}</button>}</div></>}
  </article>}

function IdentitySettings({token,overview,can,onDone}:{token:string;overview:SettingsOverview|null;can:(x:string)=>boolean;onDone:()=>Promise<void>}){const school=overview?.school;const schema=z.object({name:z.string().trim().min(2,'Nom obligatoire.'),email:z.string().trim().email('Adresse e-mail incomplète, par exemple direction@ecole.cd.').or(z.literal('')),phone:z.string().trim().regex(/^[+0-9 ()-]*$/,'Seuls les chiffres, espaces et le signe + sont acceptés.'),logo_url:z.string(),address:z.string(),city:z.string(),province:z.string(),motto:z.string().max(160,'160 caractères au plus.')});type F=z.infer<typeof schema>;const form=useForm<F>({resolver:zodResolver(schema),values:{name:school?.name??'',email:school?.email??'',phone:school?.phone??'',logo_url:school?.logo_url??'',address:school?.address??'',city:school?.city??'',province:school?.province??'',motto:school?.motto??''},...formDefaults});const [error,setError]=useState('');const save=form.handleSubmit(async v=>{if(!school)return;try{setError('');await updateSchoolIdentity(token,{name:v.name,email:v.email||null,phone:v.phone||null,logo_url:v.logo_url||null,address:v.address||null,city:v.city||null,province:v.province||null,motto:v.motto.trim()||null},school.version);toast.success('Identité de l’école enregistrée');await onDone()}catch(e){setError(friendlyError(e))}});return <Panel title="École & identité" subtitle="Coordonnées institutionnelles utilisées par l’interface et les documents.">{error&&<div className="error">{error}</div>}<LogoField token={token} canUpload={can('settings.documents.manage')}/><form className="settingsEditorGrid identityForm" onSubmit={save} noValidate><fieldset disabled={!can('settings.school_identity.update')}><legend>Établissement</legend><FormField label="Nom de l’école *" error={form.formState.errors.name?.message}><input autoComplete="organization" {...form.register('name')}/></FormField><FormField label="Devise / mention" hint="Imprimée sous le nom de l’école sur les reçus et rapports (ex. Travail – Discipline – Réussite)." error={form.formState.errors.motto?.message}><input maxLength={160} {...form.register('motto')}/></FormField></fieldset><fieldset disabled={!can('settings.school_identity.update')}><legend>Contact</legend><FormField label="Téléphone" error={form.formState.errors.phone?.message}><input type="tel" inputMode="tel" autoComplete="tel" placeholder="+243 …" {...form.register('phone')}/></FormField><FormField label="E-mail" error={form.formState.errors.email?.message}><input type="email" inputMode="email" autoComplete="email" {...form.register('email')}/></FormField></fieldset><fieldset disabled={!can('settings.school_identity.update')}><legend>Adresse</legend><FormField label="Adresse"><input autoComplete="street-address" {...form.register('address')}/></FormField><FormField label="Ville"><input autoComplete="address-level2" {...form.register('city')}/></FormField><FormField label="Province"><input autoComplete="address-level1" {...form.register('province')}/></FormField></fieldset>{can('settings.school_identity.update')&&<div className="stickyActions"><button className="primaryBtn" disabled={form.formState.isSubmitting||!form.formState.isDirty}>{form.formState.isSubmitting?'Enregistrement…':'Enregistrer'}</button></div>}</form></Panel>}

// Enrollment policy as enforced by the schooling module (required fields, guardian rules). The five terrain fields stay mandatory.
const ENROLLMENT_FIXED:[string,string][]=[['last_name','Nom'],['middle_name','Post-nom'],['first_name','Prénom'],['gender','Sexe'],['class_id','Classe']];
const ENROLLMENT_OPTIONAL:[string,string][]=[['birth_date','Date de naissance'],['birth_place','Lieu de naissance'],['nationality','Nationalité'],['address','Adresse'],['previous_school','École de provenance']];
function EnrollmentPolicySettings({token,can}:{token:string;can:(x:string)=>boolean}){
  const [policy,setPolicy]=useState<{version:number;payload:Record<string,unknown>}|null|undefined>(undefined);const [extra,setExtra]=useState<string[]>([]);const [guardian,setGuardian]=useState(false);const [phone,setPhone]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const editable=can('settings.enrollment_policy.manage');
  async function load(){try{setError('');const r=await getPolicy(token,'ENROLLMENT');setPolicy(r);const pl=(r?.payload??{}) as Record<string,unknown>;const req=Array.isArray(pl.required_student_fields)?pl.required_student_fields as string[]:[];setExtra(ENROLLMENT_OPTIONAL.map(([k])=>k).filter(k=>req.includes(k)));setGuardian(!!pl.guardian_required_at_enrollment);setPhone(!!pl.guardian_phone_required)}catch(e){setError(friendlyError(e))}}
  useEffect(()=>{void load()},[token]);
  async function save(e:React.FormEvent){e.preventDefault();try{setBusy(true);setError('');await putPolicy(token,'ENROLLMENT',{payload:{...(policy?.payload??{}),required_student_fields:[...ENROLLMENT_FIXED.map(([k])=>k),...extra],guardian_required_at_enrollment:guardian,guardian_phone_required:phone},status:'ACTIVE',expected_version:policy?.version??null});toast.success('Règles d’inscription enregistrées : elles s’appliquent aux prochaines inscriptions.');await load()}catch(e){setError(friendlyError(e))}finally{setBusy(false)}}
  if(policy===undefined&&!error)return <Loading/>;
  return <Panel title="Règles de saisie à l’inscription" subtitle="Informations que l’école exige pour inscrire un élève (réglage propre au Web). Les inscriptions déjà faites ne sont pas modifiées.">{error&&<div className="error" role="alert">{error}</div>}
    <form className="policyForm" onSubmit={save}><fieldset disabled={!editable||busy}><legend>Informations de l’élève</legend><p className="policyHint">Toujours obligatoires : {ENROLLMENT_FIXED.map(([,l])=>l).join(', ')}.</p>
      {ENROLLMENT_OPTIONAL.map(([k,l])=><label key={k} className="switchRow"><span>{l}<small>{extra.includes(k)?'Obligatoire':'Facultatif'}</small></span><input type="checkbox" role="switch" checked={extra.includes(k)} onChange={e=>setExtra(x=>e.target.checked?[...x,k]:x.filter(y=>y!==k))}/></label>)}</fieldset>
      <fieldset disabled={!editable||busy}><legend>Responsable</legend>
      <label className="switchRow"><span>Responsable exigé à l’inscription<small>Sans responsable ni foyer existant, l’inscription est refusée.</small></span><input type="checkbox" role="switch" checked={guardian} onChange={e=>setGuardian(e.target.checked)}/></label>
      <label className="switchRow"><span>Téléphone du responsable exigé<small>Quand un responsable est saisi, son téléphone devient obligatoire.</small></span><input type="checkbox" role="switch" checked={phone} onChange={e=>setPhone(e.target.checked)}/></label></fieldset>
      {editable&&<div className="stickyActions"><button className="primaryBtn" disabled={busy}>{busy?'Enregistrement…':'Enregistrer les règles'}</button></div>}
      {!editable&&<p className="policyHint">Lecture seule : la modification demande la permission de gérer la politique d’inscription.</p>}
    </form></Panel>
}

// The logo is a stored, verified image (PNG/JPEG ≤ 1 Mo, checked by its bytes server-side), never a free URL.
function LogoField({token,canUpload}:{token:string;canUpload:boolean}){
  const [src,setSrc]=useState<string|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const input=React.useRef<HTMLInputElement>(null);
  async function load(){try{const b=await schoolLogoBlob(token);setSrc(old=>{if(old)URL.revokeObjectURL(old);return b?URL.createObjectURL(b):null})}catch{setSrc(null)}}
  useEffect(()=>{void load();return()=>setSrc(old=>{if(old)URL.revokeObjectURL(old);return null})},[token]);
  async function pick(f:File|undefined){if(!f)return;setError('');if(!['image/png','image/jpeg'].includes(f.type)){setError('Choisissez une image PNG ou JPEG.');return}if(f.size>1024*1024){setError('Le logo dépasse 1 Mo : réduisez l’image puis réessayez.');return}try{setBusy(true);await uploadSchoolLogo(token,f);toast.success('Logo enregistré : il apparaîtra sur les prochains documents.');await load()}catch(e){setError(friendlyError(e))}finally{setBusy(false);if(input.current)input.current.value=''}}
  return <div className="logoField"><div className="logoPreview">{src?<img src={src} alt="Logo actuel de l’école"/>:<span aria-hidden="true"><NavGlyph g="school" size={26}/></span>}</div><div><b>Logo de l’école</b><small>{src?'Utilisé sur les documents imprimés.':'Aucun logo : les documents s’impriment sans logo.'} PNG ou JPEG, 1 Mo maximum.</small>{error&&<span className="fieldError" role="alert">{error}</span>}</div>{canUpload&&<><input ref={input} type="file" accept="image/png,image/jpeg" hidden onChange={e=>void pick(e.target.files?.[0])}/><button type="button" className="softBtn" disabled={busy} onClick={()=>input.current?.click()}>{busy?'Envoi…':src?'Remplacer':'Ajouter un logo'}</button></>}</div>
}


function ContributionsSettings({token,items,can,onDone}:{token:string;items:SettingsContribution[];can:(x:string)=>boolean;onDone:()=>Promise<void>}){const schema=z.object({label:z.string().trim().min(2,'Indiquez le nom de la contribution.'),unit:z.string().trim().min(1,'Indiquez l’unité.'),required_quantity:z.coerce.number().min(0)});type F=z.infer<typeof schema>;const form=useForm<F>({resolver:zodResolver(schema) as any,defaultValues:{label:'',unit:'unité',required_quantity:0},...formDefaults});const save=form.handleSubmit(async v=>{await createSettingsContribution(token,{...v,code:autoCode(v.label,items.map(x=>x.code))});form.reset({label:'',unit:'unité',required_quantity:0});toast.success('Contribution créée');await onDone()});return <Panel title="Contributions en nature" subtitle="Catalogue des fournitures ou biens attendus; les dépôts réels restent dans Effectifs & dépôts.">{can('settings.contributions.manage')&&<div className="sw-chips sw-presets">{CONTRIBUTION_PRESETS.filter(p=>!items.some(x=>x.label.toLowerCase()===p.label.toLowerCase())).map(p=><button key={p.label} type="button" className="sw-chip" onClick={()=>form.reset({label:p.label,unit:p.unit,required_quantity:p.qty})}>+ {p.label}</button>)}</div>}{can('settings.contributions.manage')&&<form className="settingsEditorGrid compact" onSubmit={save}><FormField label="Libellé"><input {...form.register('label')}/></FormField><FormField label="Unité"><input {...form.register('unit')}/></FormField><FormField label="Quantité exigée"><input type="number" min="0" step="any" {...form.register('required_quantity')}/></FormField><button className="primaryBtn">Ajouter</button></form>}<div className="cardsList">{items.map(x=><article key={x.id}><div><b>{x.label}</b><small>{x.code} · {x.unit}{Number(x.required_quantity??0)>0?` · exigé ${Number(x.required_quantity)}`:''}</small></div><em className={`pill ${x.enabled?'ready':''}`}>{x.enabled?'Actif':'Inactif'}</em></article>)}</div></Panel>}

// ProductsSettings: settings_products.tsx (stock catalogue, administrator finishing pass 2026-10-24).

function ModuleLoader(){return <div className="moduleLoader" role="status" aria-live="polite"><span className="moduleSpinner" aria-hidden="true"/><div className="loaderLine"><i/></div><b>Ouverture du module…</b><span>Préparation de votre espace de travail</span></div>}
function Loading(){return <ModuleLoader/>}
function Kpi({icon,value,label}:{icon:string;value:React.ReactNode;label:string}){return <article><span aria-hidden="true"><NavGlyph g={icon} size={20}/></span><b>{value}</b><small>{label}</small></article>}
function Panel({title,subtitle,children}:{title:string;subtitle?:string;children:React.ReactNode}){return <section className="panel"><div className="panelHead"><div><h3>{title}</h3>{subtitle&&<p>{subtitle}</p>}</div></div>{children}</section>}

type PlatformUser={full_name:string;email:string};
function Shell({title,subtitle,onLogout,onSwitchSpace,nav,children,user,token,roleLabel,theme,onTheme,photo}:{onSwitchSpace?:()=>void;title:string;subtitle:string;token?:string;roleLabel?:string;theme:ThemePref;onTheme:(t:ThemePref)=>void;photo:{url?:string;upload:(f:File)=>Promise<void>;remove:()=>Promise<void>};onLogout:()=>void;nav:[string,string,boolean,(()=>void)?,string?][];children:React.ReactNode;user:PlatformUser}){const [dialog,setDialog]=useState<''|'profile'|'security'|'preferences'>('');const shellNav:ShellNavItem[]=nav.map(([icon,label,active,go,key],i)=>({key:key||label,label,icon,active,onSelect:()=>go?.(),primary:i<3,shortLabel:label.split(' ')[0]}));const role=roleLabel||'Équipe plateforme';const context=`Plateforme EduSync · ${role}`;const account:ShellAccount={name:user.full_name||'Membre de l’équipe',email:user.email,context,role,avatarUrl:photo.url,items:[...(onSwitchSpace?[{key:'space',label:'Changer d’espace',icon:'layers',onSelect:onSwitchSpace}]:[]),{key:'profile',label:'Mon profil',icon:'user',onSelect:()=>setDialog('profile')},{key:'security',label:'Sécurité et appareils',icon:'shield',onSelect:()=>setDialog('security')},{key:'preferences',label:'Préférences',icon:'sliders',onSelect:()=>setDialog('preferences')},{key:'logout',label:'Se déconnecter',icon:'logout',onSelect:onLogout,danger:true}]};return <AppShell accountDock orgLabel="Plateforme" orgCode="Administration de la plateforme" mobileTitle="Plateforme EduSync" nav={shellNav} title={nav.find(n=>n[2])?.[1]||title} context={subtitle} tools={<>{token&&<NotificationBell token={token} canDismiss scope="platform"/>}<StatusChip/></>} account={account}>{children}{dialog==='profile'&&<ProfileDialog platform name={account.name} email={user.email} context={context} avatarUrl={photo.url} onPhotoUpload={photo.upload} onPhotoRemove={photo.remove} onClose={()=>setDialog('')}/>}{dialog==='security'&&token&&<SecurityDialog platform token={token} onClose={()=>setDialog('')} onPasswordChanged={onLogout}/>}{dialog==='preferences'&&<PreferencesDialog theme={theme} onTheme={onTheme} onClose={()=>setDialog('')}/>}</AppShell>}

// POINT 4D frozen navigation contract: ['settings','personnel','students','headcounts','home']
function SchoolApp({session,onLogout,onSwitchSpace}:{session:SavedSchoolSession;onLogout:()=>void;onSwitchSpace?:()=>void}){const [dialog,setDialog]=useState<''|'profile'|'security'>('');const [module,setModule]=useState('home');const goModule=(next:string)=>{if(next!==module)pushMobileScreen('school',next);setModule(next)};useEffect(()=>{replaceMobileRoot('school','home');const h=(e:Event)=>{const d=(e as CustomEvent).detail;if(d?.edusyncScope==='school'&&d.edusyncScreen)setModule(d.edusyncScreen)};window.addEventListener('edusync:android-back',h);return()=>window.removeEventListener('edusync:android-back',h)},[]);const [shellYears,setShellYears]=useState<AcademicYear[]>([]);const [selectedYearId,setSelectedYearId]=useState('');useEffect(()=>{let alive=true;listYearSelector(session.token).then(years=>{if(!alive)return;setShellYears(years);const saved=localStorage.getItem(`edusync.year.${session.school.id}`);const selected=(saved&&years.some(y=>y.id===saved)?saved:years.find(y=>y.status==='ACTIVE')?.id)||years[0]?.id||'';setSelectedYearId(selected)}).catch(()=>{if(alive)setShellYears([])});return()=>{alive=false}},[session.token,session.school.id]);function selectShellYear(id:string){setSelectedYearId(id);if(id)localStorage.setItem(`edusync.year.${session.school.id}`,id)}const selectedYear=shellYears.find(y=>y.id===selectedYearId);
  // Navigation, widgets and shortcuts come from the server (/access/me, owner decision 8): effective capabilities,
  // never a guess from prefixes or role names. Until it answers, only the home entry is shown.
  const [me,setMe]=useState<AccessMe|null>(null),[meError,setMeError]=useState<unknown>(null),[meAttempt,setMeAttempt]=useState(0);
  useEffect(()=>{let alive=true;getAccessMe(session.token).then(m=>{if(alive){setMe(m);setMeError(null)}}).catch(e=>{if(alive)setMeError(e)});return()=>{alive=false}},[session.token,meAttempt]);
  const nav=me?.navigation??[{key:'home',label:'Accueil',icon:'home'}];
  const canOpenModule=(key:string)=>nav.some(x=>x.key===key);
  useEffect(()=>{if(me&&!canOpenModule(module))setModule('home')},[me]);
  const currentLabel=nav.find(x=>x.key===module)?.label||'EduSync';
  const shortLabels:Record<string,string>={home:'Accueil',students:'Élèves',finance:'Finance',documents:'Documents'};
  const shellNav:ShellNavItem[]=nav.map(({icon,label,key})=>({key,label,icon,active:module===key,onSelect:()=>goModule(key),primary:['home','students','finance','documents'].includes(key),shortLabel:shortLabels[key]}));
  const yearLabel=selectedYear?.label;
  const account:ShellAccount={name:session.user.full_name,email:session.user.email,context:`${session.school.name} · ${session.school.code}`,detail:yearLabel?(/^ann[ée]e/i.test(yearLabel)?yearLabel:`Année ${yearLabel}`):undefined,items:[
    ...(onSwitchSpace?[{key:'space',label:'Changer d’espace',icon:'layers',onSelect:onSwitchSpace}]:[]),
    {key:'profile',label:'Mon profil',icon:'user',onSelect:()=>setDialog('profile')},
    ...(canOpenModule('settings')?[{key:'settings',label:'Paramètres de l’école',icon:'settings',onSelect:()=>goModule('settings')}]:[]),
    {key:'security',label:'Sécurité et appareils',icon:'shield',onSelect:()=>setDialog('security')},
    {key:'logout',label:'Se déconnecter',icon:'logout',onSelect:onLogout,danger:true}]};
  const yearSelect=(where:string)=>shellYears.length>0&&<label className={`es-year es-year-${where}`} title="Année scolaire consultée"><NavGlyph g="calendar" size={15}/><span>Année</span><select aria-label="Année scolaire consultée" value={selectedYearId} onChange={e=>selectShellYear(e.target.value)}>{shellYears.map(y=><option key={y.id} value={y.id} title={y.status==='ACTIVE'?'Année en cours':y.status==='CLOSED'?'Année clôturée':undefined}>{y.code||y.label}</option>)}</select></label>;
  const tools=<>{yearSelect('top')}<StatusChip compact={false}/>{session.permissions.includes('notifications.internal.read')&&<NotificationBell token={session.token} canDismiss={session.permissions.includes('notifications.internal.dismiss')}/>}</>;
  // Same shell conventions as the platform (owner decision 10): account docked in the sidebar, space switch in the
  // account menu, breadcrumb back to the home, one local boundary per screen (decision 11).
  return <AppShell accountDock orgLabel={session.school.name} orgCode={session.school.code} drawerTools={yearSelect('drawer')} nav={shellNav} title={currentLabel} context={`${session.school.name}${yearLabel?` · ${yearLabel}`:''}`} tools={tools} account={account}>
    <OfflineAdminBanner/>
    {module!=='home'&&module!=='settings'&&<PageTrail parents={[{label:'Accueil',onSelect:()=>goModule('home')}]} current={currentLabel}/>}
    <ScreenBoundary resetKey={module} label={module}><Suspense fallback={<ModuleLoader/>}>{module==='settings'?<SettingsPage session={session} onHome={()=>goModule('home')} links={nav.filter(x=>['access','sync','documents'].includes(x.key))} onNavigate={goModule}/>:module==='personnel'?<PersonnelPage token={session.token} permissions={session.permissions} schoolName={session.school.name}/>:module==='students'?<SchoolingPage token={session.token} permissions={session.permissions} schoolName={session.school.name}/>:module==='headcounts'?<EffectifsPage token={session.token} permissions={session.permissions} schoolName={session.school.name} yearId={selectedYearId||undefined}/>:module==='finance'?<FinancePage token={session.token} permissions={session.permissions}/>:module==='documents'?<DocumentsPage token={session.token} permissions={session.permissions} schoolName={session.school.name}/>:module==='stewardship'?<StewardshipPage token={session.token} permissions={session.permissions}/>:module==='sync'?<SyncAdminPage token={session.token} permissions={session.permissions}/>:module==='access'?<AccessPage token={session.token} permissions={session.permissions} userName={session.user.full_name}/>:module==='communications'?<CommunicationsPage token={session.token} permissions={session.permissions} schoolId={session.school.id} schoolName={session.school.name} onNavigate={goModule}/>:module==='home'?(me?<HomePage token={session.token} me={me} schoolName={session.school.name} userName={session.user.full_name} onNavigate={goModule} yearId={selectedYearId||undefined} yearLabel={selectedYear?.label}/>:meError?<ScreenError error={meError} onRetry={()=>setMeAttempt(a=>a+1)}/>:<ModuleLoader/>):<Panel title="Module" subtitle="Ce module sera activé lorsqu’il disposera de ses contrats métier certifiés."><div/></Panel>}</Suspense></ScreenBoundary>
    {dialog==='profile'&&<ProfileDialog name={session.user.full_name} email={session.user.email} context={`${session.school.name} · ${session.school.code}`} detail={yearLabel} onClose={()=>setDialog('')}/>}
    {dialog==='security'&&<SecurityDialog token={session.token} onClose={()=>setDialog('')} onPasswordChanged={onLogout}/>}
  </AppShell>}

export function App({initialLink=null}:{initialLink?:AccountLink|null}={}){
  // Account link e-mailed by EduSync (#invitation=… / #reset=…), read by main.tsx BEFORE any session restoration (fix
  // 2026-10-24: an invitation opened from the installed Android PWA stayed on the boot screen forever). An already-open
  // PWA receives a new link as a same-document navigation: hashchange, no reload.
  const [pendingLink,setPendingLink]=useState<AccountLink|null>(initialLink);
  useEffect(()=>{const h=()=>{const l=takeAccountLink();if(l){console.info('edusync.invitation',{stage:'link',result:'received-open-app'});setPendingLink(l)}};
    window.addEventListener('hashchange',h);return()=>window.removeEventListener('hashchange',h)},[]);
  useEffect(()=>{const offBack=installMobileBackCoordinator();const offDirty=installUnsavedFormGuard();return()=>{offBack();offDirty()}},[]);
  const [platformToken,setPlatformToken]=useState('');
  const [platformUser,setPlatformUser]=useState<PlatformUser>({full_name:'',email:''});
  const [schoolSession,setSchoolSession]=useState<SavedSchoolSession|null>(null);
  const [restoring,setRestoring]=useState(true);
  // Spaces of the identity (server truth): the "Changer d’espace" entry only exists when there is more than one.
  const [spaces,setSpaces]=useState<SpacesState|null>(null);const [switching,setSwitching]=useState(false);const [recovery,setRecovery]=useState<SpacesState|null>(null);
  const activeKey=schoolSession?spaceKey({scope:'SCHOOL',school_code:schoolSession.school.code}):platformToken?'PLATFORM':'';
  useEffect(()=>{if(!activeKey){setSpaces(null);return}let alive=true;rememberSpace(activeKey);fetchSpaces().then(x=>{if(alive)setSpaces(x)}).catch(()=>undefined);return()=>{alive=false}},[activeKey]);
  /* Applies the server's answer to a change of space: the previous space is forgotten entirely (its screens are
     unmounted, its token is already dead server-side); each space keeps its own last page and filters. */
  function applySpace(r:any){
    setSwitching(false);setRecovery(null);
    if(!r){clear();return}
    try{if(activeKey)sessionStorage.setItem(`edusync.url.${activeKey}`,window.location.search)}catch{/* facultatif */}
    const next=r.scope==='SCHOOL'?spaceKey({scope:'SCHOOL',school_code:r.school?.code}):'PLATFORM';
    let saved='';try{saved=sessionStorage.getItem(`edusync.url.${next}`)||''}catch{/* facultatif */}
    history.replaceState(null,'',window.location.pathname+saved);
    if(r.scope==='SCHOOL'){setPlatformToken('');openSchool({token:r.access_token,school:r.school,user:r.user,permissions:r.permissions||[]})}
    else{setSchoolSession(null);setPlatformUser({full_name:r.user?.full_name||'',email:r.user?.email||''});setPlatformToken(r.access_token)}
    toast.success(r.scope==='SCHOOL'?`Espace ouvert : ${r.school?.name}`:'Espace ouvert : Plateforme EduSync');
  }
  // The token of the current space can no longer be renewed: either the session is over (sign-in screen) or only
  // this space was withdrawn (the identity picks another one without signing in again).
  const checking=useRef(false);
  async function onRefused(){if(checking.current)return;checking.current=true;try{const st=await fetchSpaces();if(!st){clear();return}if(!st.current_valid)setRecovery(st)}catch{/* réseau : l’écran courant signale l’erreur */}finally{checking.current=false}}
  useEffect(()=>{const h=()=>{void onRefused()};window.addEventListener('edusync:space-check',h);return()=>window.removeEventListener('edusync:space-check',h)},[]);
  useEffect(()=>{
    let alive=true, running=false;
    restoreOfflineContext();
    async function restore(){
      if(running)return;
      // An account link is handled first: no session restoration behind it, and the boot screen is released at once
      // (the former early return here never ended `restoring`: endless boot screen).
      if(initialLink){if(alive)setRestoring(false);return}
      running=true;
      // Never wait forever for the session service: after 10 s the cached context or the sign-in screen is shown.
      const ctl=new AbortController();const timer=window.setTimeout(()=>ctl.abort(),10000);
      try{
        const r=await fetch('/api/v1/auth/refresh',{method:'POST',credentials:'include',cache:'no-store',signal:ctl.signal});
        if(!alive)return;
        if(!r.ok){
          if(r.status===401 || r.status===403){
            const st=await fetchSpaces();
            if(!alive)return;
            clearPlatformContext();setPlatformToken('');setSchoolSession(null);
            if(st&&!st.current_valid&&st.contexts.length)setRecovery(st);
            return;
          }
          throw new Error('SESSION_SERVICE_UNAVAILABLE');
        }
        const d=await r.json();if(!alive||!d.access_token)return;
        if(d.scope==='SCHOOL'&&d.school&&d.user){setPlatformAuthState('ONLINE_AUTHENTICATED');setPlatformToken('');openSchool({token:d.access_token,school:d.school,user:d.user,permissions:d.permissions||[]});}
        else if(d.scope==='PLATFORM'){
          const previous=knownPlatform();
          if(previous&&d.user?.email&&previous.me.user.email.toLowerCase()!==d.user.email.toLowerCase())clearPlatformContext();
          setPlatformAuthState('ONLINE_AUTHENTICATED');setPlatformToken(d.access_token);
          if(d.user)setPlatformUser({full_name:d.user.full_name,email:d.user.email});
        }
      }catch{
        // A timeout is not proof of revocation. Restore display-only context,
        // never a cached bearer token or authority to perform a mutation.
        // Each context keeps its own offline policy (24 h platform, 7 days school: offline_session.ts).
        const cached=knownContext();
        if(alive&&cached?.kind==='PLATFORM'){setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');setPlatformUser(cached.me.user);setPlatformToken(t=>t||OFFLINE_PLATFORM_TOKEN);}
        else if(alive&&cached?.kind==='SCHOOL'){setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED');setSchoolSession(s=>s||{token:OFFLINE_SCHOOL_TOKEN,...cached.session});}
      }finally{clearTimeout(timer);running=false;if(alive)setRestoring(false);}
    }
    const online=()=>{void restore()};
    const offline=()=>{if(knownContext())setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED')};
    const probe=(e:Event)=>{if((e as CustomEvent).detail?.state==='ONLINE'&&getPlatformAuthState()==='OFFLINE_AUTHENTICATED_CACHED'&&knownContext()&&navigator.onLine)void restore()};
    window.addEventListener('online',online);window.addEventListener('offline',offline);window.addEventListener('edusync:connectivity',probe);
    void restore();
    return()=>{alive=false;window.removeEventListener('online',online);window.removeEventListener('offline',offline);window.removeEventListener('edusync:connectivity',probe)};
  },[]);
  useEffect(()=>{const h=(e:Event)=>{const d=(e as CustomEvent).detail||{};if(!d.token)return;if(d.scope==='SCHOOL')setSchoolSession(prev=>prev?{...prev,token:d.token}:prev);else setPlatformToken(d.token)};window.addEventListener('edusync:token-refreshed',h);return()=>window.removeEventListener('edusync:token-refreshed',h)},[]);
  function clear(){clearPlatformContext();setRecovery(null);setSwitching(false);void fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'}).catch(()=>{});localStorage.removeItem(PLATFORM_TOKEN);localStorage.removeItem(SCHOOL_SESSION);setPlatformToken('');setSchoolSession(null)}
  // A school session validated online becomes the school's offline context BEFORE its screens mount, so their first
  // reads (/access/me, settings…) are already kept for an offline reopening.
  function openSchool(next:SavedSchoolSession){if(next.token!==OFFLINE_SCHOOL_TOKEN)rememberSchoolContext(next);setSchoolSession(next)}
  // A school session validated online becomes the school's offline context (display only, no token).
  useEffect(()=>{if(schoolSession&&schoolSession.token!==OFFLINE_SCHOOL_TOKEN&&getPlatformAuthState()!=='OFFLINE_AUTHENTICATED_CACHED')rememberSchoolContext(schoolSession)},[schoolSession]);
  useEffect(()=>{if(!restoring)dismissBoot()},[restoring]);
  // While the persistent session is checked, the static boot screen (index.html) stays on screen: one continuous start.
  if(restoring)return null;
  // A link received while a session is open (PWA already open): the link screen first, then back to the open space.
  if(pendingLink&&(schoolSession||platformToken))return <SecureLogin key={`link:${pendingLink.token.slice(0,8)}`} initialLink={pendingLink} onLinkHandled={()=>setPendingLink(null)}
    onPlatform={(token,user)=>{setPendingLink(null);setSchoolSession(null);setPlatformUser(user);setPlatformToken(token)}} onSchool={s=>{setPendingLink(null);setPlatformToken('');openSchool(s)}}/>;
  if(recovery)return <SpaceRecovery spaces={recovery} onSwitched={applySpace} onLogout={()=>{setRecovery(null);clear()}}/>;
  const switcher=switching&&<div className="es-stepup-layer es-space-layer"><SpaceSwitcher onClose={()=>setSwitching(false)} onSwitched={applySpace}/></div>;
  const openSwitcher=spaces&&spaces.contexts.length>1?()=>setSwitching(true):undefined;
  if(schoolSession)return <><SchoolApp key={`school:${schoolSession.school.id}`} session={schoolSession} onLogout={clear} onSwitchSpace={openSwitcher}/>{switcher}</>;
  if(platformToken)return <><AtelierPro key="platform" token={platformToken} user={platformUser} onLogout={clear} onSwitchSpace={openSwitcher}/>{switcher}</>;
  return <SecureLogin key='login' initialLink={pendingLink} onLinkHandled={()=>setPendingLink(null)}
    onPlatform={(token,user)=>{setPendingLink(null);setPlatformUser(user);setPlatformToken(token)}} onSchool={s=>{setPendingLink(null);openSchool(s)}}/>;
}
