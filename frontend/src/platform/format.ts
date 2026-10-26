/** Display formatting shared by school screens. Amounts stay strings end to end (backend Decimal): no float rounding. */

const NBSP = ' ';

/** "1250000.50" + "CDF" → "1 250 000,50 FC". Never converts through Number, so large or precise amounts stay exact. */
/** What the user reads for a currency code: « FC » for CDF (internal code), the code otherwise. */
export function currencyLabel(code?: string | null): string { return code === 'CDF' ? 'FC' : (code ?? ''); }

export function formatMoney(value: string | number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === '') return '—';
  const raw = String(value).trim();
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(raw);
  if (!m) return currency ? `${raw} ${currency === 'CDF' ? 'FC' : currency}` : raw;
  const [, sign, int, dec] = m;
  const grouped = int.replace(/^0+(?=\d)/, '').replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  const cents = dec ? dec.replace(/0+$/, '') : '';
  const fraction = cents ? `,${cents.length === 1 ? `${cents}0` : cents}` : '';
  return `${sign}${grouped}${fraction}${currency ? ` ${currency === 'CDF' ? 'FC' : currency}` : ''}`;
}

/** ISO date "2026-09-01" → "01/09/2026" (calendar date, no time-zone shift). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

export const PERIODICITY_LABEL: Record<string, string> = {
  ONE_TIME: 'Paiement unique', MONTHLY: 'Mensuel', PERIODIC: 'Par période', OPTIONAL: 'Facultatif',
};

/** Next school year after the most recent one (Sept → June), e.g. "2027-2028". Only a suggestion: the school edits it. */
export function suggestNextYear(codes: string[], today = new Date()): {code: string; label: string; start_date: string; end_date: string} {
  const starts = codes.map(c => /^(\d{4})/.exec(c)?.[1]).filter(Boolean).map(Number);
  const base = starts.length ? Math.max(...starts) + 1 : (today.getMonth() >= 6 ? today.getFullYear() : today.getFullYear() - 1);
  const code = `${base}-${base + 1}`;
  return {code, label: code, start_date: `${base}-09-01`, end_date: `${base + 1}-06-30`};
}
