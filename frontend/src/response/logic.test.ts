import { describe, expect, it } from "vitest";
import { EventRow, eventTitle, frequencyText, needsReason, severityText, sortEvents, verdictLabel } from "./logic";

const ev = (id: string, start: string, rank: number): EventRow => ({
  id, kind: "rain", area: "lucknow", start, end: start, days: 1, peak_value: 100, peak_date: start, threshold_summary: 58,
  severity: 100, severity_unit: "mm", provisional: false, rank, n_events: 3, years_with_event_this_severe: 1, n_years: 46,
  severity_band: "",
});

describe("response logic", () => {
  it("sorts by severity rank or by recency without mutating", () => {
    const list = [ev("a", "2001-01-01", 2), ev("b", "2020-01-01", 3), ev("c", "1990-01-01", 1)];
    expect(sortEvents(list, "severity").map((e) => e.id)).toEqual(["c", "a", "b"]);
    expect(sortEvents(list, "recent").map((e) => e.id)).toEqual(["b", "a", "c"]);
    expect(list[0].id).toBe("a");
  });
  it("labels verdicts in plain language", () => {
    expect(verdictLabel("corroborated")).toMatch(/Agrees/);
    expect(verdictLabel("not_corroborated")).toBe("Does not confirm");
    expect(verdictLabel("no_data")).toMatch(/No data/);
  });
  it("mirrors the server's reason rule", () => {
    expect(needsReason("open", "investigating")).toBe(false);
    expect(needsReason("investigating", "confirmed")).toBe(true);
    expect(needsReason("dismissed", "investigating")).toBe(true);
  });
  it("writes titles and frequency without probability claims", () => {
    expect(eventTitle({ kind: "heat", start: "2002-07-19", end: "2002-07-30", days: 12 })).toBe("Heat episode, 2002-07-19 → 2002-07-30 (12 days)");
    expect(frequencyText({ years_with_event_this_severe: 1, n_years: 46 })).toBe("Events at least this strong happened in 1 of 46 years of this record.");
    expect(frequencyText({ years_with_event_this_severe: 1, n_years: 46 })).not.toMatch(/probab|chance|will/i);
    expect(severityText({ kind: "rain", severity: 282.5, severity_unit: "mm", peak_value: 150 })).toBe("283 mm in total; wettest day 150 mm");
  });
});
