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
