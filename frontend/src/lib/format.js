// Presentation-only formatting. Nothing here computes an analytic figure:
// shares come from the backend; pct() only renders a share (or n/d that the
// backend already returned as a pair) to text.

export const fmt = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("en-US"));

export function pct(share, digits = 2) {
  if (share === null || share === undefined || Number.isNaN(share)) return "—";
  return `${(share * 100).toFixed(digits)}%`;
}

// Render n/d for display where the backend gave both numbers but no share.
export function ratio(n, d, digits = 2) {
  if (!d) return "—";
  return pct(n / d, digits);
}

export function usd(v) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export const shortId = (id) => (id ? id.slice(0, 6).toUpperCase() : "");

export function dateOnly(iso) {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

export function dateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

export function bytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export const humanize = (s) => (s ? String(s).replace(/[_-]+/g, " ") : "");

export function kappaText(k) {
  if (k === null || k === undefined) return "undefined";
  return k.toFixed(3);
}
