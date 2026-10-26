/* Point 5B — professional document I/O.
   PDF printing always previews first. Exports can use one school-selected folder and overwrite
   the same logical file instead of creating browser duplicates. */
export type ExportLocation={school:string;academicYear?:string;module:string;category:string;filename:string};
type DirHandle=any;
let rootHandle:DirHandle|null=null;
const clean=(s:string)=>s.replace(/[<>:"/\\|?*\x00-\x1F]/g,'_').replace(/\s+/g,' ').trim()||'Non classe';
export function supportsManagedExportFolder(){return typeof (window as any).showDirectoryPicker==='function'}
export async function chooseManagedExportFolder():Promise<boolean>{
 if(!supportsManagedExportFolder())return false;
 rootHandle=await (window as any).showDirectoryPicker({id:'edusync-documents',mode:'readwrite',startIn:'documents'});
 return !!rootHandle;
}
export function managedFolderReady(){return !!rootHandle}
async function child(root:DirHandle,name:string){return root.getDirectoryHandle(clean(name),{create:true})}
export async function exportManaged(blob:Blob,loc:ExportLocation):Promise<'managed'|'download'> {
 if(rootHandle){
   try{
    let d=await child(rootHandle,'Documents EduSync'); d=await child(d,loc.school); if(loc.academicYear)d=await child(d,loc.academicYear); d=await child(d,loc.module); d=await child(d,loc.category);
    const f=await d.getFileHandle(clean(loc.filename),{create:true}); const w=await f.createWritable(); await w.write(blob); await w.close(); return 'managed';
   }catch(e){console.warn('EduSync managed export unavailable, browser fallback',e)}
 }
 // The link is attached to the page before the click: a detached link is not always honoured by the browser (2026-10-25).
 const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=clean(loc.filename);a.rel='noopener';a.style.display='none';document.body.appendChild(a);a.click();setTimeout(()=>{a.remove();URL.revokeObjectURL(u)},30_000);return 'download';
}
/** PDF stays inside EduSync by default. The viewer still offers Print, Download and « Open separately ». */
export function previewPdf(blob:Blob,title='Document PDF'){
  const u=URL.createObjectURL(blob);
  const accepted=window.dispatchEvent(new CustomEvent('edusync:pdf-preview',{detail:{url:u,title,revokeOnClose:true}}));
  // dispatchEvent returning false only means preventDefault; the host is mounted in App for every authenticated space.
  if(!accepted)URL.revokeObjectURL(u);
}
export function previewPdfUrl(url:string,title='Document PDF'){
  window.dispatchEvent(new CustomEvent('edusync:pdf-preview',{detail:{url,title,revokeOnClose:false}}));
}
