// Settings parity pass 3 (2026-10-24) — copied from the Desktop golden master (app/ui/settings_page.py::_build_documents,
// _backup_now, _test_backup, _export_diagnostic; app/services/diagnostics.py), adapted to a shared Web server:
//  * Documents & signature: signatory name / title and « show the logo » printed on every PDF;
//  * Sauvegardes: the platform backs the whole server up every day (status shown here); the school can download a
//    verified copy of ITS OWN data and test it (SHA-256 of every file, row counts). Restoring is done by the platform;
//  * Diagnostic: versions and volumes only, never a pupil name, a phone number or an amount.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {
  BackupStatus, BackupTest, Diagnostic, DocumentSettings, Numbering,
  diagnosticReport, exportSchoolData, getBackupStatus, getDiagnostic, getDocumentSettings, getNumbering, putDocumentSettings, testSchoolData,
} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}
const when = (iso?: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {dateStyle: 'long', timeStyle: 'short'}) : '—';
const STATE: Record<string, [string, string]> = {OK: ['ok', 'À jour'], DEGRADED: ['warn', 'En retard'], DOWN: ['bad', 'En échec'], NOT_CONFIGURED: ['neutral', 'Non configurée sur ce serveur']};

export function DocumentSettingsPanel({token, can}: {token: string; can: (p: string) => boolean}) {
  const [d, setD] = useState<DocumentSettings | null>(null); const [name, setName] = useState(''); const [title, setTitle] = useState(''); const [logo, setLogo] = useState(true);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load() { try { const r = await getDocumentSettings(token); setD(r); setName(r.signatory_name ?? ''); setTitle(r.signatory_title ?? ''); setLogo(r.show_school_logo); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  const edit = can('settings.documents.manage');
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (title.trim() && !name.trim()) { setError('Indiquez aussi le nom du signataire, par exemple « Jean Kabeya ».'); return; }
    try { setBusy(true); setError(''); await putDocumentSettings(token, {signatory_name: name.trim() || null, signatory_title: title.trim() || null, show_school_logo: logo}); toast.success('Réglages des documents enregistrés'); await load(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <section className="panel">
    <div className="panelHead"><div><h3>Documents &amp; signature</h3><p>Ce qui figure sur les reçus et les rapports PDF. La devise de l’école se règle dans « École &amp; identité » ; le logo, le préfixe des reçus, le format et le nombre de copies dans le module Documents.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {d && <form className="benefitCard" onSubmit={save} noValidate><fieldset disabled={!edit || busy}>
      <legend>Signataire des documents</legend>
      <div className="benefitGrid">
        <FormField label="Nom du signataire"><input value={name} maxLength={120} placeholder="Ex. Jean Kabeya" onChange={e => setName(e.target.value)}/></FormField>
        <FormField label="Fonction"><input value={title} maxLength={120} placeholder="Ex. Préfet des études, Économe" onChange={e => setTitle(e.target.value)}/></FormField>
      </div>
      <label className="switchRow"><span>Afficher le logo de l’école<small>{logo ? 'Le logo apparaît en tête des reçus et des rapports' : 'Les documents sont imprimés sans logo'}</small></span><input type="checkbox" role="switch" checked={logo} onChange={e => setLogo(e.target.checked)}/></label>
      <p className="policyHint">Aperçu : {name.trim() ? <>« Signature et cachet » puis <b>{[name.trim(), title.trim()].filter(Boolean).join(' — ')}</b> en bas de chaque reçu et rapport.</> : 'sans signataire, seule la mention « Signature et cachet » des rapports reste.'}</p>
      {edit && <div className="formActions"><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>}
    </fieldset></form>}
  </section>;
}

export function NumberingCard({token}: {token: string}) {
  const [n, setN] = useState<Numbering | null>(null);
  useEffect(() => { getNumbering(token).then(setN).catch(() => setN(null)); }, [token]);
  if (!n) return null;
  return <section className="panel numberingCard"><div className="panelHead"><div><h3>Numérotation automatique</h3><p>Les prochains numéros attribués par EduSync. Ils sont donnés au moment de l’enregistrement ; personne ne les saisit à la main.</p></div></div>
    <dl className="numberingGrid"><div><dt>Prochain matricule élève</dt><dd>{n.student}</dd></div><div><dt>Prochain code famille</dt><dd>{n.family}</dd></div><div><dt>Prochain reçu</dt><dd>{n.receipt}</dd></div></dl>
  </section>;
}

export function MaintenanceSettings({token, can}: {token: string; can: (p: string) => boolean}) {
  const [status, setStatus] = useState<BackupStatus | null>(null); const [test, setTest] = useState<BackupTest | null>(null); const [diag, setDiag] = useState<Diagnostic | null>(null);
  const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  async function load() {
    // Each block loads on its own: a failure of one never hides the other.
    setError(''); const errs: string[] = [];
    await Promise.all([
      can('settings.backups.read') ? getBackupStatus(token).then(setStatus).catch(e => { errs.push(friendlyError(e)); }) : null,
      can('settings.diagnostics.read') ? getDiagnostic(token).then(setDiag).catch(e => { errs.push(friendlyError(e)); }) : null,
    ]);
    if (errs.length) setError(errs.join(' · '));
  }
  useEffect(() => { void load(); }, [token]);
  async function run(key: string, fn: () => Promise<void>) { try { setBusy(key); setError(''); await fn(); } catch (e) { setError(friendlyError(e)); } finally { setBusy(''); } }
  const copy = () => run('export', async () => { const r = await exportSchoolData(token); download(r.blob, r.filename); toast.success('Copie des données téléchargée et vérifiée'); await load(); });
  const check = () => run('test', async () => { const r = await testSchoolData(token); setTest(r); r.ok ? toast.success('Test réussi : copie complète et intacte') : toast.error('Le test a détecté un problème'); await load(); });
  const report = () => run('report', async () => { download(await diagnosticReport(token), `diagnostic_${new Date().toISOString().slice(0, 10)}.txt`); toast.success('Rapport de diagnostic téléchargé'); });
  const p = status?.platform; const [tone, label] = STATE[p?.state ?? 'NOT_CONFIGURED'] ?? STATE.NOT_CONFIGURED;
  return <section className="panel maintenance">
    <div className="panelHead"><div><h3>Sauvegardes &amp; diagnostic</h3><p>Les données de l’école sont sur le serveur EduSync, sauvegardé automatiquement chaque jour. Vous pouvez aussi garder votre propre copie, contrôlée, des données de l’école.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {status && <div className="benefitCard">
      <b>Sauvegarde automatique du serveur</b>
      <p className="mtLine"><em className={`status ${tone}`}>{label}</em> {p?.detail}{p?.finished_at ? ` · ${when(p.finished_at)}` : ''}</p>
      <p className="policyHint">{p?.restore_verified ? 'La dernière restauration d’essai a réussi. ' : ''}{p?.offsite ? 'Une copie est conservée hors du serveur. ' : ''}{status.restore}</p>
    </div>}
    {(can('settings.backups.create') || can('settings.backups.test')) && <div className="benefitCard">
      <b>Copie des données de l’école</b>
      <p className="policyHint">Une archive ZIP de toutes les données de l’école (élèves, familles, classes, frais, paiements…), chaque fichier contrôlé par son empreinte SHA-256. Elle contient des données personnelles : rangez-la dans un endroit sûr.</p>
      {status?.last_school_copy && <p className="mtLine">Dernière opération : {when(status.last_school_copy.created_at)}{status.last_school_copy.new_json?.total_rows !== undefined ? ` · ${status.last_school_copy.new_json.total_rows} ligne(s)` : ''}</p>}
      <div className="formActions">
        {can('settings.backups.test') && <button type="button" className="softBtn" disabled={!!busy} onClick={() => void check()}>{busy === 'test' ? 'Test en cours…' : 'Tester une copie'}</button>}
        {can('settings.backups.create') && <button type="button" className="primaryBtn" disabled={!!busy} onClick={() => void copy()}>{busy === 'export' ? 'Préparation…' : 'Sauvegarder maintenant'}</button>}
      </div>
      {test && <div className={test.ok ? 'mtOk' : 'error'} role="status">{test.ok
        ? `Test réussi : ${test.tables} tables, ${test.total_rows} lignes, toutes les empreintes vérifiées (${(test.size_bytes / 1024).toFixed(0)} Ko).`
        : `Problème détecté : ${test.problems.join(' ; ')}`}{test.skipped_tables.length > 0 && ` Tables non disponibles sur ce serveur : ${test.skipped_tables.length}.`}</div>}
    </div>}
    {diag && <div className="benefitCard">
      <b>Assistance technique</b>
      <dl className="numberingGrid"><div><dt>Version EduSync</dt><dd>{diag.app_version}</dd></div><div><dt>Version du schéma</dt><dd title={diag.schema_version ?? undefined}>{diag.schema_version ? diag.schema_version.split('_')[0] : 'indisponible'}</dd></div>
        <div><dt>Année</dt><dd>{diag.academic_year ? diag.academic_year.label : 'aucune'}</dd></div><div><dt>Paramétrage</dt><dd>{diag.readiness ? `${diag.readiness.percent} %` : '—'}</dd></div></dl>
      <ul className="mtVolumes">{diag.volumes.map(v => <li key={v.key}><span>{v.label}</span><b>{v.count ?? '—'}</b></li>)}</ul>
      <p className="policyHint">À transmettre au support en cas de problème : le rapport ne contient ni noms d’élèves, ni téléphones, ni montants.</p>
      {can('settings.diagnostics.export') && <div className="formActions"><button type="button" className="softBtn" disabled={!!busy} onClick={() => void report()}>{busy === 'report' ? 'Préparation…' : 'Exporter le diagnostic'}</button></div>}
    </div>}
  </section>;
}
