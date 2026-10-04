import React from 'react';
export function FormField({label,error,children,hint}:{label:string;error?:string;children:React.ReactNode;hint?:string}){return <label className={`formField ${error?'invalid':''}`}><span>{label}</span>{children}{hint&&!error&&<small>{hint}</small>}{error&&<small className="fieldError" role="alert">{error}</small>}</label>}
export const formDefaults={mode:'onBlur' as const,reValidateMode:'onChange' as const,shouldFocusError:true};
