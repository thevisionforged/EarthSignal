/** Pure helpers (unit-tested). No numbers are invented here; they only transform API values. */

export function senLine(years: number[], slopePerDecade: number, intercept: number): number[] {
  const perYear = slopePerDecade / 10;
  return years.map((y) => intercept + perYear * y);
}

export function signed(value: number, digits = 2): string {
  const s = value.toFixed(digits);
  return value > 0 ? `+${s}` : s;
}

export function formatP(p: number): string {
  if (p < 0.001) return "< 0.001";
  return p.toFixed(3);
}

export function unitLabel(units: string): string {
  return units === "C" ? "°C" : units;
}

/** Short human label for a dataset in the multi-source view. */
export function sourceLabel(s: { source_type: string; area?: string | null }): string {
  const cell = s.area === "lucknow_airport" ? "western cell" : s.area === "lucknow" ? "eastern cell" : "";
  switch (s.source_type) {
    case "nasa_power_met":
      return `POWER MERRA-2 (${cell})`;
    case "nasa_power_imerg":
      return `GPM IMERG via POWER (${cell})`;
    case "noaa_gsod":
      return "NOAA GSOD airport station";
    case "imd_gridded":
      return "IMD rain-gauge grid (both cells)";
    default:
      return s.source_type;
  }
}

/** What kind of values a dataset holds, by source type. The generic data_kind "derived_estimate" covers
 *  reanalysis, satellite-gauge and gauge-grid products alike, so it must not be shown as "reanalysis" for all. */
export function sourceKindLabel(sourceType: string): string {
  switch (sourceType) {
    case "nasa_power_met":
      return "Reanalysis estimate (model + observations)";
    case "nasa_power_imerg":
      return "Satellite estimate, gauge-calibrated";
    case "imd_gridded":
      return "Gridded from rain gauges";
    case "noaa_cpcu":
      return "Gridded from rain gauges";
    case "noaa_gsod":
      return "Station observation";
    default:
      return sourceType;
  }
}

/** Short name of a study area for titles: "eastern cell" / "western cell". */
export function shortAreaLabel(area: string): string {
  return area === "lucknow_airport" ? "western cell, airport" : area === "lucknow" ? "eastern cell, city centre" : area;
}

/** Which problem to show for a failed API call. 404 = backend up but no ingested data. */
export function loadProblem(status: number | undefined): "no-data" | "backend-unreachable" {
  return status === 404 ? "no-data" : "backend-unreachable";
}

export function trendLineLabel(slopePerDecade: number, units: string, significant: boolean): string {
  const base = `Sen's slope ${signed(slopePerDecade)} ${units}/decade`;
  return significant ? base : `${base} (not significant)`;
}

export function dataKindLabel(kind: string): string {
  switch (kind) {
    case "observed":
      return "Observed";
    case "derived_estimate":
      return "Derived estimate (reanalysis)";
    case "derived_statistic":
      return "Derived statistic";
    case "forecast":
      return "Forecast";
    case "hypothetical":
      return "Hypothetical scenario";
    default:
      return kind;
  }
}
