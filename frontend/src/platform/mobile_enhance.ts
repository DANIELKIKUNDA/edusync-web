// Mobile-first pass (2026-10-31): two behaviours every screen gets on a phone, without touching each screen.
// 1. A data table becomes one card per record (mobile.css, table.m-cards): each cell receives the label of its column.
//    Tables marked data-keep-table (comparisons read across rows) are left as they are.
// 2. A tab touched in a swiped tab bar is brought to the centre, so the next one is always visible.
const PHONE = '(max-width:767.98px)';
function label(table: HTMLTableElement) {
  if (table.dataset.keepTable !== undefined || table.closest('[data-keep-table]')) return;
  const heads = [...table.querySelectorAll('thead th')].map(th => (th.textContent || '').trim());
  if (heads.length < 2) return;
  table.querySelectorAll('tbody tr').forEach(tr => [...tr.children].forEach((td, i) => { if (heads[i] && !(td as HTMLElement).dataset.label) (td as HTMLElement).dataset.label = heads[i]; }));
  table.classList.add('m-cards');
}
// Grids drawn with blocks instead of <table> (recovery, registers, compact tables…): a header row (class « head » or
// « th ») followed by rows.
function labelGrid(grid: HTMLElement) {
  if (grid.dataset.keepTable !== undefined || grid.classList.contains('m-cards-div')) return;
  const rows = [...grid.children] as HTMLElement[]; const head = rows[0];
  if (!head || !(head.classList.contains('head') || head.classList.contains('th')) || head.children.length < 2) return;
  const heads = [...head.children].map(c => (c.textContent || '').trim());
  rows.slice(1).forEach(r => [...r.children].forEach((c, i) => { if (heads[i]) (c as HTMLElement).dataset.label = heads[i]; }));
  grid.classList.add('m-cards-div');
}
export function installMobileEnhancements() {
  if (typeof window === 'undefined' || !window.matchMedia) return;
  const mq = window.matchMedia(PHONE); let queued = false;
  const scan = () => { queued = false; if (!mq.matches) { document.querySelectorAll('.m-cards,.m-cards-div').forEach(t => t.classList.remove('m-cards', 'm-cards-div')); return; }
    document.querySelectorAll<HTMLTableElement>('.es-content table').forEach(label);
    document.querySelectorAll<HTMLElement>('.es-content [class*="Table"]:not(table)').forEach(labelGrid); };
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(scan); } }).observe(document.body, {childList: true, subtree: true});
  mq.addEventListener('change', scan); scan();
  document.addEventListener('click', e => { if (!mq.matches) return;
    const tab = (e.target as HTMLElement | null)?.closest?.('[role=tab], .personTabs > *, .financeTabs > *, .kp-tabs > *, .fxTabs > *, .commTabs > *');
    if (tab) (tab as HTMLElement).scrollIntoView({behavior: 'smooth', inline: 'center', block: 'nearest'}); }, true);
}
