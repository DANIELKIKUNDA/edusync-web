// Dates are typed and read « JJ/MM/AAAA », whatever the browser language (owner report 2026-11-06: Edge in English
// showed « mm/dd/yyyy » on the birth date). The value exchanged with the code stays ISO « AAAA-MM-JJ », exactly like a
// native date input: a hidden native input carries it, so react-hook-form `register`, `value`/`onChange(e.target.value)`,
// `min`/`max` and the browser calendar keep working unchanged.
import React, {forwardRef, useCallback, useImperativeHandle, useLayoutEffect, useRef, useState} from 'react';
import {NavGlyph} from './nav_icons';
import './date_input.css';

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** « 2015-03-04 » → « 04/03/2015 » (empty when the value is not a full ISO date). */
export function isoToFrench(iso: string | undefined | null): string {
  const m = ISO.exec(iso ?? '');
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
}

/** Keeps only digits and inserts the slashes while typing: « 0403 » → « 04/03 », « 04032015 » → « 04/03/2015 ». */
export function maskFrenchDate(raw: string): string {
  const iso = ISO.exec(raw.trim());
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;  // pasted or filled in ISO
  const parts = raw.split(/[^\d]+/).filter(Boolean);
  if (parts.length >= 2 && parts.length <= 3 && parts[0].length <= 2 && parts[1].length <= 2) {  // « 4/3/2015 », « 4.3.15 »
    const [d, m, y = ''] = parts;
    return [d.padStart(2, '0'), m.padStart(2, '0'), y.slice(0, 4)].filter((x, i) => i < 2 || x).join('/');
  }
  return guidedDigits(raw.replace(/\D/g, '')).text;
}

/** Owner report 2026-11-08: the day and the month are checked while typing. « 2 » as a month means February (« 02 »);
 *  a digit that would give month 13–19 or day 32–39 is refused on the spot, with the reason, instead of a date that
 *  is accepted now and refused later. */
export function guidedDigits(input: string): {text: string; hint: string} {
  let day = '', month = '', year = '', hint = '';
  for (const ch of input) {
    if (day.length < 2) {
      if (day === '' && ch > '3') day = '0' + ch;
      else if (day === '3' && ch > '1') { hint = 'Le jour va de 01 à 31.'; }
      else if (day === '0' && ch === '0') { hint = 'Le jour commence à 01.'; }
      else day += ch;
    } else if (month.length < 2) {
      if (month === '' && ch > '1') month = '0' + ch;
      else if (month === '1' && ch > '2') { hint = 'Le mois va de 01 à 12 : pour février, écrivez 02.'; }
      else if (month === '0' && ch === '0') { hint = 'Le mois commence à 01 (janvier).'; }
      else month += ch;
    } else if (year.length < 4) year += ch;
  }
  return {text: [day, month, year].filter(Boolean).join('/'), hint};
}

/** « 04/03/2015 » → « 2015-03-04 »; '' when incomplete; null when complete but impossible (31/02, 00/13…). */
export function frenchToIso(text: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
  if (!m) return '';
  const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (y < 1900 || y > 2100 || dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return `${m[3]}-${m[2]}-${m[1]}`;
}

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>;

export const DateInput = forwardRef<HTMLInputElement, Props>(function DateInput(props, ref) {
  const {value, defaultValue, onChange, onBlur, name, min, max, disabled, required, id, className, placeholder, style, autoFocus, ...rest} = props;
  const native = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => native.current as HTMLInputElement);
  const controlled = value !== undefined;
  const [text, setText] = useState(() => isoToFrench(String(value ?? defaultValue ?? '')));
  const [problem, setProblem] = useState('');
  const editing = useRef(false);
  const known = useRef(String(value ?? defaultValue ?? ''));  // the last ISO value the text reflects

  // The ISO value may change from outside (form reset, preset, calendar): the text then follows it.
  useLayoutEffect(() => {
    const iso = controlled ? String(value ?? '') : native.current?.value ?? '';
    if (iso === known.current) return;
    known.current = iso;
    if (!editing.current) { setText(isoToFrench(iso)); setProblem(''); }
  });

  const emit = useCallback((iso: string) => {
    const el = native.current;
    known.current = iso;
    if (!el || el.value === iso) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(el, iso);
    el.dispatchEvent(new Event('input', {bubbles: true}));  // React onChange (register or controlled) receives e.target.value = ISO
  }, []);

  function outOfRange(iso: string) {
    if (min && iso < String(min)) return `Date trop ancienne : au plus tôt le ${isoToFrench(String(min))}.`;
    if (max && iso > String(max)) return `Date trop tardive : au plus tard le ${isoToFrench(String(max))}.`;
    return '';
  }

  function onType(raw: string) {
    editing.current = true;
    const shown = maskFrenchDate(raw);
    setText(shown);
    const guided = /^[\d/]*$/.test(raw) ? guidedDigits(raw.replace(/\D/g, '')).hint : '';
    if (guided) { setProblem(guided); return; }
    const iso = frenchToIso(shown);
    if (iso === null) { setProblem('Cette date n’existe pas : vérifiez le jour et le mois.'); return; }
    if (iso) { const p = outOfRange(iso); setProblem(p); if (!p) emit(iso); return; }
    setProblem('');
    if (shown === '') emit('');
  }

  function finish(e: React.FocusEvent<HTMLInputElement>) {
    editing.current = false;
    if (text && frenchToIso(text) === '') setProblem('Date incomplète : écrivez JJ/MM/AAAA, par exemple 04/03/2015.');
    onBlur?.({...e, target: native.current as HTMLInputElement, currentTarget: native.current as HTMLInputElement} as React.FocusEvent<HTMLInputElement>);
  }

  function openCalendar() {
    const el = native.current as (HTMLInputElement & {showPicker?: () => void}) | null;
    try { el?.showPicker?.(); } catch { el?.focus(); }
  }

  return <span className={`dateInput ${problem ? 'invalid' : ''} ${className ?? ''}`} style={style}><span className="dateInputBox">
    <input {...rest} id={id} type="text" inputMode="numeric" autoComplete="off" autoFocus={autoFocus} disabled={disabled} required={required}
      placeholder={placeholder ?? 'JJ/MM/AAAA'} maxLength={10} value={text} aria-invalid={problem ? true : undefined}
      onChange={e => onType(e.target.value)} onBlur={finish}/>
    <button type="button" className="dateInputCal" aria-label="Ouvrir le calendrier" tabIndex={-1} disabled={disabled} onClick={openCalendar}>
      <NavGlyph g="calendar" size={16}/></button>
    <input ref={native} className="dateInputNative" type="date" tabIndex={-1} aria-hidden="true" name={name} min={min} max={max} disabled={disabled}
      {...(controlled ? {value: String(value ?? '')} : {defaultValue: defaultValue as string | undefined})}
      onChange={e => { if (!editing.current) { known.current = e.target.value; setText(isoToFrench(e.target.value)); setProblem(''); } onChange?.(e); }}/></span>
    {problem && <small className="dateInputProblem" role="alert">{problem}</small>}
  </span>;
});
