// Class choice in one compact field (owner report 2026-11-06: the chips of every class made the enrollment form grow
// with the size of the school). Closed, it looks like a select; open, it offers a search, the sections and the classes
// grouped by level. On a phone it opens as a bottom sheet. Keyboard: ↑ ↓ to move, Entrée to choose, Échap to close.
import React, {useEffect, useId, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import type {SchoolClass} from './api';
import {NavGlyph} from './platform/nav_icons';
import './class_select.css';

/** RDC reference levels, used when the school's catalogue gives no label (never a raw code such as « H1 » on screen). */
const LEVELS: Record<string, string> = {M1: '1re maternelle', M2: '2e maternelle', M3: '3e maternelle', P1: '1re primaire', P2: '2e primaire',
  P3: '3e primaire', P4: '4e primaire', P5: '5e primaire', P6: '6e primaire', S7: '7e EB', S8: '8e EB', H1: '1re Humanités',
  H2: '2e Humanités', H3: '3e Humanités', H4: '4e Humanités'};

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const compact = (s: string) => fold(s).replace(/[^a-z0-9]/g, '');

type Section = {id: string; label: string};
function sectionsOf(classes: SchoolClass[]): Section[] {
  const seen = new Map<string, string>();
  for (const c of classes) if (!seen.has(c.section_id)) seen.set(c.section_id, (c as any).section_label ?? 'Section');
  return [...seen].map(([id, label]) => ({id, label}));
}

export function levelName(c: SchoolClass, levelLabels: Record<string, string> = {}): string {
  const code = String(c.reference_code ?? '').toUpperCase();
  return levelLabels[code] ?? LEVELS[code] ?? (code || 'Autres classes');
}

/** Accent- and space-insensitive search over the class, its level, option and section: « 1hp », « scientif », « 7e b ». */
export function matchesClass(c: SchoolClass, query: string, levelLabels: Record<string, string> = {}): boolean {
  const q = fold(query).trim();
  if (!q) return true;
  const hay = [c.label, levelName(c, levelLabels), (c as any).option_label ?? '', (c as any).section_label ?? ''].join(' ');
  const bare = (x: string) => compact(fold(x).replace(/(\d+)(re|ere|er|e)\b/g, '$1'));  // « 1re HP » ≈ « 1hp »
  return q.split(/\s+/).every(w => fold(hay).includes(w)) || compact(hay).includes(compact(q)) || bare(hay).includes(bare(q));
}

export function ClassSelect({classes, value, onChange, invalid, suggested, levelLabels = {}, placeholder = 'Choisir la classe…', id, ariaLabel = 'Classe'}: {
  classes: SchoolClass[]; value: string; onChange: (id: string) => void; invalid?: boolean; suggested?: string; levelLabels?: Record<string, string>;
  placeholder?: string; id?: string; ariaLabel?: string}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [section, setSection] = useState('');
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState<React.CSSProperties>({});
  const panel = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const listId = useId();
  const secs = useMemo(() => sectionsOf(classes), [classes]);
  const current = classes.find(c => c.id === value);

  const shown = useMemo(() => classes.filter(c => (!section || c.section_id === section) && matchesClass(c, q, levelLabels)), [classes, section, q, levelLabels]);
  // Groups in the school's order: section, then level (the classes arrive sorted by the server). A level title is shown
  // only when it tells something the class names do not (« 1re Humanités » above « 1re HP, 1re HSC… »).
  const groups = useMemo(() => {
    const out: {key: string; section: string; title: string; showTitle: boolean; items: SchoolClass[]}[] = [];
    for (const c of shown) {
      const title = levelName(c, levelLabels);
      const key = `${c.section_id}|${title}`;
      const g = out.find(x => x.key === key);
      if (g) g.items.push(c); else out.push({key, section: c.section_id, title, showTitle: false, items: [c]});
    }
    for (const g of out) g.showTitle = !g.items.every(c => fold(c.label).startsWith(fold(g.title)));
    return out;
  }, [shown, levelLabels]);
  const sectionTitles = secs.length > 1 && !section;
  const flat = groups.flatMap(g => g.items);

  useEffect(() => {
    if (!open) return;
    const i = flat.findIndex(c => c.id === value);
    setActive(i >= 0 ? i : 0);
    const t = window.setTimeout(() => search.current?.focus(), 30);
    const away = (e: MouseEvent | TouchEvent) => { const t = e.target as Node; if (!root.current?.contains(t) && !panel.current?.contains(t)) close(false); };
    document.addEventListener('mousedown', away); document.addEventListener('touchstart', away);
    return () => { window.clearTimeout(t); document.removeEventListener('mousedown', away); document.removeEventListener('touchstart', away); };
  }, [open]);
  // Desktop: the list floats above the form (portal), under the field or above it when the room below is too short;
  // it follows the field when the form scrolls. On a phone the CSS turns it into a bottom sheet.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = trigger.current?.getBoundingClientRect();
      if (!r) return;
      const below = window.innerHeight - r.bottom - 12, above = r.top - 12;
      const up = below < 300 && above > below;
      const maxHeight = Math.max(200, Math.min(420, up ? above : below));
      setPos(up ? {left: r.left, width: r.width, bottom: window.innerHeight - r.top + 6, maxHeight} : {left: r.left, width: r.width, top: r.bottom + 6, maxHeight});
    };
    place();
    window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
  }, [open]);
  useEffect(() => { setActive(0); }, [q, section]);
  useEffect(() => { list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({block: 'nearest'}); }, [active, open]);

  function close(focusTrigger = true) { setOpen(false); setQ(''); if (focusTrigger) trigger.current?.focus(); }
  function choose(c: SchoolClass) { onChange(c.id); close(); }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, flat.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (flat[active]) choose(flat[active]); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
  }

  let index = -1;
  return <div className={`cs ${open ? 'open' : ''}`} ref={root}>
    <button type="button" id={id} ref={trigger} className={`cs-trigger ${invalid ? 'invalid' : ''} ${current ? '' : 'cs-unset'}`} aria-haspopup="listbox"
      aria-expanded={open} aria-label={current ? `${ariaLabel} : ${current.label}` : ariaLabel} onClick={() => open ? close() : setOpen(true)}
      onKeyDown={e => { if (!open && (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setOpen(true); } }}>
      {current ? <span className="cs-value"><b>{current.label}</b><small>{(current as any).section_label ?? levelName(current, levelLabels)}</small></span>
        : <span className="cs-placeholder">{placeholder}</span>}
      <NavGlyph g="chevronDown" size={16}/>
    </button>
    {open && createPortal(<>
      <div className="cs-backdrop" aria-hidden="true" onClick={e => { e.preventDefault(); close(false); }}/>
      <div ref={panel} className="cs-panel" style={pos} role="dialog" aria-label="Choisir la classe" onKeyDown={onKey}
        onClick={e => { if (!(e.target as HTMLElement).closest('button')) e.preventDefault(); }}>
        <div className="cs-sheetHead"><b>Choisir la classe</b><button type="button" aria-label="Fermer" onClick={() => close()}><NavGlyph g="close" size={18}/></button></div>
        <div className="cs-search"><NavGlyph g="search" size={16}/>
          <input ref={search} value={q} onChange={e => setQ(e.target.value)} placeholder="Rechercher : 1re, HP, Scientifique, B…" aria-label="Rechercher une classe"
            role="combobox" aria-expanded="true" aria-controls={listId} aria-activedescendant={flat[active] ? `${listId}-${flat[active].id}` : undefined}/>
          {q && <button type="button" className="cs-clear" aria-label="Effacer la recherche" onClick={() => { setQ(''); search.current?.focus(); }}>×</button>}
        </div>
        {secs.length > 1 && <div className="cs-sections" role="tablist" aria-label="Section">
          <button type="button" role="tab" aria-selected={!section} className={!section ? 'on' : ''} onClick={() => setSection('')}>Toutes<small>{classes.length}</small></button>
          {secs.map(s => <button key={s.id} type="button" role="tab" aria-selected={section === s.id} className={section === s.id ? 'on' : ''}
            onClick={() => setSection(s.id)}>{s.label}<small>{classes.filter(c => c.section_id === s.id).length}</small></button>)}
        </div>}
        <div className="cs-list" role="listbox" id={listId} ref={list} aria-label="Classes">
          {groups.map((g, gi) => <div key={g.key} className="cs-group" role="group" aria-label={g.title}>
            {sectionTitles && g.section !== groups[gi - 1]?.section && <div className="cs-sectionTitle">{secs.find(x => x.id === g.section)?.label}</div>}
            {g.showTitle && <div className="cs-groupTitle">{g.title}</div>}
            {g.items.map(c => { index += 1; const i = index; const chosen = c.id === value; const count = (c as any).student_count;
              return <div key={c.id} id={`${listId}-${c.id}`} role="option" aria-selected={chosen} data-index={i}
                className={`cs-option ${i === active ? 'active' : ''} ${chosen ? 'chosen' : ''}`}
                onMouseEnter={() => setActive(i)} onMouseDown={e => e.preventDefault()} onClick={() => choose(c)}>
                <span className="cs-optLabel">{c.label}{suggested === c.id && <em>proposée</em>}</span>
                {typeof count === 'number' && <small>{count} élève{count > 1 ? 's' : ''}</small>}
                {chosen && <NavGlyph g="check" size={16}/>}
              </div>; })}
          </div>)}
          {flat.length === 0 && <p className="cs-empty">Aucune classe ne correspond à « {q} ».</p>}
        </div>
      </div>
    </>, document.body)}
  </div>;
}
