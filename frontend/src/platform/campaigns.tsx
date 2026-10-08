import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {
  campaignList, campaignSend, platformRbacRoles, platformSchoolDetail, platformSchoolsPage, teamRoles, teamUsers,
  type Campaign, type CampaignTarget,
} from '../api';
import {Modal} from './account';
import {friendlyError} from './errors';
import {NavGlyph} from './nav_icons';
import './campaigns.css';

const TARGETS: {value: CampaignTarget['type']; label: string; hint: string; team?: boolean}[] = [
  {value: 'ALL_ACTIVE_SCHOOLS', label: 'Toutes les écoles actives', hint: 'Chaque membre actif de chaque école active'},
  {value: 'SCHOOLS', label: 'Écoles choisies', hint: 'Les membres actifs des écoles sélectionnées'},
  {value: 'SCHOOL_ROLE', label: 'Un rôle école', hint: 'Ex. : tous les caissiers (toutes écoles ou écoles choisies)'},
  {value: 'SCHOOL_USER', label: 'Un membre d’une école', hint: 'Une personne précise dans une école'},
  {value: 'PLATFORM_ALL', label: 'Toute l’équipe plateforme', hint: 'Comptes Atelier Pro actifs', team: true},
  {value: 'PLATFORM_ROLE', label: 'Un rôle plateforme', hint: 'Ex. : Support niveau 1', team: true},
  {value: 'PLATFORM_USER', label: 'Un membre de l’équipe', hint: 'Un compte Atelier Pro précis', team: true},
];
const SEV: Record<string, string> = {INFO: 'Information', WARNING: 'Avertissement', CRITICAL: 'Critique'};
const SCOPE_LABEL: Record<string, string> = Object.fromEntries(TARGETS.map(t => [t.value, t.label]).concat([['SCHOOL', 'Une école']]));

function Composer({token, canTeam, onClose, onSent}: {token: string; canTeam: boolean; onClose: () => void; onSent: () => void}) {
  const [type, setType] = useState<CampaignTarget['type']>('ALL_ACTIVE_SCHOOLS');
  const [title, setTitle] = useState(''); const [body, setBody] = useState(''); const [severity, setSeverity] = useState('INFO');
  const [link, setLink] = useState(''); const [expires, setExpires] = useState('');
  const [schools, setSchools] = useState<any[]>([]); const [picked, setPicked] = useState<string[]>([]);
  const [schoolRoles, setSchoolRoles] = useState<any[]>([]); const [platformRoles, setPlatformRoles] = useState<any[]>([]);
  const [members, setMembers] = useState<any[]>([]); const [teamList, setTeamList] = useState<any[]>([]);
  const [role, setRole] = useState(''); const [userId, setUserId] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [key] = useState(() => crypto.randomUUID());  // one key per composition: a double click or a lost response never sends twice
  useEffect(() => {
    platformSchoolsPage(token, '', 'ACTIVE', 0).then(r => setSchools(r.items)).catch(() => setSchools([]));
    platformRbacRoles(token).then(setSchoolRoles).catch(() => setSchoolRoles([]));
    if (canTeam) { teamRoles(token).then(r => setPlatformRoles(r.items.filter(x => x.status === 'ACTIVE'))).catch(() => {}); teamUsers(token).then(r => setTeamList(r.items.filter(x => x.platform_status === 'ACTIVE' && x.roles.length))).catch(() => {}); }
  }, [token]);
  useEffect(() => { setMembers([]); setUserId(''); if (type === 'SCHOOL_USER' && picked[0]) platformSchoolDetail(token, picked[0]).then(d => setMembers((d.users || []).filter((u: any) => u.membership_active))).catch(() => setMembers([])); }, [type, picked[0]]);
  const toggle = (id: string) => setPicked(p => type === 'SCHOOL_USER' ? [id] : p.includes(id) ? p.filter(x => x !== id) : [...p, id]);
  async function send(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (title.trim().length < 2 || body.trim().length < 2) { setError('Le titre et le message sont obligatoires.'); return; }
    if (link && !/^\/[A-Za-z0-9/_?=&.-]*$/.test(link)) { setError('Le lien doit être un chemin interne commençant par « / ».'); return; }
    const target: CampaignTarget = {type, school_ids: ['SCHOOLS', 'SCHOOL_ROLE', 'SCHOOL_USER'].includes(type) ? picked : [], role_code: ['SCHOOL_ROLE', 'PLATFORM_ROLE'].includes(type) ? role || null : null, user_id: ['SCHOOL_USER', 'PLATFORM_USER'].includes(type) ? userId || null : null};
    try {
      setBusy(true);
      const r = await campaignSend(token, key, {title: title.trim(), body: body.trim(), severity, target, link_path: link || null, expires_at: expires ? new Date(expires + 'T23:59:59').toISOString() : null});
      toast.success(`Notification remise à ${r.recipient_count} destinataire(s)${r.push ? ` · push : ${r.push.accepted}/${r.push.devices} appareil(s)` : ''}. Aucun SMS n’est envoyé.`);
      onSent();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  const def = TARGETS.find(t => t.value === type)!;
  return <Modal title="Nouvelle notification" subtitle="Notification interne à l’application. Aucun SMS ni WhatsApp n’est envoyé." onClose={onClose} wide>
    <form className="es-form cp-form" onSubmit={send} noValidate>
      <fieldset className="cp-targets"><legend>Destinataires</legend>
        {TARGETS.filter(t => !t.team || canTeam).map(t => <label key={t.value} className={type === t.value ? 'cp-on' : ''}>
          <input type="radio" name="target" checked={type === t.value} onChange={() => { setType(t.value); setPicked([]); setRole(''); setUserId(''); }}/>
          <span><b>{t.label}</b><small>{t.hint}</small></span></label>)}
      </fieldset>
      {['SCHOOLS', 'SCHOOL_ROLE', 'SCHOOL_USER'].includes(type) && <fieldset className="cp-schools"><legend>{type === 'SCHOOL_USER' ? 'École' : type === 'SCHOOL_ROLE' ? 'Limiter à ces écoles (facultatif)' : 'Écoles'}</legend>
        {schools.length === 0 ? <p className="es-hint">Aucune école active.</p> : schools.map(s => <label key={s.id}>
          <input type={type === 'SCHOOL_USER' ? 'radio' : 'checkbox'} name="school" checked={picked.includes(s.id)} onChange={() => toggle(s.id)}/>{s.name} <small>{s.code}</small></label>)}
      </fieldset>}
      {type === 'SCHOOL_ROLE' && <label className="cp-field"><span>Rôle école *</span><select value={role} onChange={e => setRole(e.target.value)}><option value="">Choisir…</option>{schoolRoles.map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select></label>}
      {type === 'PLATFORM_ROLE' && <label className="cp-field"><span>Rôle plateforme *</span><select value={role} onChange={e => setRole(e.target.value)}><option value="">Choisir…</option>{platformRoles.map(r => <option key={r.code} value={r.code}>{r.label}</option>)}</select></label>}
      {type === 'SCHOOL_USER' && picked[0] && <label className="cp-field"><span>Membre *</span><select value={userId} onChange={e => setUserId(e.target.value)}><option value="">Choisir…</option>{members.map(m => <option key={m.user_id} value={m.user_id}>{m.full_name} · {m.email}</option>)}</select></label>}
      {type === 'PLATFORM_USER' && <label className="cp-field"><span>Membre de l’équipe *</span><select value={userId} onChange={e => setUserId(e.target.value)}><option value="">Choisir…</option>{teamList.map(u => <option key={u.id} value={u.id}>{u.full_name} · {u.email}</option>)}</select></label>}
      <div className="cp-grid">
        <label className="cp-field"><span>Titre *</span><input value={title} onChange={e => setTitle(e.target.value)} maxLength={180}/></label>
        <label className="cp-field"><span>Gravité</span><select value={severity} onChange={e => setSeverity(e.target.value)}>{Object.entries(SEV).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      </div>
      <label className="cp-field"><span>Message *</span><textarea rows={5} value={body} onChange={e => setBody(e.target.value)} maxLength={2000}/></label>
      <div className="cp-grid">
        <label className="cp-field"><span>Lien interne (facultatif)</span><input value={link} onChange={e => setLink(e.target.value)} placeholder="/aide/paiements"/></label>
        <label className="cp-field"><span>Expire le (facultatif)</span><input type="date" value={expires} min={new Date().toISOString().slice(0, 10)} onChange={e => setExpires(e.target.value)}/></label>
      </div>
      <p className="es-hint"><NavGlyph g="info" size={12}/> {def.hint}. Un destinataire ne reçoit jamais deux fois la même notification ; l’envoi est tracé dans l’audit.</p>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><button className="es-btn es-btn-primary" disabled={busy}>{busy ? 'Envoi…' : 'Envoyer la notification'}</button></div>
    </form>
  </Modal>;
}

export function CampaignsPanel({token, canTeam}: {token: string; canTeam: boolean}) {
  const [items, setItems] = useState<Campaign[] | null>(null); const [more, setMore] = useState(false); const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false); const [error, setError] = useState('');
  async function load(off = 0) { try { setError(''); const r = await campaignList(token, off); setItems(prev => off && prev ? [...prev, ...r.items] : r.items); setMore(r.has_more); setOffset(off); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(0); }, [token]);
  return <div className="cp">
    <div className="cp-bar"><p className="es-hint">Notifications internes ciblées, lues dans la cloche de chaque destinataire.</p><button className="es-btn es-btn-primary" onClick={() => setOpen(true)}><NavGlyph g="plus" size={16}/>Nouvelle notification</button></div>
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {items === null ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> : items.length === 0 ? <div className="es-empty">Aucune notification envoyée.</div> :
      <ul className="cp-list">{items.map(c => { const pct = c.recipient_count ? Math.round(100 * c.read_count / c.recipient_count) : 0; return <li key={c.id}>
        <div className="cp-main"><b>{c.title}</b><small>{SCOPE_LABEL[c.target_scope] || c.target_scope}{c.target_school_code ? ` · ${c.target_school_code}` : ''} · {SEV[c.severity]} · {new Date(c.created_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'short'})}{c.author ? ` · ${c.author}` : ''}</small></div>
        <div className="cp-read" aria-label={`${c.read_count} lue(s) sur ${c.recipient_count}`}><span><b>{c.read_count}</b>/{c.recipient_count} lue(s)</span><i><em style={{width: `${pct}%`}}/></i></div>
      </li>; })}</ul>}
    {more && <button className="es-btn es-btn-ghost" onClick={() => void load(offset + 30)}>Charger plus</button>}
    {open && <Composer token={token} canTeam={canTeam} onClose={() => setOpen(false)} onSent={() => { setOpen(false); void load(0); }}/>}
  </div>;
}
