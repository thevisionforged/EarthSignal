import { describe, expect, it } from "vitest";
import {
  CASE_PAGE_SIZE, canGoBack, canGoForward, CasePage, caseRange, casesUrl, EventRow, eventTitle, frequencyText, lastPageOffset, needsReason,
  nextOffset, offsetAfter, pageOffset, pastTheEnd, previousOffset, severityText, sortEvents, verdictLabel,
} from "./logic";

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

const pg = (total: number, offset: number, has_more: boolean, limit = 25): CasePage => ({ total, limit, offset, has_more });

describe("case pagination", () => {
  it("asks the server for one page of 25 at a sane offset", () => {
    expect(CASE_PAGE_SIZE).toBe(25);
    expect(casesUrl(0)).toBe("/api/cases?limit=25&offset=0");
    expect(casesUrl(50)).toBe("/api/cases?limit=25&offset=50");
    expect(casesUrl(10, 5)).toBe("/api/cases?limit=5&offset=10");
    expect(casesUrl(-25)).toBe("/api/cases?limit=25&offset=0");
    expect(casesUrl(Number.NaN)).toBe("/api/cases?limit=25&offset=0");
    expect(casesUrl(Number.POSITIVE_INFINITY)).toBe("/api/cases?limit=25&offset=0");
    expect(casesUrl(25.7)).toBe("/api/cases?limit=25&offset=25");
    expect(pageOffset(-1)).toBe(0);
  });

  it("describes the visible range, including a partial last page", () => {
    expect(caseRange(pg(57, 0, true), 25)).toBe("Cases 1–25 of 57");
    expect(caseRange(pg(57, 25, true), 25)).toBe("Cases 26–50 of 57");
    expect(caseRange(pg(57, 50, false), 7)).toBe("Cases 51–57 of 57");
    expect(caseRange(pg(1, 0, false), 1)).toBe("Cases 1–1 of 1");
    expect(caseRange(pg(0, 0, false), 0)).toBe("Cases 0 of 0");
    expect(caseRange(pg(57, 75, false), 0)).toBe("Cases 0 of 57");
  });

  it("only allows moving to pages that exist", () => {
    expect(canGoBack(pg(57, 0, true))).toBe(false);
    expect(canGoForward(pg(57, 0, true))).toBe(true);
    expect(canGoBack(pg(57, 25, true))).toBe(true);
    expect(canGoBack(pg(57, 50, false))).toBe(true);
    expect(canGoForward(pg(57, 50, false))).toBe(false);
    expect(canGoBack(pg(0, 0, false))).toBe(false);
    expect(canGoForward(pg(0, 0, false))).toBe(false);
    expect(canGoForward(pg(50, 25, false))).toBe(false);
  });

  it("steps forward and back by one page without leaving the record", () => {
    expect(nextOffset(pg(57, 0, true))).toBe(25);
    expect(nextOffset(pg(57, 25, true))).toBe(50);
    expect(nextOffset(pg(57, 50, false))).toBe(50);
    expect(previousOffset(pg(57, 50, false))).toBe(25);
    expect(previousOffset(pg(57, 25, true))).toBe(0);
    expect(previousOffset(pg(57, 0, true))).toBe(0);
    expect(previousOffset(pg(57, 10, true))).toBe(0);
  });

  it("recovers from an offset past the end of the record", () => {
    expect(pastTheEnd(pg(57, 75, false), 0)).toBe(true);
    expect(pastTheEnd(pg(0, 25, false), 0)).toBe(true);
    expect(pastTheEnd(pg(0, 0, false), 0)).toBe(false);
    expect(pastTheEnd(pg(57, 50, false), 7)).toBe(false);
    expect(lastPageOffset(57)).toBe(50);
    expect(lastPageOffset(50)).toBe(25);
    expect(lastPageOffset(25)).toBe(0);
    expect(lastPageOffset(1)).toBe(0);
    expect(lastPageOffset(0)).toBe(0);
    expect(lastPageOffset(7, 3)).toBe(6);
  });

  it("returns to the first page after opening a case and stays put after an update", () => {
    expect(offsetAfter("open", 50)).toBe(0);
    expect(offsetAfter("open", 0)).toBe(0);
    expect(offsetAfter("update", 50)).toBe(50);
    expect(offsetAfter("update", -5)).toBe(0);
  });
});
