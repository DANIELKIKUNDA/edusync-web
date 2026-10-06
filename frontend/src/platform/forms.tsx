import React,{useId} from 'react';
/* Shared form field: explicit label association (id/htmlFor), error announced and linked to the control. */
export function FormField({label,error,children,hint}:{label:string;error?:string;children:React.ReactNode;hint?:string}){
 const auto=useId();
 const child=React.isValidElement(children)?children as React.ReactElement<any>:null;
 const id=(child?.props?.id as string|undefined)||`f${auto.replace(/[^a-zA-Z0-9_-]/g,'')}`;
 const describedBy=error?`${id}-err`:hint?`${id}-hint`:undefined;
 const control=child?React.cloneElement(child,{id,'aria-invalid':error?true:child.props['aria-invalid'],'aria-describedby':describedBy||child.props['aria-describedby']}):children;
 return <label className={`formField ${error?'invalid':''}`} htmlFor={child?id:undefined}><span>{label}</span>{control}{hint&&!error&&<small id={`${id}-hint`}>{hint}</small>}{error&&<small id={`${id}-err`} className="fieldError" role="alert">{error}</small>}</label>}
export const formDefaults={mode:'onBlur' as const,reValidateMode:'onChange' as const,shouldFocusError:true};
