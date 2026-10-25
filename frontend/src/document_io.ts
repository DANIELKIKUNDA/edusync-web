/* Point 5B — professional document I/O.
   PDF printing always previews first. Exports can use one school-selected folder and overwrite
   the same logical file instead of creating browser duplicates. */
import {UserFacingError} from './platform/errors';
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
 const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=clean(loc.filename);a.click();setTimeout(()=>URL.revokeObjectURL(u),30_000);return 'download';
}
// window.open(…,'noopener') ALWAYS returns null (HTML spec), even when the tab opened: every PDF preview then reported a
// false « blocked » error shown as the generic sentence (owner report 2026-10-25). Open normally, then cut the opener.
export function previewPdf(blob:Blob){const u=URL.createObjectURL(blob);const w=window.open(u,'_blank');if(!w){URL.revokeObjectURL(u);throw new UserFacingError('Le navigateur a bloqué l’ouverture du PDF. Autorisez les fenêtres EduSync pour ce site, puis réessayez.','POPUP_BLOCKED')}try{w.opener=null}catch{/* other origin */}setTimeout(()=>URL.revokeObjectURL(u),120_000)}
