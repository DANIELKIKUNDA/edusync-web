export type TextPromptOptions={title:string;message?:string;label:string;placeholder?:string;confirmLabel?:string;required?:boolean;minLength?:number};

export function promptText(options:TextPromptOptions):Promise<string|null>{
  return new Promise(resolve=>{
    const host=document.createElement('div');host.className='eduDialogBackdrop';host.setAttribute('role','presentation');
    const dialog=document.createElement('section');dialog.className='eduDialog';dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');
    const titleId=`edu-dialog-${crypto.randomUUID()}`;dialog.setAttribute('aria-labelledby',titleId);
    const head=document.createElement('div');head.className='eduDialogHead';
    const copy=document.createElement('div');const h=document.createElement('h3');h.id=titleId;h.textContent=options.title;copy.appendChild(h);
    if(options.message){const p=document.createElement('p');p.textContent=options.message;copy.appendChild(p)}head.appendChild(copy);
    const close=document.createElement('button');close.type='button';close.className='eduDialogClose';close.textContent='×';close.setAttribute('aria-label','Fermer');head.appendChild(close);
    const form=document.createElement('form');form.noValidate=true;
    const label=document.createElement('label');const span=document.createElement('span');span.textContent=`${options.label}${options.required===false?'':' *'}`;label.appendChild(span);
    const input=document.createElement('textarea');input.rows=3;input.placeholder=options.placeholder??'';input.required=options.required!==false;input.minLength=options.minLength??3;label.appendChild(input);
    const error=document.createElement('small');error.className='eduFieldError';label.appendChild(error);form.appendChild(label);
    const actions=document.createElement('div');actions.className='eduDialogActions';const cancel=document.createElement('button');cancel.type='button';cancel.className='ghost';cancel.textContent='Annuler';const ok=document.createElement('button');ok.type='submit';ok.textContent=options.confirmLabel??'Confirmer';actions.append(cancel,ok);form.appendChild(actions);
    dialog.append(head,form);host.appendChild(dialog);document.body.appendChild(host);
    const finish=(value:string|null)=>{document.removeEventListener('keydown',escape);host.remove();resolve(value)};
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')finish(null)};document.addEventListener('keydown',escape);
    close.onclick=()=>finish(null);cancel.onclick=()=>finish(null);host.onmousedown=e=>{if(e.target===host)finish(null)};
    form.onsubmit=e=>{e.preventDefault();const value=input.value.trim();if(input.required&&!value){error.textContent='Ce champ est obligatoire.';input.focus();return}if(value.length<input.minLength){error.textContent=`Saisissez au moins ${input.minLength} caractères.`;input.focus();return}finish(value)};
    queueMicrotask(()=>input.focus());
  });
}
