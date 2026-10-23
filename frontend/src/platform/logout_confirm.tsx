// Confirmation of a VOLUNTARY sign-out (lot 2026-10). Shown only when the person clicks « Se déconnecter » in the
// account menu; an expired or revoked session is ended by the application without this dialog. One component for
// every role and every account menu (top bar, sidebar dock, phone drawer): the shell wraps the « logout » item.
import React, {useEffect, useId, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {NavGlyph} from './nav_icons';

export function LogoutConfirm({onConfirm, onCancel}: {onConfirm: () => unknown | Promise<unknown>; onCancel: () => void}) {
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const titleId = useId(), textId = useId();
  useEffect(() => { cancel.current?.focus(); }, []);
  async function confirm() {
    if (busy) return;                       // a double click never signs out twice
    setBusy(true);
    try { await onConfirm(); } catch { setBusy(false); }
  }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape' && !busy) { e.preventDefault(); onCancel(); return; }
    if (e.key !== 'Tab') return;            // focus trap: Tab / Shift+Tab stay inside the dialog
    const items = Array.from(box.current?.querySelectorAll<HTMLElement>('button:not([disabled])') || []);
    if (!items.length) { e.preventDefault(); return; }
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  return createPortal(<div className="es-stepup-layer">
    <div className="es-modal-backdrop" onMouseDown={e => { if (e.currentTarget === e.target && !busy) onCancel(); }}>
      <div className="es-modal es-logout" role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={textId} ref={box} onKeyDown={onKey}>
        <div className="es-logout-ico" aria-hidden="true"><NavGlyph g="logout" size={22}/></div>
        <h2 id={titleId}>Se déconnecter ?</h2>
        <p id={textId}>Voulez-vous vraiment vous déconnecter de votre session EduSync ?</p>
        <div className="es-modal-foot">
          <button ref={cancel} type="button" className="es-btn es-btn-ghost" onClick={onCancel} disabled={busy}>Annuler</button>
          <button type="button" className="es-btn es-btn-danger es-logout-go" onClick={() => void confirm()} disabled={busy} aria-busy={busy}>
            {busy ? <><i className="es-update-spin" aria-hidden="true"/>Déconnexion…</> : 'Se déconnecter'}</button>
        </div>
      </div>
    </div>
  </div>, document.body);
}

/** The element to give the focus back to after « Annuler »: the account button that opened the menu, or the phone
    menu button when the drawer closed. */
export function logoutOrigin(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[aria-haspopup="menu"][aria-expanded="true"], .es-drawer-acct[aria-expanded="true"]');
}
export function restoreFocus(origin: HTMLElement | null) {
  const target = origin && origin.isConnected ? origin : document.querySelector<HTMLElement>('.es-side-acct, .es-account-btn, [aria-label="Ouvrir le menu"]');
  target?.focus();
}
