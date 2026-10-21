import React, {useEffect, useId, useRef, useState} from 'react';
import {NavGlyph} from './nav_icons';
import {pageTitle, VerticalNavigation} from './navigation';
import {connectivityLabel, getConnectivity, subscribeActivity, subscribeConnectivity, type ConnectivityState, type WriteActivity} from './connectivity';
import './shell.css';
import './theme.css';
import {announceIfJustUpdated, applyUpdate, shortBuild, useUpdateNotice} from './updates';

export type ShellNavItem = {key: string; label: string; icon: string; active: boolean; onSelect: () => void; primary?: boolean; shortLabel?: string};
export type ShellMenuItem = {key: string; label: string; icon: string; onSelect: () => void; danger?: boolean};
export type ShellAccount = {name: string; email?: string; context?: string; detail?: string; role?: string; avatarUrl?: string; items: ShellMenuItem[]};

const COLLAPSED_KEY = 'edusync.shell.collapsed';
function readCollapsed() { try { return localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { return false; } }
function writeCollapsed(v: boolean) { try { localStorage.setItem(COLLAPSED_KEY, v ? '1' : '0'); } catch { /* préférence locale facultative */ } }

export function initialsOf(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase() || 'U';
}

/** Profile photo when the account has one, initials otherwise (also while the photo loads or if it fails). */
export function Avatar({name, url, className = ''}: {name: string; url?: string; className?: string}) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [url]);
  return <span className={`es-avatar ${className} ${url && !broken ? 'es-avatar-photo' : ''}`} aria-hidden="true">
    {url && !broken ? <img src={url} alt="" draggable={false} onError={() => setBroken(true)}/> : initialsOf(name)}</span>;
}

function useDismiss(open: boolean, close: () => void, ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close(); };
    window.addEventListener('keydown', onKey); window.addEventListener('mousedown', onDown);
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onDown); };
  }, [open, close, ref]);
}

/* Connection + write activity, in words a school user understands. */
export function StatusChip({compact = false}: {compact?: boolean}) {
  const [state, setState] = useState<ConnectivityState>(getConnectivity().state);
  const [act, setAct] = useState<WriteActivity>({pending: 0, retrying: false, last: 'none', at: 0});
  const [, tick] = useState(0);
  useEffect(() => subscribeConnectivity(s => setState(s.state)), []);
  useEffect(() => subscribeActivity(a => { setAct(a); window.setTimeout(() => tick(x => x + 1), 4200); }), []);
  const recentOk = act.last === 'ok' && Date.now() - act.at < 4000;
  const recentFail = act.last === 'failed' && Date.now() - act.at < 60000;
  let tone = 'ok', icon = 'wifi', label = 'En ligne', detail = 'Connexion au serveur EduSync active.';
  if (state === 'OFFLINE') { tone = 'bad'; icon = 'wifiOff'; label = 'Hors ligne'; detail = 'Pas de connexion au serveur. Les enregistrements reprendront quand la connexion reviendra ; rien n’est envoyé en attendant.'; }
  else if (state === 'SUSPECTED_OFFLINE' || state === 'DEGRADED') { tone = 'warn'; icon = 'wifi'; label = connectivityLabel(state); detail = 'Le réseau répond mal. EduSync réessaie automatiquement les opérations sûres.'; }
  else if (state === 'RECOVERING') { tone = 'warn'; icon = 'sync'; label = 'Reconnexion…'; detail = 'La connexion revient, vérification en cours.'; }
  if (act.pending > 0) { tone = act.retrying ? 'warn' : 'busy'; icon = act.retrying ? 'sync' : 'cloudUp'; label = act.retrying ? 'Nouvel essai d’envoi…' : 'Enregistrement…'; detail = `${act.pending} opération(s) en cours d’envoi au serveur.`; }
  else if (recentFail) { tone = 'bad'; icon = 'alert'; label = 'Envoi non confirmé'; detail = 'La dernière opération n’a pas pu être confirmée par le serveur. Réessayez : EduSync empêche les doublons.'; }
  else if (recentOk) { tone = 'ok'; icon = 'checkCircle'; label = 'Enregistré'; detail = 'La dernière opération a été enregistrée sur le serveur.'; }
  return <span className={`es-status es-${tone} ${compact ? 'es-status-compact' : ''}`} role="status" aria-live="polite" title={detail}>
    <NavGlyph g={icon} size={15}/><span className={compact ? 'es-sr' : ''}>{label}</span>
  </span>;
}

export function AccountMenu({account}: {account: ShellAccount}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useDismiss(open, () => setOpen(false), ref);
  const initials = initialsOf(account.name);
  return <div className="es-account" ref={ref}>
    <button className="es-account-btn" aria-haspopup="menu" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen(x => !x)} title={account.name}>
      <Avatar name={account.name} url={account.avatarUrl}/>
      <span className="es-account-name">{account.name.split(/\s+/)[0]}</span>
      <NavGlyph g="chevronDown" size={14}/>
    </button>
    {open && <div className="es-menu" id={menuId} role="menu" aria-label="Compte">
      <div className="es-menu-head">
        <Avatar name={account.name} url={account.avatarUrl} className="es-avatar-lg"/>
        <div><b>{account.name}</b>{account.email && <small>{account.email}</small>}{account.context && <em>{account.context}</em>}{account.detail && <small>{account.detail}</small>}</div>
      </div>
      {account.items.map(item => <button key={item.key} role="menuitem" className={item.danger ? 'es-danger' : ''} onClick={() => { setOpen(false); item.onSelect(); }}>
        <NavGlyph g={item.icon} size={17}/><span>{item.label}</span>
      </button>)}
    </div>}
  </div>;
}

/* New version available: message + "Mettre à jour" in the top bar (compact on phones). */
export function UpdateChip({bar = false}: {bar?: boolean}) {
  const u = useUpdateNotice();
  if (!u.available) return null;
  return <div className={bar ? 'es-update es-update-bar' : 'es-update es-update-chip'} role="status" aria-live="polite">
    <span className="es-update-text"><NavGlyph g="sparkles" size={15}/><span>Nouvelle version disponible</span></span>
    <button type="button" className="es-update-btn" onClick={() => void applyUpdate()} disabled={u.updating}
      title={u.build ? `Version ${shortBuild(u.build)}` : undefined} aria-label={u.updating ? 'Mise à jour en cours' : 'Mettre à jour EduSync vers la nouvelle version'}>
      {u.updating ? <><i className="es-update-spin" aria-hidden="true"/>Mise à jour…</> : <><NavGlyph g="download" size={15}/><span className="es-update-label">Mettre à jour</span></>}
    </button>
  </div>;
}

/* Compact account block docked at the bottom of the sidebar (platform space): avatar, name, role, chevron.
   The account menu opens only on demand, upward (or to the right of the collapsed rail). */
function SideAccount({account}: {account: ShellAccount}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useDismiss(open, () => setOpen(false), ref);
  useEffect(() => { if (open) ref.current?.querySelector<HTMLElement>('[role=menuitem]')?.focus(); }, [open]);
  const onMenuKey = (e: React.KeyboardEvent) => {
    const items = Array.from(ref.current?.querySelectorAll<HTMLElement>('[role=menuitem]') || []);
    const i = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length]?.focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
    if (e.key === 'Escape') { setOpen(false); ref.current?.querySelector<HTMLElement>('.es-side-acct')?.focus(); }
  };
  return <div className="es-side-account" ref={ref}>
    {open && <div className="es-menu es-menu-up" id={menuId} role="menu" aria-label="Compte" onKeyDown={onMenuKey}>
      <div className="es-menu-head"><Avatar name={account.name} url={account.avatarUrl} className="es-avatar-lg"/>
        <div><b>{account.name}</b>{account.email && <small>{account.email}</small>}{account.context && <em>{account.context}</em>}</div></div>
      {account.items.map(item => <button key={item.key} role="menuitem" className={item.danger ? 'es-danger' : ''} onClick={() => { setOpen(false); item.onSelect(); }}>
        <NavGlyph g={item.icon} size={17}/><span>{item.label}</span></button>)}
    </div>}
    <button type="button" className="es-side-acct" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      aria-label={`Compte : ${account.name}${account.role ? `, ${account.role}` : ''}. Ouvrir le menu du compte`} title={account.name} onClick={() => setOpen(x => !x)}>
      <Avatar name={account.name} url={account.avatarUrl}/>
      <span className="es-side-acct-text"><b>{account.name}</b>{account.role && <small>{account.role}</small>}</span>
      <NavGlyph g="chevronDown" size={16}/>
    </button>
  </div>;
}

/* Phone menu: the same compact block; touching it unfolds the account actions in place (no tiny desktop menu). */
function DrawerAccount({account, onPick}: {account: ShellAccount; onPick: (item: ShellMenuItem) => void}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  return <div className="es-drawer-account es-drawer-account-compact">
    <button type="button" className="es-drawer-acct" aria-expanded={open} aria-controls={listId} onClick={() => setOpen(x => !x)}>
      <Avatar name={account.name} url={account.avatarUrl} className="es-avatar-lg"/>
      <span className="es-side-acct-text"><b>{account.name}</b>{account.role && <small>{account.role}</small>}</span>
      <span className={`es-drawer-acct-chev ${open ? 'es-open' : ''}`} aria-hidden="true"><NavGlyph g="chevronDown" size={18}/></span>
    </button>
    <div id={listId} className="es-drawer-acct-list" hidden={!open}>
      {account.email && <p className="es-drawer-acct-mail">{account.email}</p>}
      {account.items.map(item => <button key={item.key} type="button" className={item.danger ? 'es-danger' : ''} onClick={() => onPick(item)}>
        <NavGlyph g={item.icon} size={18}/><span>{item.label}</span></button>)}
    </div>
  </div>;
}

export function AppShell({orgLabel, orgCode, nav, title, context, tools, drawerTools, account, children, mobileTitle, accountDock = false}: {
  orgLabel: string; orgCode?: string; nav: ShellNavItem[]; title: string; context?: string; tools?: React.ReactNode; drawerTools?: React.ReactNode;
  account: ShellAccount; children: React.ReactNode; mobileTitle?: string;
  /** Platform space: compact account block at the bottom of the sidebar / phone menu instead of the top bar. */
  accountDock?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawer, setDrawer] = useState(false);
  const [tip, setTip] = useState<{label: string; top: number} | null>(null);
  const drawerRef = useRef<HTMLElement>(null);
  useDismiss(drawer, () => setDrawer(false), drawerRef);
  useEffect(() => {
    const updateTitle=()=>{
      const trails=Array.from(document.querySelectorAll<HTMLElement>('#es-content .pf-trail[data-page-title]'));
      const current=trails.filter(el=>!el.closest('[hidden]')).at(-1)?.dataset.pageTitle;
      document.title=pageTitle(current||title);
    };
    const content=document.getElementById('es-content');
    const observer=new MutationObserver(updateTitle);
    if(content)observer.observe(content,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden','data-page-title']});
    updateTitle();return()=>observer.disconnect();
  }, [title]);
  useEffect(() => { announceIfJustUpdated(); }, []);
  function toggle() { setCollapsed(v => { writeCollapsed(!v); return !v; }); setTip(null); setPeek(false); }
  const railOnly = () => collapsed || window.matchMedia('(min-width:768px) and (max-width:1100px)').matches;
  // Rail: the full menu shows temporarily over the content (mouse after a short delay, or keyboard focus); "Épingler" keeps it open.
  const [peek, setPeek] = useState(false);
  const peekTimer = useRef<number | undefined>(undefined);
  const finePointer = () => window.matchMedia('(hover:hover) and (pointer:fine)').matches;
  const schedulePeek = (open: boolean, delay: number) => { window.clearTimeout(peekTimer.current); peekTimer.current = window.setTimeout(() => { const next = open && railOnly(); setPeek(next); if (next) setTip(null); }, delay); };
  const sideHandlers = {
    onMouseEnter: () => { if (finePointer() && railOnly()) schedulePeek(true, 280); },
    onMouseLeave: () => schedulePeek(false, 180),
    onFocus: (e: React.FocusEvent) => { if (railOnly() && e.target.matches(':focus-visible')) { window.clearTimeout(peekTimer.current); setPeek(true); setTip(null); } },
    onBlur: (e: React.FocusEvent<HTMLElement>) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) schedulePeek(false, 0); },
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Escape' && peek) { setPeek(false); (document.activeElement as HTMLElement | null)?.blur(); } },
  };
  useEffect(() => () => window.clearTimeout(peekTimer.current), []);
  // The phone drawer never survives a switch to the desktop layout (rotation, window resize).
  useEffect(() => {
    const mq = window.matchMedia('(min-width:768px)');
    const onChange = () => { if (mq.matches) setDrawer(false); else setPeek(false); };
    mq.addEventListener('change', onChange); return () => mq.removeEventListener('change', onChange);
  }, []);
  const showTip = (label: string) => (e: React.MouseEvent | React.FocusEvent) => {
    if (!railOnly() || peek) return;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTip({label, top: r.top + r.height / 2});
  };
  const primary = nav.filter(n => n.primary).slice(0, 4);
  const go = (n: ShellNavItem) => { n.onSelect(); setDrawer(false); };
  const collapseLabel = collapsed ? (peek ? 'Épingler le menu' : 'Déployer le menu') : 'Réduire le menu';
  return <div className={`es-shell ${collapsed ? 'es-collapsed' : ''} ${accountDock ? 'es-dock' : ''}`}>
    <a className="es-skip" href="#es-content">Aller au contenu</a>
    <aside className={`es-side ${peek ? 'es-peek' : ''}`} aria-label="Navigation principale" {...sideHandlers}>
      <div className="es-brand">
        <img src="/icons/edusync-mark.svg" alt="" width={32} height={32}/>
        <span className="es-brand-text"><b>EduSync</b><small title={orgLabel}>{orgLabel}</small></span>
        <button type="button" className="es-collapse" onClick={toggle} aria-label={collapseLabel} aria-expanded={!collapsed || peek} title={collapseLabel}
          onMouseEnter={showTip(collapseLabel)} onMouseLeave={() => setTip(null)}>
          <NavGlyph g={collapsed && peek ? 'pin' : 'panelLeft'} size={17}/>
        </button>
      </div>
      <nav className="es-nav">
        {nav.map(n => <button key={n.key} className={n.active ? 'es-active' : ''} aria-current={n.active ? 'page' : undefined}
          aria-label={n.label} onClick={() => { n.onSelect(); setPeek(false); }}
          onMouseEnter={showTip(n.label)} onMouseLeave={() => setTip(null)} onFocus={showTip(n.label)} onBlur={() => setTip(null)}>
          <NavGlyph g={n.icon} size={19}/><span className="es-nav-label">{n.label}</span>
        </button>)}
      </nav>
      {accountDock && <SideAccount account={account}/>}
    </aside>
    {tip && <div className="es-tip" role="tooltip" style={{top: tip.top}}>{tip.label}</div>}
    <div className="es-main">
      <header className="es-top">
        <button className="es-burger" aria-label="Ouvrir le menu" aria-expanded={drawer} onClick={() => setDrawer(true)}><NavGlyph g="menu" size={21}/></button>
        <div className="es-title"><h1>{title}</h1>{context && <p>{context}</p>}</div>
        <div className="es-tools"><UpdateChip/>{tools}{!accountDock && <AccountMenu account={account}/>}</div>
      </header>
      <UpdateChip bar/>
      <main className="es-content" id="es-content" tabIndex={-1}>{children}</main>
      {accountDock && <VerticalNavigation/>}
    </div>
    <nav className="es-bottom" aria-label="Navigation rapide">
      {primary.map(n => <button key={n.key} className={n.active ? 'es-active' : ''} aria-current={n.active ? 'page' : undefined} onClick={n.onSelect}>
        <NavGlyph g={n.icon} size={21}/><small>{n.shortLabel || n.label}</small>
      </button>)}
      <button className={!primary.some(n => n.active) ? 'es-active' : ''} onClick={() => setDrawer(true)} aria-label="Tous les modules"><NavGlyph g="menu" size={21}/><small>Menu</small></button>
    </nav>
    {drawer && <div className="es-drawer-backdrop">
      <aside className="es-drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-label="Menu EduSync">
        <div className="es-drawer-head">
          <img src="/icons/edusync-mark.svg" alt="" width={30} height={30}/>
          <div><b>{mobileTitle || orgLabel}</b>{orgCode && <small>{orgCode}</small>}</div>
          <button aria-label="Fermer le menu" onClick={() => setDrawer(false)}><NavGlyph g="close" size={20}/></button>
        </div>
        <div className="es-drawer-status"><StatusChip/>{drawerTools}</div>
        <nav className="es-drawer-nav">
          {nav.map(n => <button key={n.key} className={n.active ? 'es-active' : ''} aria-current={n.active ? 'page' : undefined} onClick={() => go(n)}>
            <NavGlyph g={n.icon} size={20}/><span>{n.label}</span>
          </button>)}
        </nav>
        {accountDock ? <DrawerAccount account={account} onPick={item => { setDrawer(false); item.onSelect(); }}/> : <div className="es-drawer-account">
          <div className="es-menu-head"><Avatar name={account.name} url={account.avatarUrl} className="es-avatar-lg"/>
            <div><b>{account.name}</b>{account.email && <small>{account.email}</small>}{account.context && <em>{account.context}</em>}</div></div>
          {account.items.map(item => <button key={item.key} className={item.danger ? 'es-danger' : ''} onClick={() => { setDrawer(false); item.onSelect(); }}>
            <NavGlyph g={item.icon} size={18}/><span>{item.label}</span>
          </button>)}
        </div>}
      </aside>
    </div>}
  </div>;
}
