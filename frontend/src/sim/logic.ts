/** Pure Simulation Studio helpers (unit-tested). They shape inputs and results; no climate numbers are made here. */

export type Params = Record<string, string | number>;

export function queryString(p: Params): string {
  const u = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => u.set(k, String(v)));
  return u.toString();
}

export function simUrl(tool: string, p: Params, format: "json" | "csv" = "json"): string {
  return `/api/sim/${tool}?${queryString(format === "csv" ? { ...p, format: "csv" } : p)}`;
}

/** Clamp to a control's range and snap to its step, so typed values can never leave the allowed domain. */
export function clampStep(v: number, min: number, max: number, step: number): number {
  if (!Number.isFinite(v)) return min;
  const snapped = Math.round((v - min) / step) * step + min;
  return Math.min(max, Math.max(min, Number(snapped.toFixed(6))));
}

/** Equal-width histogram of numeric values (Plotly's basic bundle has no histogram trace). */
export function histogram(values: number[], nBins = 20): { centers: number[]; counts: number[]; width: number } {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return { centers: [], counts: [], width: 0 };
  let lo = Math.min(...v);
  let hi = Math.max(...v);
  if (lo === hi) {
    lo -= 0.5;
    hi += 0.5;
  }
  const w = (hi - lo) / nBins;
  const counts = new Array(nBins).fill(0);
  v.forEach((x) => {
    const i = Math.min(nBins - 1, Math.floor((x - lo) / w));
    counts[i] += 1;
  });
  return { centers: counts.map((_, i) => lo + w * (i + 0.5)), counts, width: w };
}

/** Shared bin edges so baseline and scenario histograms are directly comparable. */
export function pairedHistogram(a: number[], b: number[], nBins = 20) {
  const all = [...a, ...b].filter((x) => Number.isFinite(x));
  if (!all.length) return { centers: [], a: [], b: [], width: 0 };
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (lo === hi) {
    lo -= 0.5;
    hi += 0.5;
  }
  const w = (hi - lo) / nBins;
  const bin = (xs: number[]) => {
    const c = new Array(nBins).fill(0);
    xs.filter((x) => Number.isFinite(x)).forEach((x) => (c[Math.min(nBins - 1, Math.floor((x - lo) / w))] += 1));
    return c;
  };
  return { centers: Array.from({ length: nBins }, (_, i) => lo + w * (i + 0.5)), a: bin(a), b: bin(b), width: w };
}

/** Sequential colour for matrix cells: dark navy -> cyan, by position of v within [min, max]. */
export function rampColor(v: number, min: number, max: number): string {
  const t = max > min ? Math.min(1, Math.max(0, (v - min) / (max - min))) : 0.5;
  const from = [13, 33, 58]; // #0D213A
  const to = [34, 211, 238]; // #22D3EE
  const c = from.map((f, i) => Math.round(f + (to[i] - f) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** Readable text on a ramp colour (dark text on light cyan, light text on navy). */
export function rampText(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0.5;
  return t > 0.55 ? "#05111E" : "#E6F0FA";
}

export function fmt(v: number | null | undefined, digits = 1, unit = ""): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  return `${v.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

export function fmtSigned(v: number | null | undefined, digits = 1, unit = ""): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const s = v.toFixed(digits);
  return `${v > 0 ? "+" : ""}${s}${unit ? ` ${unit}` : ""}`;
}

/** Local storage of saved configurations. Never throws: storage can be blocked (private mode, previews). */
export interface SavedConfig {
  name: string;
  tool: string;
  params: Params;
  savedAt: string;
}

const KEY = "earthsignal.sim.saved.v1";

export function loadSaved(storage: Pick<Storage, "getItem"> | undefined = safeStorage()): SavedConfig[] {
  try {
    const raw = storage?.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => x && typeof x.name === "string" && x.params) : [];
  } catch {
    return [];
  }
}

export function saveConfig(cfg: SavedConfig, storage: Pick<Storage, "getItem" | "setItem"> | undefined = safeStorage()): boolean {
  try {
    const list = loadSaved(storage).filter((x) => !(x.tool === cfg.tool && x.name === cfg.name));
    list.unshift(cfg);
    storage?.setItem(KEY, JSON.stringify(list.slice(0, 50)));
    return !!storage;
  } catch {
    return false;
  }
}

export function deleteConfig(tool: string, name: string, storage: Pick<Storage, "getItem" | "setItem"> | undefined = safeStorage()): void {
  try {
    storage?.setItem(KEY, JSON.stringify(loadSaved(storage).filter((x) => !(x.tool === tool && x.name === name))));
  } catch {
    /* storage unavailable: nothing to delete */
  }
}

function safeStorage(): Storage | undefined {
  try {
    return typeof window !== "undefined" ? window.localStorage : undefined;
  } catch {
    return undefined;
  }
}
