/** Fades out and removes the static boot screen rendered by index.html. Idempotent. */
export function dismissBoot(){
  const el=document.getElementById('edusync-boot');
  if(!el||el.classList.contains('out'))return;
  el.classList.add('out');
  window.setTimeout(()=>el.remove(),320);
}
