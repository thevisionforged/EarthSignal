/** Pure helpers for the Anticipate (forecast) view. Arithmetic on returned numbers only; unit-tested. */

export interface ForecastDay {
  date: string;
  lead_days: number;
  forecast: number;
  low: number;
  high: number;
  climatology: number;
  method: string;
}

export interface LeadResult {
  lead_days: number;
  chosen: string;
  passes: boolean;
  band_coverage_dev: number;
  holdout: {
    n: number;
    rmse: { chosen: number; baseline: number; climatology: number };
    mae: { chosen: number; baseline: number };
    bias_chosen: number;
    skill_vs_baseline: number;
    skill_vs_climatology: number;
    mse_improvement_p05: number;
  };
}

/** Local calendar date as YYYY-MM-DD (the user's "today"). */
export function isoToday(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

/** Forecast days split into those already past (awaiting NASA data) and those still ahead. */
export function splitByToday(days: ForecastDay[], today: string): { past: ForecastDay[]; future: ForecastDay[] } {
  return { past: days.filter((d) => d.date < today), future: days.filter((d) => d.date >= today) };
}

export function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN;
}

/** Average forecast and average departure from the usual (seasonal) value over a set of days. */
export function weekSummary(days: ForecastDay[]): { forecast: number; usual: number; diff: number } | null {
  if (!days.length) return null;
  const f = mean(days.map((d) => d.forecast));
  const u = mean(days.map((d) => d.climatology));
  return { forecast: f, usual: u, diff: f - u };
}

/** Plain words for a departure from the usual temperature. Thresholds are for wording only. */
export function departureWords(diff: number): string {
  const a = Math.abs(diff);
  if (a < 0.5) return "close to usual for the time of year";
  const size = a < 1.5 ? "slightly" : a < 3 ? "noticeably" : "much";
  return `${size} ${diff > 0 ? "warmer" : "cooler"} than usual for the time of year`;
}

/** Skill of damped persistence vs climatology, from RMSEs: 1 - (rmse_b / rmse_clim)^2. */
export function baselineSkill(r: LeadResult): number {
  const { baseline, climatology } = r.holdout.rmse;
  return 1 - (baseline / climatology) ** 2;
}

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export const METHOD_LABEL: Record<string, string> = {
  anomaly_regression: "Anomaly regression",
  seasonal_damped: "Seasonal damped persistence",
  damped_anomaly: "Damped persistence (baseline)",
};
