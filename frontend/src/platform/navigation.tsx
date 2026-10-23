import React, {useEffect, useRef, useState} from 'react';
import {NavGlyph} from './nav_icons';
import './navigation.css';

export type Crumb = {label: string; onSelect: () => void};

const UUID_RX = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;

/** The page label alone: no « EduSync », no « Gestion scolaire », no technical id, short. */
export function pageLabel(label: string) {
  const clean = (label || '')
    .replace(UUID_RX, '')
    .replace(/\bEduSync\b/gi, '')
    .replace(/\bGestion scolaire\b/gi, '')
    .replace(/\s*[·—–|-]\s*(?=[·—–|-]|$)/g, '')
    .replace(/^\s*[·—–|-]\s*/, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
  const short = clean.length > 60 ? `${clean.slice(0, 59).trimEnd()}…` : clean;
  return short || 'Plateforme';
}

/** Browser tab: « Push — EduSync ». One single global rule (the shell applies it), the same for every role. */
export function pageTitle(label: string) {
  return `${pageLabel(label)} — EduSync`;
}

/** Installed application (PWA): the browser already writes the application name « EduSync » in the title bar, so
    the page gives its label only — never « EduSync … — EduSync ». */
export function isStandalone(): boolean {
  try { return window.matchMedia('(display-mode: standalone)').matches || window.matchMedia('(display-mode: window-controls-overlay)').matches
    || Boolean((navigator as Navigator & {standalone?: boolean}).standalone); } catch { return false; }
}
export function windowTitle(label: string) {
  return isStandalone() ? pageLabel(label) : pageTitle(label);
}

/** Parents come from the authorized screen that rendered the detail, never from
 * an untrusted URL or history length. The same component serves every role. */
export function PageTrail({parents, current}: {parents: Crumb[]; current: string}) {
  const parent = parents.at(-1);
  if (!parent) return null;
  return <nav className="pf-trail" aria-label="Fil d’Ariane" data-page-title={current}>
    <div className="pf-trail-desktop">{parents.map((p, i) => <React.Fragment key={`${i}:${p.label}`}>
      <button type="button" onClick={p.onSelect} title={p.label}>{p.label}</button><span aria-hidden="true">›</span>
    </React.Fragment>)}<span aria-current="page" title={current}>{current}</span></div>
    <div className="pf-trail-mobile"><button type="button" className="pf-back" aria-label={`Retour : ${parent.label}`} onClick={parent.onSelect}>
      <NavGlyph g="chevronLeft" size={22}/></button><strong title={current}>{current}</strong></div>
  </nav>;
}

export function scrollPosition(y: number, height: number, viewport: number) {
  return {long: height > viewport * 1.6, started: y > 80, bottom: height - viewport - y < Math.max(140, viewport * .18)};
}

/** One control for the platform shell, with a reserved safe-area position. */
export function VerticalNavigation() {
  const [position, setPosition] = useState({long: false, started: false, bottom: false});
  const [active, setActive] = useState(false);
  const [obstructed, setObstructed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      setPosition(scrollPosition(window.scrollY, document.documentElement.scrollHeight, window.innerHeight));
      // Do not cover a business action, even when it sits in the safe-area slot.
      const r = button.current?.getBoundingClientRect();
      setObstructed(!!r && Array.from(document.querySelectorAll<HTMLElement>('button,a,input,select,textarea,[role="button"]')).some(el => {
        if (el === button.current || button.current?.contains(el)) return false;
        const b = el.getBoundingClientRect();
        return b.width > 0 && b.height > 0 && b.left < r.right && b.right > r.left && b.top < r.bottom && b.bottom > r.top;
      }));
    };
    const update = () => {if (!frame) frame = requestAnimationFrame(measure);};
    const interact = () => {setActive(true); clearTimeout(timer.current); timer.current = setTimeout(() => {if(document.activeElement!==button.current)setActive(false)}, 3500); update();};
    const observer = new ResizeObserver(update); observer.observe(document.body);
    window.addEventListener('scroll', interact, {passive: true}); window.addEventListener('resize', update);
    window.addEventListener('touchstart', interact, {passive: true}); window.addEventListener('keydown', interact);
    update();
    return () => {observer.disconnect(); cancelAnimationFrame(frame); clearTimeout(timer.current); window.removeEventListener('scroll', interact); window.removeEventListener('resize', update); window.removeEventListener('touchstart', interact); window.removeEventListener('keydown', interact);};
  }, []);
  const visible = position.long && position.started && active && !obstructed;
  return <button ref={button} type="button" className={`pf-vertical ${position.bottom ? 'pf-up' : ''}`} data-visible={visible}
    aria-label={position.bottom ? 'Revenir en haut de la page' : 'Aller en bas de la page'} aria-hidden={!visible} tabIndex={visible ? 0 : -1}
    onFocus={() => {setActive(true); clearTimeout(timer.current);}}
    onBlur={() => {timer.current = setTimeout(() => setActive(false), 3500);}}
    onClick={() => window.scrollTo({top: position.bottom ? 0 : document.documentElement.scrollHeight, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})}>
    <NavGlyph g="chevronDown" size={22}/>
  </button>;
}
