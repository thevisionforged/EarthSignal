/** Pure helpers for the Response Intelligence view (unit-tested). Plain-language labels for non-specialists. */

export interface EventRow {
  id: string;
  kind: "heat" | "rain";
  area: string;
  start: string;
  end: string;
  days: number;
  peak_value: number;
  peak_date: string;
  threshold_summary: number;
  severity: number;
  severity_unit: string;
  provisional: boolean;
  rank: number;
  n_events: number;
  years_with_event_this_severe: number;
  n_years: number;
  severity_band: string;
}

export type SortKey = "severity" | "recent";

export function sortEvents(events: EventRow[], key: SortKey): EventRow[] {
  const copy = [...events];
  return key === "severity" ? copy.sort((a, b) => a.rank - b.rank) : copy.sort((a, b) => (a.start < b.start ? 1 : -1));
}

export const VERDICT_LABEL: Record<string, string> = {
  corroborated: "Agrees: also unusual",
  not_corroborated: "Does not confirm",
  no_data: "No data for these dates",
};

export function verdictLabel(v: string): string {
  return VERDICT_LABEL[v] ?? v;
}

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  investigating: "Investigating",
  confirmed: "Confirmed",
  dismissed: "Dismissed",
  needs_data: "Needs more data",
  escalated: "Escalated for expert review",
};

export const ACTION_LABEL: Record<string, string> = {
  investigating: "Start / resume investigating",
  confirmed: "Confirm: the event is real",
  dismissed: "Dismiss: not noteworthy or a data artifact",
  needs_data: "Needs more data",
  escalated: "Escalate for expert review",
};

/** Decisions that must carry a written reason (mirrors the server rule). */
export function needsReason(from: string, to: string): boolean {
  return ["confirmed", "dismissed", "needs_data", "escalated"].includes(to) || (to === "investigating" && ["confirmed", "dismissed"].includes(from));
}

export function eventTitle(e: Pick<EventRow, "kind" | "start" | "end" | "days">): string {
  const what = e.kind === "heat" ? "Heat episode" : "Extreme rainfall";
  return e.days === 1 ? `${what}, ${e.start}` : `${what}, ${e.start} → ${e.end} (${e.days} days)`;
}

export function severityText(e: Pick<EventRow, "kind" | "severity" | "severity_unit" | "peak_value">): string {
  return e.kind === "heat"
    ? `${e.severity.toFixed(1)} ${e.severity_unit} above the threshold; peak daily mean ${e.peak_value.toFixed(1)} °C`
    : `${e.severity.toFixed(0)} mm in total; wettest day ${e.peak_value.toFixed(0)} mm`;
}

/** "Once in N years" phrasing from the empirical count; never a probability claim. */
export function frequencyText(e: Pick<EventRow, "years_with_event_this_severe" | "n_years">): string {
  const k = e.years_with_event_this_severe;
  return `Events at least this strong happened in ${k} of ${e.n_years} years of this record.`;
}

export const CASE_PAGE_SIZE = 25;

export interface CasePage {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export function pageOffset(offset: number): number {
  return Number.isFinite(offset) && offset > 0 ? Math.floor(offset) : 0;
}

export function casesUrl(offset: number, limit: number = CASE_PAGE_SIZE): string {
  return `/api/cases?limit=${limit}&offset=${pageOffset(offset)}`;
}

export function caseRange(page: CasePage, shown: number): string {
  if (shown <= 0) return `Cases 0 of ${page.total}`;
  return `Cases ${page.offset + 1}–${page.offset + shown} of ${page.total}`;
}

export function canGoBack(page: CasePage): boolean {
  return page.offset > 0;
}

export function canGoForward(page: CasePage): boolean {
  return page.has_more;
}

export function nextOffset(page: CasePage): number {
  return page.has_more ? page.offset + page.limit : page.offset;
}

export function previousOffset(page: CasePage): number {
  return Math.max(0, page.offset - page.limit);
}

export function lastPageOffset(total: number, limit: number = CASE_PAGE_SIZE): number {
  return total > 0 ? Math.floor((total - 1) / limit) * limit : 0;
}

export function pastTheEnd(page: CasePage, shown: number): boolean {
  return shown === 0 && page.offset > 0;
}

export function offsetAfter(action: "open" | "update", offset: number): number {
  return action === "open" ? 0 : pageOffset(offset);
}
