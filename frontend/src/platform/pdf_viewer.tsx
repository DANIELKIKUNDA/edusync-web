import React,{useEffect,useRef,useState} from 'react';
import {NavGlyph} from './nav_icons';

export type PdfPreviewDetail={url:string;title?:string;revokeOnClose?:boolean};

export function PdfPreviewHost(){
  const [doc,setDoc]=useState<PdfPreviewDetail|null>(null);
  const frame=useRef<HTMLIFrameElement>(null);
  useEffect(()=>{
    const open=(e:Event)=>{const d=(e as CustomEvent<PdfPreviewDetail>).detail;if(d?.url)setDoc(d)};
    window.addEventListener('edusync:pdf-preview',open);
    return()=>window.removeEventListener('edusync:pdf-preview',open);
  },[]);
  useEffect(()=>{
    if(!doc)return;
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();close()}};
    window.addEventListener('keydown',key);
    return()=>window.removeEventListener('keydown',key);
  },[doc]);
  function close(){
    setDoc(cur=>{if(cur?.revokeOnClose)try{URL.revokeObjectURL(cur.url)}catch{/* ignore */}return null});
  }
  function print(){
    try{frame.current?.contentWindow?.focus();frame.current?.contentWindow?.print()}
    catch{if(doc){const w=window.open(doc.url,'_blank');if(w)try{w.opener=null}catch{/* cross origin */}}}
  }
  if(!doc)return null;
  return <div className="pdfv-backdrop" onMouseDown={e=>e.target===e.currentTarget&&close()}>
    <section className="pdfv-shell" role="dialog" aria-modal="true" aria-label={doc.title||'Aperçu PDF'}>
      <header className="pdfv-head"><button type="button" className="pdfv-icon" onClick={close} aria-label="Retour"><NavGlyph g="chevronLeft" size={19}/></button>
        <div><b>{doc.title||'Document PDF'}</b><small>Aperçu dans EduSync</small></div>
        <div className="pdfv-actions"><button type="button" onClick={print}><NavGlyph g="print" size={16}/>Imprimer</button>
          <a href={doc.url} download><NavGlyph g="download" size={16}/>Télécharger</a>
          <a href={doc.url} target="_blank" rel="noopener"><NavGlyph g="external" size={16}/>Ouvrir séparément</a>
          <button type="button" className="pdfv-icon" onClick={close} aria-label="Fermer"><NavGlyph g="close" size={18}/></button></div>
      </header>
      <iframe ref={frame} className="pdfv-frame" src={doc.url} title={doc.title||'Document PDF'}/>
    </section>
  </div>;
}
