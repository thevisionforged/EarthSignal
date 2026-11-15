import { describe, expect, it } from "vitest";
import { baselineSkill, departureWords, ForecastDay, isoToday, LeadResult, splitByToday, weekSummary } from "./logic";

const day = (date: string, forecast: number, climatology: number): ForecastDay => ({
  date, lead_days: 1, forecast, low: forecast - 2, high: forecast + 2, climatology, method: "anomaly_regression",
});

describe("forecast logic", () => {
  it("formats today in local time", () => {
    expect(isoToday(new Date(2026, 10, 5))).toBe("2026-11-05");
  });
  it("splits forecast days into past and future around today", () => {
    const days = [day("2026-11-12", 21, 20), day("2026-11-15", 20, 20), day("2026-11-16", 19, 20)];
    const { past, future } = splitByToday(days, "2026-11-15");
    expect(past.map((d) => d.date)).toEqual(["2026-11-12"]);
    expect(future.map((d) => d.date)).toEqual(["2026-11-15", "2026-11-16"]);
  });
  it("summarises a week against the usual value", () => {
    const s = weekSummary([day("a", 22, 20), day("b", 20, 19)])!;
    expect(s.forecast).toBeCloseTo(21);
    expect(s.diff).toBeCloseTo(1.5);
    expect(weekSummary([])).toBeNull();
  });
  it("describes departures in plain words", () => {
    expect(departureWords(0.2)).toBe("close to usual for the time of year");
    expect(departureWords(1.0)).toBe("slightly warmer than usual for the time of year");
    expect(departureWords(-2)).toBe("noticeably cooler than usual for the time of year");
    expect(departureWords(4)).toBe("much warmer than usual for the time of year");
  });
  it("derives baseline skill from RMSEs", () => {
    const r = { holdout: { rmse: { chosen: 1, baseline: 1, climatology: 2 } } } as LeadResult;
    expect(baselineSkill(r)).toBeCloseTo(0.75);
  });
});
