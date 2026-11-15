import { describe, expect, it } from "vitest";
import { ArbLite, rainfallFinding, stationFinding, temperatureFinding, unavailableFinding } from "./findings";

const t = (s: number, pv: number) => ({ sen_slope_per_decade: s, modified_mk_p_value: pv, significant_at_0_05: pv < 0.05 });

describe("temperatureFinding", () => {
  it("says no significant trend only when neither cell is significant", () => {
    const f = temperatureFinding({ ...t(-0.16, 0.18), period_start_year: 1981, period_end_year: 2025 }, t(-0.12, 0.35));
    expect(f.headline).toBe("No statistically significant temperature trend over 1981–2025 in either grid cell.");
    expect(f.evidence).toContain("-0.16 °C/decade (p 0.18)");
  });
  it("reports a one-cell trend as one cell only", () => {
    expect(temperatureFinding(t(0.3, 0.01), t(0.1, 0.4)).headline).toMatch(/one grid cell only/);
  });
});

describe("stationFinding", () => {
  it("uses the drift test result", () => {
    const f = stationFinding({ ...t(-0.3, 0.017), n_years: 16 }, [2006, 2023]);
    expect(f.headline).toMatch(/drift apart over 2006–2023/);
    expect(f.evidence).toMatch(/cannot tell which record/);
    expect(stationFinding({ ...t(-0.1, 0.4), n_years: 16 }, [2006, 2023]).headline).toMatch(/no significant drift/);
  });
});

const arb = (merraDrift: [number, number], imergDrift: [number, number], p2006: number): ArbLite => ({
  vs_reference: {
    merra2: { difference_trend: t(...merraDrift), breaks: { "2006": { available: true, mann_whitney_p: p2006 } } },
    imerg: { difference_trend: t(...imergDrift), breaks: {} },
  },
  trends: { imd: t(0, 0.5) },
});

describe("rainfallFinding", () => {
  it("names only the cells where POWER drifts and never claims a trend", () => {
    const f = rainfallFinding(arb([39, 0.63], [-140, 0.06], 0.022), arb([129, 0.02], [4, 0.89], 0.008));
    expect(f.headline).toBe(
      "NASA POWER's rainfall increase is not supported by rain gauges in the western cell; no Lucknow rainfall trend is claimed.",
    );
    expect(f.evidence).toMatch(/eastern and western cells/);
  });
  it("falls back to 'sources disagree' when IMERG also drifts", () => {
    const f = rainfallFinding(arb([129, 0.02], [-150, 0.01], 0.5), arb([10, 0.6], [4, 0.9], 0.5));
    expect(f.headline).toMatch(/^Rainfall sources disagree/);
    expect(f.evidence).not.toMatch(/2006/);
  });
});

describe("unavailableFinding", () => {
  it("names what is missing without inventing numbers", () => {
    const f = unavailableFinding("rainfall", "Rain-gauge check of the rainfall trend", "No IMD dataset", "sources");
    expect(f.key).toBe("rainfall-unavailable");
    expect(f.headline).toContain("not available");
    expect(f.evidence).toContain("No IMD dataset");
    expect(/\d/.test(f.headline + f.evidence.replace("No IMD dataset", ""))).toBe(false);
  });
});
