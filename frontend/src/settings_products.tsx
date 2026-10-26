// Articles scolaires (administrator finishing pass 2026-10-24) — a real stock catalogue: unit sale price, opening stock,
// low-stock alert, traced receipts and counted corrections (inventory_stock_movements, same capabilities as the
// Intendance stock). A sale is recorded by the cash desk only and lowers the stock there; nothing here can sell.
import React, {useMemo, useState} from 'react';
import {toast} from 'sonner';
import {SettingsProduct, createSettingsProduct, moveProductStock, updateSettingsProduct} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {formatMoney} from './platform/format';
import {NavGlyph} from './platform/nav_icons';
import {autoCode, PRODUCT_PRESETS} from './settings_wizards';

const qty = (v?: string) => Number(v ?? 0);
const fmtQty = (v?: string) => qty(v).toLocaleString('fr-FR', {maximumFractionDigits: 3});
const decimalOk = (v: string, places = 2) => new RegExp(`^\\d+([.,]\\d{1,${places}})?$`).test(v.trim());
const norm = (v: string) => v.trim().replace(/\s/g, '').replace(',', '.');
/** Exact price × quantity in cents (project rule: money never goes through floats). */
function scaled(v: string, places: number): bigint { const [i, f = ''] = String(v || '0').split('.'); return BigInt(i || '0') * 10n ** BigInt(places) + BigInt((f + '0'.repeat(places)).slice(0, places) || '0'); }
export function lineValue(price: string, quantity: string): bigint { return (scaled(price, 2) * scaled(quantity, 3) + 500n) / 1000n; }
const centsText = (c: bigint) => `${c / 100n}.${String(c % 100n).padStart(2, '0')}`;

export function stockState(p: SettingsProduct): {tone: 'ok' | 'warn' | 'bad' | 'neutral'; label: string} {
  if (!p.stock_tracking) return {tone: 'neutral', label: 'Stock non suivi'};
  if (qty(p.quantity) <= 0) return {tone: 'bad', label: 'Rupture'};
  if (qty(p.low_threshold) > 0 && qty(p.quantity) <= qty(p.low_threshold)) return {tone: 'warn', label: 'Stock bas'};
  return {tone: 'ok', label: 'En stock'};
}

export function ProductsSettings({token, items, can, onDone}: {token: string; items: SettingsProduct[]; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const manage = can('settings.products.manage');
  const [adding, setAdding] = useState(false); const [preset, setPreset] = useState('');
  const [filter, setFilter] = useState<'all' | 'alert'>('all');
  const alerts = items.filter(p => p.enabled && ['bad', 'warn'].includes(stockState(p).tone));
  const shown = filter === 'alert' ? alerts : items;
  const value = useMemo(() => {
    const m = new Map<string, bigint>();
    for (const p of items) if (p.enabled && p.stock_tracking) m.set(p.currency, (m.get(p.currency) ?? 0n) + lineValue(p.unit_price, p.quantity ?? '0'));
    return [...m.entries()];
  }, [items]);
  return <section className="panel productsPanel">
    <div className="panelHead"><div><h3>Articles scolaires</h3><p>Catalogue vendu à la caisse : prix de vente unitaire, quantité en stock et seuil d’alerte. Chaque entrée de stock est tracée ; la caisse retire le stock à chaque vente.</p></div>
      {manage && !adding && <button className="primaryBtn" onClick={() => { setPreset(''); setAdding(true); }}>Nouvel article</button>}</div>
    <div className="productKpis">
      <div><span><NavGlyph g="box" size={18}/></span><b>{items.filter(p => p.enabled).length}</b><small>article(s) actif(s)</small></div>
      <button type="button" className={alerts.length ? 'alert' : ''} onClick={() => setFilter(f => f === 'alert' ? 'all' : 'alert')} aria-pressed={filter === 'alert'}>
        <span><NavGlyph g="alert" size={18}/></span><b>{alerts.length}</b><small>{filter === 'alert' ? 'alertes affichées · tout voir' : 'en rupture ou stock bas'}</small></button>
      <div><span><NavGlyph g="finance" size={18}/></span><b>{value.length ? value.map(([c, v]) => formatMoney(centsText(v), c)).join(' · ') : '—'}</b><small>valeur du stock au prix de vente</small></div>
    </div>
    {manage && !adding && items.length < 30 && <div className="sw-chips sw-presets">{PRODUCT_PRESETS.filter(p => !items.some(x => x.label.toLowerCase() === p.label.toLowerCase())).map(p =>
      <button key={p.label} type="button" className="sw-chip" onClick={() => { setPreset(p.label); setAdding(true); }}>+ {p.label}</button>)}</div>}
    {adding && <ProductForm token={token} items={items} preset={preset} onCancel={() => setAdding(false)} onSaved={async () => { setAdding(false); await onDone(); }}/>}
    {items.length === 0 && !adding && <div className="emptyGuide"><b>Aucun article</b><p>Ajoutez les articles vendus par l’école (uniforme, pull, journal de classe…) avec leur prix et leur stock de départ.</p></div>}
    <div className="productGrid">{shown.map(p => <ProductCard key={p.id} token={token} p={p} can={can} onDone={onDone}/>)}</div>
  </section>;
}

function ProductForm({token, items, preset, onCancel, onSaved}: {token: string; items: SettingsProduct[]; preset: string; onCancel: () => void; onSaved: () => Promise<void>}) {
  const [label, setLabel] = useState(preset); const [price, setPrice] = useState(''); const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF');
  const [tracking, setTracking] = useState(true); const [opening, setOpening] = useState(''); const [low, setLow] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (label.trim().length < 2) { setError('Indiquez le nom de l’article, par exemple « Uniforme scolaire ».'); return; }
    if (items.some(x => x.label.toLowerCase() === label.trim().toLowerCase())) { setError('Un article porte déjà ce nom.'); return; }
    if (!decimalOk(price) || Number(norm(price)) <= 0) { setError('Prix de vente unitaire : un nombre supérieur à zéro (ex. 15000).'); return; }
    if (tracking && opening.trim() && !decimalOk(opening, 3)) { setError('Stock de départ : un nombre (ex. 120).'); return; }
    if (tracking && low.trim() && !decimalOk(low, 3)) { setError('Seuil d’alerte : un nombre (ex. 10).'); return; }
    try {
      setBusy(true);
      await createSettingsProduct(token, {code: autoCode(label, items.map(x => x.code)), label: label.trim(), currency, unit_price: norm(price), stock_tracking: tracking,
        opening_quantity: tracking && opening.trim() ? norm(opening) : '0', low_threshold: tracking && low.trim() ? norm(low) : '0'});
      toast.success(tracking && Number(norm(opening || '0')) > 0 ? `Article créé avec ${norm(opening)} en stock` : 'Article créé'); await onSaved();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="benefitCard productForm" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <fieldset disabled={busy}><legend>Nouvel article</legend>
      <div className="benefitGrid">
        <FormField label="Article *"><input value={label} maxLength={160} autoFocus placeholder="Ex. Uniforme scolaire" onChange={e => setLabel(e.target.value)}/></FormField>
        <FormField label="Prix de vente unitaire *"><div className="moneyInput"><input inputMode="decimal" value={price} placeholder="0" onChange={e => setPrice(e.target.value)}/>
          <select aria-label="Devise" value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option value="CDF">FC</option><option>USD</option></select></div></FormField>
      </div>
      <label className="switchRow"><span>Suivre le stock<small>{tracking ? 'La caisse refuse une vente si le stock est épuisé' : 'Article vendu sans contrôle de quantité (service, commande)'}</small></span><input type="checkbox" role="switch" checked={tracking} onChange={e => setTracking(e.target.checked)}/></label>
      {tracking && <div className="benefitGrid">
        <FormField label="Stock de départ" hint="Quantité réellement disponible aujourd’hui (enregistrée comme entrée « Stock initial »)."><input inputMode="decimal" value={opening} placeholder="0" onChange={e => setOpening(e.target.value)}/></FormField>
        <FormField label="Seuil d’alerte" hint="En dessous, l’article est signalé « Stock bas »."><input inputMode="decimal" value={low} placeholder="0" onChange={e => setLow(e.target.value)}/></FormField>
      </div>}
      <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Créer l’article'}</button></div>
    </fieldset>
  </form>;
}

function ProductCard({token, p, can, onDone}: {token: string; p: SettingsProduct; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const [panel, setPanel] = useState<'' | 'edit' | 'receipt' | 'adjust'>('');
  const st = stockState(p);
  const canReceive = can('inventory.stock.receive') && p.stock_tracking && p.enabled;
  const canAdjust = can('inventory.stock.adjust') && p.stock_tracking && p.enabled;
  const manage = can('settings.products.manage');
  return <article className={`productCard ${p.enabled ? '' : 'muted'}`}>
    <button type="button" className="productMain" onClick={() => setPanel(x => x ? '' : manage ? 'edit' : canReceive ? 'receipt' : '')} aria-expanded={!!panel}>
      <span className="productIcon" aria-hidden="true"><NavGlyph g="cart" size={20}/></span>
      <span className="productText"><b>{p.label}</b><small>{formatMoney(p.unit_price, p.currency)} l’unité</small></span>
      <span className="productStock"><b>{p.stock_tracking ? fmtQty(p.quantity) : '—'}</b><em className={`pill tone-${st.tone}`}>{p.enabled ? st.label : 'Inactif'}</em></span>
    </button>
    {p.stock_tracking && qty(p.low_threshold) > 0 && <small className="productHint">Alerte sous {fmtQty(p.low_threshold)}</small>}
    {p.stock_tracking && p.enabled && !canReceive && qty(p.quantity) <= qty(p.low_threshold) && <small className="productHint">Les entrées de stock sont enregistrées par l’Intendance (rôle Intendant).</small>}
    {(manage || canReceive || canAdjust) && <div className="productActions">
      {manage && <button type="button" className={panel === 'edit' ? 'on' : ''} onClick={() => setPanel(x => x === 'edit' ? '' : 'edit')}>Prix & réglages</button>}
      {canReceive && <button type="button" className={panel === 'receipt' ? 'on' : ''} onClick={() => setPanel(x => x === 'receipt' ? '' : 'receipt')}>+ Entrée de stock</button>}
      {canAdjust && <button type="button" className={panel === 'adjust' ? 'on' : ''} onClick={() => setPanel(x => x === 'adjust' ? '' : 'adjust')}>Correction</button>}
    </div>}
    {panel === 'edit' && <EditPanel token={token} p={p} can={can} onDone={async () => { setPanel(''); await onDone(); }}/>}
    {(panel === 'receipt' || panel === 'adjust') && <StockPanel token={token} p={p} kind={panel} onDone={async () => { setPanel(''); await onDone(); }}/>}
  </article>;
}

function EditPanel({token, p, can, onDone}: {token: string; p: SettingsProduct; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const [price, setPrice] = useState(p.unit_price.replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1')); const [low, setLow] = useState(String(qty(p.low_threshold)));
  const [tracking, setTracking] = useState(p.stock_tracking); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function save(enabled: boolean) {
    setError('');
    if (!decimalOk(price) || Number(norm(price)) <= 0) { setError('Prix : un nombre supérieur à zéro.'); return; }
    if (tracking && !decimalOk(low || '0', 3)) { setError('Seuil d’alerte : un nombre.'); return; }
    try { setBusy(true); await updateSettingsProduct(token, p, {label: p.label, currency: p.currency, unit_price: norm(price), stock_tracking: tracking, enabled, low_threshold: tracking ? norm(low || '0') : null});
      toast.success(enabled === p.enabled ? 'Article mis à jour' : enabled ? 'Article réactivé' : 'Article désactivé : il n’est plus proposé à la caisse'); await onDone(); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <div className="productPanel">
    {error && <div className="error" role="alert">{error}</div>}
    <div className="benefitGrid">
      <FormField label={`Prix de vente unitaire (${p.currency})`}><input inputMode="decimal" value={price} onChange={e => setPrice(e.target.value)}/></FormField>
      {tracking && <FormField label="Seuil d’alerte"><input inputMode="decimal" value={low} onChange={e => setLow(e.target.value)}/></FormField>}
    </div>
    <label className="checkField"><input type="checkbox" checked={tracking} onChange={e => setTracking(e.target.checked)}/> Suivre le stock</label>
    <p className="policyHint">Un nouveau prix s’applique aux prochaines ventes ; les reçus déjà émis gardent leur prix.</p>
    <div className="formActions">
      {(p.enabled ? can('settings.products.activate') || can('settings.products.manage') : can('settings.products.manage')) &&
        <button type="button" className="ghost" disabled={busy} onClick={() => void save(!p.enabled)}>{p.enabled ? 'Désactiver' : 'Réactiver'}</button>}
      <button type="button" className="primaryBtn" disabled={busy} onClick={() => void save(p.enabled)}>{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>
  </div>;
}

function StockPanel({token, p, kind, onDone}: {token: string; p: SettingsProduct; kind: 'receipt' | 'adjust'; onDone: () => Promise<void>}) {
  const [q, setQ] = useState(''); const [dir, setDir] = useState<'INCREASE' | 'DECREASE'>('DECREASE');
  const [reason, setReason] = useState(kind === 'receipt' ? 'Livraison du fournisseur' : ''); const [ref, setRef] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const after = q && decimalOk(q, 3) ? qty(p.quantity) + (kind === 'receipt' || dir === 'INCREASE' ? 1 : -1) * Number(norm(q)) : null;
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError('');
    if (!decimalOk(q, 3) || Number(norm(q)) <= 0) { setError('Quantité : un nombre supérieur à zéro.'); return; }
    if (reason.trim().length < 3) { setError(kind === 'receipt' ? 'Indiquez l’origine de l’entrée (livraison, don…).' : 'Indiquez le motif de la correction (inventaire, article abîmé…).'); return; }
    if (after !== null && after < 0) { setError(`Impossible : seulement ${fmtQty(p.quantity)} en stock.`); return; }
    try { setBusy(true);
      const r = await moveProductStock(token, p.id, {movement_type: kind === 'receipt' ? 'RECEIPT' : 'ADJUSTMENT', quantity: norm(q), adjustment_direction: kind === 'adjust' ? dir : null, reason: reason.trim(), reference: ref.trim() || null});
      toast.success(`${p.label} : ${fmtQty(r.quantity)} en stock`); await onDone(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="productPanel" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="benefitGrid">
      {kind === 'adjust' && <FormField label="Sens"><select value={dir} onChange={e => setDir(e.target.value as 'INCREASE' | 'DECREASE')}><option value="DECREASE">Retirer (perte, casse, écart d’inventaire)</option><option value="INCREASE">Ajouter (écart d’inventaire)</option></select></FormField>}
      <FormField label="Quantité *"><input inputMode="decimal" value={q} autoFocus onChange={e => setQ(e.target.value)}/></FormField>
      <FormField label="Motif *"><input value={reason} maxLength={240} onChange={e => setReason(e.target.value)}/></FormField>
      {kind === 'receipt' && <FormField label="Référence (facultatif)"><input value={ref} maxLength={96} placeholder="Bon de livraison, facture…" onChange={e => setRef(e.target.value)}/></FormField>}
    </div>
    <p className="policyHint">Stock actuel : <b>{fmtQty(p.quantity)}</b>{after !== null && after >= 0 && <> → après l’opération : <b>{after.toLocaleString('fr-FR', {maximumFractionDigits: 3})}</b></>}. Le mouvement est tracé (auteur, date, motif).</p>
    <div className="formActions"><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : kind === 'receipt' ? 'Enregistrer l’entrée' : 'Enregistrer la correction'}</button></div>
  </form>;
}
