export class UserFacingError extends Error{constructor(message:string,public code='GENERIC'){super(message)}}
export function friendlyHttpMessage(status:number){if(status===400||status===422)return 'Certaines informations sont incorrectes. Vérifiez le formulaire.';if(status===401)return 'Votre session a expiré. Reconnectez-vous.';if(status===403)return "Vous n’avez pas l’autorisation d’effectuer cette action.";if(status===404)return 'La donnée demandée est introuvable.';if(status===409||status===412)return 'Cette information a changé. Actualisez puis réessayez.';if(status===429)return 'Trop de tentatives. Patientez un instant puis réessayez.';if(status>=500)return 'Le service rencontre momentanément une difficulté. Votre travail reste protégé.';return 'Cette opération n’a pas pu aboutir. Réessayez.'}
// Server refusals explained to the user (2026-10-24): the reason the server gives is kept, translated when it is a
// technical shape (validation list, permission code, version conflict, server error reference). Every message built
// here is remembered so friendlyError shows it instead of the generic sentence.
const explained=new Set<string>();
const FIELD:Record<string,string>={name:'Nom',label:'Libellé',code:'Code',email:'E-mail',phone:'Téléphone',address:'Adresse',city:'Ville',province:'Province',logo_url:'Logo',
  start_date:'Date de rentrée',end_date:'Date de fin',amount:'Montant',currency:'Devise',periodicity:'Périodicité',reason:'Motif',quantity:'Quantité',section_id:'Section',
  class_id:'Classe',academic_year_id:'Année scolaire',fee_type_id:'Type de frais',full_name:'Nom complet',password:'Mot de passe',due_date:'Échéance',unit_price:'Prix unitaire'};
const VALIDATION:Record<string,string>={missing:'est obligatoire',string_too_short:'est trop court',string_too_long:'est trop long',string_pattern_mismatch:'n’a pas le bon format',
  value_error:'n’est pas valide',greater_than:'doit être plus grand',greater_than_equal:'doit être positif ou nul',less_than_equal:'est trop grand',int_parsing:'doit être un nombre entier',
  decimal_parsing:'doit être un nombre',date_from_datetime_parsing:'doit être une date',date_parsing:'doit être une date',enum:'n’est pas une valeur proposée',uuid_parsing:'n’est pas valide'};
export function explainHttpError(status:number,body:unknown):string{
  const b=(body??{}) as {detail?:unknown;correlation_id?:string};const d=b.detail;
  let text='';
  if(Array.isArray(d)){
    const parts=d.slice(0,3).map((x:any)=>{const field=String((x?.loc??[]).filter((k:unknown)=>typeof k==='string'&&k!=='body').at(-1)??'');
      return `${FIELD[field]??(field?field.replace(/_/g,' '):'Une valeur')} ${VALIDATION[String(x?.type??'')]??'n’est pas valide'}`});
    text=`Enregistrement refusé : ${parts.join(' ; ')}.`;
  }else if(d&&typeof d==='object'&&typeof (d as any).message==='string')text=(d as any).message;
  else if(typeof d==='string')text=d;
  if(status===403&&/^Permission requise\s*:/.test(text))text=`Vous n’avez pas le droit d’effectuer cette action. Demandez-le au gestionnaire des accès de votre école (droit requis : ${text.split(':').slice(1).join(':').trim()}).`;
  if((status===409||status===412)&&/modifi[ée]e? par une autre session|version/i.test(text))text='Cette fiche vient d’être modifiée ailleurs (autre onglet ou autre personne). Rechargez la page pour voir la dernière version, puis refaites votre modification.';
  if(status>=500||/erreur inattendue/i.test(text)){const ref=b.correlation_id?String(b.correlation_id).slice(0,8):(/Référence : ([0-9a-f]+)/.exec(text)?.[1]??'');
    text=`Le serveur n’a pas pu enregistrer : une erreur technique est survenue de notre côté, pas dans votre saisie. Rien n’a été modifié. Réessayez dans un instant${ref?` ; si cela persiste, communiquez la référence ${ref} au support`:''}.`;}
  if(!text)text=friendlyHttpMessage(status);
  explained.add(text);if(explained.size>200)explained.delete(explained.values().next().value as string);
  return text;
}
export function friendlyError(error:unknown){if(error instanceof UserFacingError)return error.message;if(error instanceof Error&&explained.has(error.message))return error.message;if(error instanceof DOMException&&error.name==='AbortError')return 'La connexion est trop lente : l’opération n’a pas pu être confirmée. Réessayez ; EduSync empêche tout doublon.';if(error instanceof TypeError)return 'Connexion interrompue : l’opération n’a pas pu être confirmée. Réessayez dès que la connexion revient ; EduSync empêche tout doublon.';return 'Une difficulté est survenue. Réessayez ; si elle persiste, contactez l’administrateur.'}
export function reportTechnical(error:unknown,context:string){console.error('[EduSync]',context,error)}
