/* V2 lot 3c — the teacher's grade sheets are kept on the phone (owner 2026-11-22: « encore plus de facilité »; the school
   works offline — 2026-10-25). When the network is there, « Mes classes » downloads in the background the sheet of every
   course of the teacher; without network, the sheet opens from this copy and the marks go to the device outbox (already
   replayed safely by the server). Per account and school (outbox scope); no token is ever stored. Best effort: a full or
   blocked storage only means the sheet needs the network. */
import {getGradeSheet, getMyTeaching, type GradeSheet, type MyTeaching} from './api';
import {outboxScope} from './offline/outbox';

const KEY = 'edusync.pedagogy.sheets.v1';
type Store = {scope: string; savedAt: string; mine?: MyTeaching; sheets: Record<string, {savedAt: string; sheet: GradeSheet}>};
const sheetKey = (classId: string, course: string) => `${classId}:${course}`;

function read(): Store | null {
  try {
    const raw = localStorage.getItem(KEY); if (!raw) return null;
    const s = JSON.parse(raw) as Store;
    return s.scope === outboxScope() ? s : null;              // another account on this phone: never shown
  } catch { return null; }
}
function write(s: Store) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage full or blocked */ } }
function base(): Store { return read() ?? {scope: outboxScope(), savedAt: new Date().toISOString(), sheets: {}}; }

export function cachedSheet(classId: string, course: string) { return read()?.sheets[sheetKey(classId, course)] ?? null; }
export function cachedMine() { const s = read(); return s?.mine ? {mine: s.mine, savedAt: s.savedAt} : null; }
export function rememberSheet(classId: string, course: string, sheet: GradeSheet) {
  const s = base(); s.sheets[sheetKey(classId, course)] = {savedAt: new Date().toISOString(), sheet}; write(s);
}
export function offlineReady(classId: string, course: string) { return !!cachedSheet(classId, course); }

/** Downloads every sheet of the teacher (current period), one after the other, without blocking the screen. */
export async function prefetchMine(token: string, onProgress?: (done: number, total: number) => void): Promise<MyTeaching> {
  const mine = await getMyTeaching(token);
  const s = base(); s.mine = mine; s.savedAt = new Date().toISOString(); write(s);
  const all = mine.classes.flatMap(c => c.courses.map(k => [c.class_id, k.course_code] as const));
  let done = 0;
  for (const [classId, course] of all) {
    if (navigator.onLine === false) break;
    try { rememberSheet(classId, course, await getGradeSheet(token, classId, course)); } catch { /* one sheet failed: the others go on */ }
    onProgress?.(++done, all.length);
  }
  return mine;
}
