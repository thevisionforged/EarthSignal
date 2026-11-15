import { describe, expect, it } from "vitest";
import { clampStep, deleteConfig, fmt, fmtSigned, histogram, loadSaved, pairedHistogram, rampColor, saveConfig, simUrl } from "./logic";

describe("simUrl", () => {
  it("builds json and csv URLs from inputs", () => {
    expect(simUrl("heat", { area: "lucknow", threshold_c: 35 })).toBe("/api/sim/heat?area=lucknow&threshold_c=35");
    expect(simUrl("heat", { area: "lucknow" }, "csv")).toBe("/api/sim/heat?area=lucknow&format=csv");
  });
});

describe("clampStep", () => {
  it("keeps typed values inside the allowed range and on the step grid", () => {
    expect(clampStep(9, -3, 5, 0.5)).toBe(5);
    expect(clampStep(-7, -3, 5, 0.5)).toBe(-3);
    expect(clampStep(1.26, -3, 5, 0.5)).toBe(1.5);
    expect(clampStep(Number.NaN, 0, 2, 0.05)).toBe(0);
  });
});

describe("histograms", () => {
  it("counts every finite value exactly once", () => {
    const h = histogram([1, 2, 2, 3, Number.NaN], 2);
    expect(h.counts.reduce((a, b) => a + b, 0)).toBe(4);
    expect(h.counts).toEqual([1, 3]);
  });
  it("uses shared bins for paired series", () => {
    const p = pairedHistogram([0, 0, 1], [9, 10], 5);
    expect(p.a.reduce((x, y) => x + y)).toBe(3);
    expect(p.b.reduce((x, y) => x + y)).toBe(2);
    expect(p.centers.length).toBe(5);
    expect(p.b[4]).toBe(2); // 9 and the maximum 10 both fall in the last bin [8, 10]
  });
  it("handles a constant series", () => {
    expect(histogram([4, 4, 4], 3).counts.reduce((a, b) => a + b)).toBe(3);
  });
});

describe("formatting and colour", () => {
  it("formats missing values explicitly", () => {
    expect(fmt(null)).toBe("n/a");
    expect(fmtSigned(2, 1, "°C")).toBe("+2.0 °C");
    expect(fmtSigned(-0.5, 2)).toBe("-0.50");
  });
  it("maps the ramp ends to navy and cyan", () => {
    expect(rampColor(0, 0, 10)).toBe("rgb(13, 33, 58)");
    expect(rampColor(10, 0, 10)).toBe("rgb(34, 211, 238)");
  });
});

describe("saved configurations", () => {
  const mem = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };
  it("saves, replaces by name and deletes", () => {
    const s = mem();
    saveConfig({ name: "A", tool: "scenario", params: { temp_offset_c: 2 }, savedAt: "t" }, s);
    saveConfig({ name: "A", tool: "scenario", params: { temp_offset_c: 3 }, savedAt: "t2" }, s);
    expect(loadSaved(s)).toHaveLength(1);
    expect(loadSaved(s)[0].params.temp_offset_c).toBe(3);
    deleteConfig("scenario", "A", s);
    expect(loadSaved(s)).toHaveLength(0);
  });
  it("never throws when storage is blocked or corrupt", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(loadSaved(broken)).toEqual([]);
    expect(saveConfig({ name: "A", tool: "x", params: {}, savedAt: "t" }, broken)).toBe(false);
    expect(loadSaved({ getItem: () => "{not json" })).toEqual([]);
  });
});
