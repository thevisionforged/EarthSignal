import { describe, expect, it } from "vitest";
import { dataKindLabel, formatP, loadProblem, senLine, signed, trendLineLabel, unitLabel } from "./format";

describe("loadProblem", () => {
  it("distinguishes missing data from an unreachable backend", () => {
    expect(loadProblem(404)).toBe("no-data");
    expect(loadProblem(500)).toBe("backend-unreachable"); // Vite proxy error when uvicorn is down
    expect(loadProblem(0)).toBe("backend-unreachable");
    expect(loadProblem(undefined)).toBe("backend-unreachable");
  });
});

describe("trendLineLabel", () => {
  it("marks non-significant trends on the chart legend", () => {
    expect(trendLineLabel(-0.158, "°C", false)).toBe("Sen's slope -0.16 °C/decade (not significant)");
    expect(trendLineLabel(0.243, "mm/day", true)).toBe("Sen's slope +0.24 mm/day/decade");
  });
});

describe("senLine", () => {
  it("evaluates intercept + slope*year with slope given per decade", () => {
    expect(senLine([2000, 2010], 0.5, -75)).toEqual([-75 + 0.05 * 2000, -75 + 0.05 * 2010]);
  });
});

describe("formatting", () => {
  it("signs values", () => {
    expect(signed(0.234)).toBe("+0.23");
    expect(signed(-0.2)).toBe("-0.20");
  });
  it("formats p-values", () => {
    expect(formatP(0.0004)).toBe("< 0.001");
    expect(formatP(0.0421)).toBe("0.042");
  });
  it("labels units and data kinds without upgrading estimates to observations", () => {
    expect(unitLabel("C")).toBe("°C");
    expect(unitLabel("mm/day")).toBe("mm/day");
    expect(dataKindLabel("derived_estimate")).toContain("reanalysis");
    expect(dataKindLabel("derived_estimate")).not.toMatch(/observed/i);
  });
});
