/** Pure functions that turn API results into the overview's key findings (unit-tested).
 *  Every sentence is derived from numbers returned by the API; nothing is hard-coded. */

export interface TrendLite {
  sen_slope_per_decade: number;
  modified_mk_p_value: number;
  significant_at_0_05: boolean;
  period_start_year?: number;
  period_end_year?: number;
}

export interface Finding {
  key: string;
  headline: string;
  evidence: string;
  view: "analysis" | "sources";
}

const fmt = (x: number, d = 2) => (x > 0 ? `+${x.toFixed(d)}` : x.toFixed(d));
const p = (x: number) => (x < 0.001 ? "< 0.001" : x.toFixed(2));

export function temperatureFinding(east: TrendLite, west: TrendLite): Finding {
  const anySig = east.significant_at_0_05 || west.significant_at_0_05;
  const period = east.period_start_year ? `${east.period_start_year}–${east.period_end_year}` : "the record";
  const headline = anySig
    ? `A statistically significant temperature trend appears in ${east.significant_at_0_05 && west.significant_at_0_05 ? "both grid cells" : "one grid cell only"} (${period}).`
    : `No statistically significant temperature trend over ${period} in either grid cell.`;
  return {
    key: "temperature",
    headline,
    evidence:
      `NASA POWER 2 m temperature, corrected Mann-Kendall test: eastern cell ${fmt(east.sen_slope_per_decade)} °C/decade (p ${p(east.modified_mk_p_value)}), ` +
      `western cell ${fmt(west.sen_slope_per_decade)} °C/decade (p ${p(west.modified_mk_p_value)}). Naive tests that ignore year-to-year ` +
      "correlation would overstate significance.",
    view: "analysis",
  };
}

export function stationFinding(diff: TrendLite & { n_years: number }, years: number[]): Finding {
  const span = `${years[0]}–${years[years.length - 1]}`;
  return {
    key: "station",
    headline: diff.significant_at_0_05
      ? `NASA POWER and the Lucknow airport thermometer drift apart over ${span}.`
      : `NASA POWER and the Lucknow airport thermometer show no significant drift over ${span}.`,
    evidence:
      `POWER minus station (annual temperature anomalies, ${diff.n_years} years): ${fmt(diff.sen_slope_per_decade)} °C/decade ` +
      `(p ${p(diff.modified_mk_p_value)}). These data cannot tell which record is responsible.`,
    view: "analysis",
  };
}

export interface ArbLite {
  vs_reference: Record<"merra2" | "imerg", { difference_trend: TrendLite; breaks: Record<string, { available: boolean; mann_whitney_p?: number }> }>;
  trends: Record<"imd", TrendLite>;
}

export function rainfallFinding(east: ArbLite, west: ArbLite, breakAlpha = 0.025): Finding {
  const drifts = (a: ArbLite) => a.vs_reference.merra2.difference_trend.significant_at_0_05;
  const imergDrifts = (a: ArbLite) => a.vs_reference.imerg.difference_trend.significant_at_0_05;
  const step2006 = (a: ArbLite) => {
    const b = a.vs_reference.merra2.breaks["2006"];
    return !!b?.available && (b.mann_whitney_p ?? 1) < breakAlpha;
  };
  const cellsDrift = [drifts(east) && "eastern", drifts(west) && "western"].filter(Boolean) as string[];
  let headline: string;
  if (cellsDrift.length && !imergDrifts(east) && !imergDrifts(west)) {
    headline = `NASA POWER's rainfall increase is not supported by rain gauges in the ${cellsDrift.join(" and ")} cell${cellsDrift.length > 1 ? "s" : ""}; no Lucknow rainfall trend is claimed.`;
  } else {
    headline = "Rainfall sources disagree on the long-term trend; no Lucknow rainfall trend is claimed.";
  }
  const steps = [step2006(east) && "eastern", step2006(west) && "western"].filter(Boolean) as string[];
  const evidence =
    `Against the IMD rain-gauge analysis: POWER drift ${fmt(east.vs_reference.merra2.difference_trend.sen_slope_per_decade, 0)} (east, p ${p(east.vs_reference.merra2.difference_trend.modified_mk_p_value)}) and ` +
    `${fmt(west.vs_reference.merra2.difference_trend.sen_slope_per_decade, 0)} mm/yr per decade (west, p ${p(west.vs_reference.merra2.difference_trend.modified_mk_p_value)}); GPM IMERG drift ` +
    `${fmt(east.vs_reference.imerg.difference_trend.sen_slope_per_decade, 0)} / ${fmt(west.vs_reference.imerg.difference_trend.sen_slope_per_decade, 0)}.` +
    (steps.length
      ? ` POWER shifts relative to the gauges at 2006, when its documented gauge input (NOAA CPC) changed version (${steps.join(" and ")} cell${steps.length > 1 ? "s" : ""}).`
      : "");
  return { key: "rainfall", headline, evidence, view: "sources" };
}
