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
