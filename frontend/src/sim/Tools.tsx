import { useMemo, useState } from "react";
import Chart from "../Chart";
import { fmt, fmtSigned, pairedHistogram, rampColor, rampText } from "./logic";
import { AREA_FIELD, END_FIELD, Field, Kpi, SimEnvelope, START_FIELD, ToolFrame } from "./ToolFrame";

const BASE = "#8FA3BF";
const SCEN = "#22D3EE";
const AMBER = "#F5B841";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const BASE_PERIOD = { area: "lucknow", start_year: 1991, end_year: 2020 };

type Cmp = Record<string, { baseline: number; scenario: number; difference: number; percent: number | null }>;
type Clim = { month: number; mean_temp_c: number | null; mean_monthly_precip_mm: number | null; exceedance_days_per_year: number; wet_days_per_year: number; high_rain_days_per_year: number }[];

const T_OFFSET: Field = { key: "temp_offset_c", label: "Temperature offset", kind: "slider", min: -3, max: 5, step: 0.5, unit: "°C" };
const P_MULT: Field = { key: "precip_multiplier", label: "Precipitation multiplier", kind: "slider", min: 0, max: 2, step: 0.05, unit: "×", help: "1.00 = unchanged; 0.70 = 30% less rain on every day" };
const T_THRESH: Field = { key: "threshold_c", label: "Temperature threshold (daily mean)", kind: "slider", min: 25, max: 40, step: 0.5, unit: "°C" };
const WET: Field = { key: "wet_threshold_mm", label: "Wet-day threshold", kind: "number", min: 0.1, max: 50, step: 0.1, unit: "mm/day", help: "A day with at least this much rain counts as wet (default 1 mm)." };
const HEAVY: Field = { key: "heavy_threshold_mm", label: "High-rainfall-day threshold", kind: "number", min: 1, max: 500, step: 1, unit: "mm/day", help: "Your chosen level, not an official hazard category (default 50 mm)." };
const PERIOD = [AREA_FIELD, START_FIELD, END_FIELD];
const dark = { dark: true as const };

// ---------------------------------------------------------------- Tool 1
type ScenarioRes = SimEnvelope & { summary: Cmp; monthly: { months: string[]; baseline_temp: (number | null)[]; scenario_temp: (number | null)[]; baseline_precip: (number | null)[]; scenario_precip: (number | null)[] }; climatology: { baseline: Clim; scenario: Clim } };

export function ScenarioBuilder() {
  return (
    <ToolFrame<ScenarioRes>
      tool="scenario"
      title="Climate Scenario Builder"
      question="What does the historical record look like if every day were warmer, cooler, wetter or drier by a fixed amount?"
      fields={[{ key: "name", label: "Scenario name", kind: "text" }, ...PERIOD, T_OFFSET, P_MULT]}
      defaults={{ ...BASE_PERIOD, name: "Custom", temp_offset_c: 0, precip_multiplier: 1 }}
      presets={[
        { label: "Historical baseline", params: { name: "Historical baseline", temp_offset_c: 0, precip_multiplier: 1 } },
        { label: "Warmer", params: { name: "Warmer conditions", temp_offset_c: 2, precip_multiplier: 1 } },
        { label: "Drier", params: { name: "Drier conditions", temp_offset_c: 0, precip_multiplier: 0.7 } },
        { label: "Wetter", params: { name: "Wetter conditions", temp_offset_c: 0, precip_multiplier: 1.3 } },
        { label: "Combined stress", params: { name: "Combined stress", temp_offset_c: 2, precip_multiplier: 0.7 } },
        { label: "Custom", params: { name: "Custom" } },
      ]}
      render={(d, a) => <ScenarioView d={d} name={String(a.name)} />}
    />
  );
}

function ScenarioView({ d, name }: { d: ScenarioRes; name: string }) {
  const [v, setV] = useState<"temp" | "precip">("temp");
  const s = d.summary;
  const x = d.monthly.months.map((m) => `${m}-15`);
  const series = useMemo(
    () =>
      v === "temp"
        ? [
            { type: "scatter", mode: "lines", name: "Historical (baseline)", x, y: d.monthly.baseline_temp, line: { color: BASE, width: 1.2 } },
            { type: "scatter", mode: "lines", name: `Hypothetical: ${name}`, x, y: d.monthly.scenario_temp, line: { color: SCEN, width: 1.2 } },
          ]
        : [
            { type: "scatter", mode: "lines", name: "Historical (baseline)", x, y: d.monthly.baseline_precip, line: { color: BASE, width: 1.2 } },
            { type: "scatter", mode: "lines", name: `Hypothetical: ${name}`, x, y: d.monthly.scenario_precip, line: { color: SCEN, width: 1.2 } },
          ],
    [d, v, x, name],
  );
  const clim = useMemo(
    () => [
      { type: "bar", name: "Baseline precipitation", x: MONTHS, y: d.climatology.baseline.map((r) => r.mean_monthly_precip_mm), marker: { color: BASE } },
      { type: "bar", name: "Scenario precipitation", x: MONTHS, y: d.climatology.scenario.map((r) => r.mean_monthly_precip_mm), marker: { color: SCEN } },
      { type: "scatter", mode: "lines+markers", name: "Baseline temperature", x: MONTHS, y: d.climatology.baseline.map((r) => r.mean_temp_c), yaxis: "y2", line: { color: BASE, dash: "dot" } },
      { type: "scatter", mode: "lines+markers", name: "Scenario temperature", x: MONTHS, y: d.climatology.scenario.map((r) => r.mean_temp_c), yaxis: "y2", line: { color: SCEN, dash: "dot" } },
    ],
    [d],
  );
  return (
    <>
      <div className="kpis">
        <Kpi label="Mean temperature" base={s.mean_temp_c?.baseline ?? null} scen={s.mean_temp_c?.scenario ?? null} unit="°C" digits={2} />
        <Kpi label="Total precipitation, whole period" base={s.total_precip_mm?.baseline ?? null} scen={s.total_precip_mm?.scenario ?? null} unit="mm" digits={0} pct={s.total_precip_mm?.percent} />
        <Kpi label="Mean daily precipitation" base={s.mean_daily_precip_mm?.baseline ?? null} scen={s.mean_daily_precip_mm?.scenario ?? null} unit="mm/day" digits={2} pct={s.mean_daily_precip_mm?.percent} />
        <Kpi label="Wet days (≥ 1 mm)" base={s.wet_days?.baseline ?? null} scen={s.wet_days?.scenario ?? null} unit="days" digits={0} pct={s.wet_days?.percent} />
      </div>
      <div className="seg" role="group" aria-label="Series">
        <button aria-pressed={v === "temp"} onClick={() => setV("temp")}>Monthly mean temperature (°C)</button>
        <button aria-pressed={v === "precip"} onClick={() => setV("precip")}>Monthly precipitation (mm)</button>
      </div>
      <Chart {...dark} data={series} layout={{ yaxis: { title: { text: v === "temp" ? "°C" : "mm / month" } } }} ariaLabel="Monthly baseline and scenario series" />
      <p className="chart-cap">Average seasonal cycle over the period: precipitation (bars, mm/month) and temperature (dotted, °C, right axis)</p>
      <Chart {...dark} small data={clim} layout={{ barmode: "group", yaxis: { title: { text: "mm / month" } }, yaxis2: { title: { text: "°C" }, overlaying: "y", side: "right", showgrid: false }, margin: { l: 52, r: 52, t: 8, b: 32 } }} ariaLabel="Seasonal cycle baseline versus scenario" />
      <p className="note-d">Percentage changes are not shown for temperature: °C has an arbitrary zero, so a percent change would be meaningless.</p>
    </>
  );
}

// ---------------------------------------------------------------- Tool 2
type HeatRes = SimEnvelope & { summary: Cmp; per_year: { years: number[]; baseline: number[]; scenario: number[] }; monthly: { baseline: Clim; scenario: Clim }; hottest_days: { date: string; temp_c: number }[]; hottest_months: { month: string; mean_temp_c: number }[] };

export function HeatExplorer() {
  return (
    <ToolFrame<HeatRes>
      tool="heat"
      title="Heat Stress Explorer"
      question="How many days exceed a daily-mean temperature threshold, historically and with a temperature offset?"
      fields={[...PERIOD, T_THRESH, T_OFFSET]}
      defaults={{ ...BASE_PERIOD, threshold_c: 35, temp_offset_c: 2 }}
      render={(d, a) => <HeatView d={d} thr={Number(a.threshold_c)} />}
    />
  );
}

function HeatView({ d, thr }: { d: HeatRes; thr: number }) {
  const s = d.summary;
  const n = d.years_used.length;
  const per = useMemo(() => [
    { type: "bar", name: "Historical", x: d.per_year.years, y: d.per_year.baseline, marker: { color: BASE } },
    { type: "bar", name: "Hypothetical", x: d.per_year.years, y: d.per_year.scenario, marker: { color: SCEN } },
  ], [d]);
  const mon = useMemo(() => [
    { type: "bar", name: "Historical", x: MONTHS, y: d.monthly.baseline.map((r) => r.exceedance_days_per_year), marker: { color: BASE } },
    { type: "bar", name: "Hypothetical", x: MONTHS, y: d.monthly.scenario.map((r) => r.exceedance_days_per_year), marker: { color: SCEN } },
  ], [d]);
  return (
    <>
      <div className="kpis">
        <Kpi label={`Days with daily mean > ${thr} °C (whole period)`} base={s.temp_exceedance_days?.baseline ?? 0} scen={s.temp_exceedance_days?.scenario ?? 0} unit="days" digits={0} pct={s.temp_exceedance_days?.percent} />
        <Kpi label="Per year (mean)" base={(s.temp_exceedance_days?.baseline ?? 0) / n} scen={(s.temp_exceedance_days?.scenario ?? 0) / n} unit="days/yr" digits={1} />
        <Kpi label="Hottest daily mean" base={s.max_temp_c?.baseline ?? null} scen={s.max_temp_c?.scenario ?? null} unit="°C" digits={2} />
      </div>
      <p className="chart-cap">Exceedance days per year</p>
      <Chart {...dark} data={per} layout={{ barmode: "group", yaxis: { title: { text: "days / year" } } }} ariaLabel="Exceedance days per year" />
      <div className="two">
        <div>
          <p className="chart-cap">Monthly distribution (mean days per year)</p>
          <Chart {...dark} small data={mon} layout={{ barmode: "group", yaxis: { title: { text: "days / year" } } }} ariaLabel="Exceedance days by month" />
        </div>
        <div className="tables">
          <table className="dtable">
            <caption>Hottest historical days (daily mean)</caption>
            <tbody>{d.hottest_days.slice(0, 6).map((h) => <tr key={h.date}><td>{h.date}</td><td className="num">{fmt(h.temp_c, 2, "°C")}</td></tr>)}</tbody>
          </table>
          <table className="dtable">
            <caption>Hottest historical months (monthly mean)</caption>
            <tbody>{d.hottest_months.map((h) => <tr key={h.month}><td>{h.month}</td><td className="num">{fmt(h.mean_temp_c, 2, "°C")}</td></tr>)}</tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- Tool 3
type Seas = { season: string; label: string; mean_seasonal_precip_mm: number | null; wet_days_per_year: number; high_rain_days_per_year: number }[];
type RainRes = SimEnvelope & { summary: Cmp; per_year: { years: number[]; baseline_total: number[]; scenario_total: number[]; baseline_high: number[]; scenario_high: number[] }; monthly: { baseline: Clim; scenario: Clim }; seasonal: { baseline: Seas; scenario: Seas } };

export function RainSimulator() {
  return (
    <ToolFrame<RainRes>
      tool="rain"
      title="Rainfall Stress Simulator"
      question="How do rainfall totals and rain-day counts change if every day's rain is scaled?"
      fields={[...PERIOD, P_MULT, WET, HEAVY]}
      defaults={{ ...BASE_PERIOD, precip_multiplier: 1.3, wet_threshold_mm: 1, heavy_threshold_mm: 50 }}
      render={(d, a) => <RainView d={d} wet={Number(a.wet_threshold_mm)} heavy={Number(a.heavy_threshold_mm)} />}
    />
  );
}

function RainView({ d, wet, heavy }: { d: RainRes; wet: number; heavy: number }) {
  const s = d.summary;
  const tot = useMemo(() => [
    { type: "scatter", mode: "lines+markers", name: "Historical", x: d.per_year.years, y: d.per_year.baseline_total, line: { color: BASE } },
    { type: "scatter", mode: "lines+markers", name: "Hypothetical", x: d.per_year.years, y: d.per_year.scenario_total, line: { color: SCEN } },
  ], [d]);
  const mon = useMemo(() => [
    { type: "bar", name: "Historical", x: MONTHS, y: d.monthly.baseline.map((r) => r.mean_monthly_precip_mm), marker: { color: BASE } },
    { type: "bar", name: "Hypothetical", x: MONTHS, y: d.monthly.scenario.map((r) => r.mean_monthly_precip_mm), marker: { color: SCEN } },
  ], [d]);
  return (
    <>
      <div className="kpis">
        <Kpi label="Total precipitation, whole period" base={s.total_precip_mm?.baseline ?? null} scen={s.total_precip_mm?.scenario ?? null} unit="mm" digits={0} pct={s.total_precip_mm?.percent} />
        <Kpi label="Mean daily precipitation" base={s.mean_daily_precip_mm?.baseline ?? null} scen={s.mean_daily_precip_mm?.scenario ?? null} unit="mm/day" digits={2} pct={s.mean_daily_precip_mm?.percent} />
        <Kpi label={`Wet days (≥ ${wet} mm)`} base={s.wet_days?.baseline ?? 0} scen={s.wet_days?.scenario ?? 0} unit="days" digits={0} pct={s.wet_days?.percent} />
        <Kpi label={`High-rainfall days (≥ ${heavy} mm)`} base={s.high_rain_days?.baseline ?? 0} scen={s.high_rain_days?.scenario ?? 0} unit="days" digits={0} pct={s.high_rain_days?.percent} />
        <Kpi label="Wettest single day" base={s.max_daily_precip_mm?.baseline ?? null} scen={s.max_daily_precip_mm?.scenario ?? null} unit="mm" digits={1} pct={s.max_daily_precip_mm?.percent} />
      </div>
      <p className="chart-cap">Annual precipitation totals (mm/year)</p>
      <Chart {...dark} data={tot} layout={{ yaxis: { title: { text: "mm / year" } } }} ariaLabel="Annual precipitation totals" />
      <div className="two">
        <div>
          <p className="chart-cap">Monthly distribution (mean mm per month)</p>
          <Chart {...dark} small data={mon} layout={{ barmode: "group", yaxis: { title: { text: "mm / month" } } }} ariaLabel="Monthly precipitation distribution" />
        </div>
        <table className="dtable">
          <caption>Seasons (IMD), mean per year</caption>
          <thead><tr><th>Season</th><th className="num">Historical mm</th><th className="num">Hypothetical mm</th><th className="num">High-rain days</th></tr></thead>
          <tbody>
            {d.seasonal.baseline.map((b, i) => (
              <tr key={b.season}>
                <td>{b.label}</td>
                <td className="num">{fmt(b.mean_seasonal_precip_mm, 0)}</td>
                <td className="num">{fmt(d.seasonal.scenario[i].mean_seasonal_precip_mm, 0)}</td>
                <td className="num">{b.high_rain_days_per_year.toFixed(2)} → {d.seasonal.scenario[i].high_rain_days_per_year.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- Tool 4
type Cell = { temp_offset_c: number; precip_multiplier: number; mean_temp_c: number | null; total_precip_mm: number | null; exceedance_days_per_year: number; precip_mm_per_year: number; wet_days_per_year: number; high_rain_days_per_year: number };
type CompoundRes = SimEnvelope & { offsets: number[]; multipliers: number[]; cells: Cell[] };
const CELL_METRICS: { key: keyof Cell; label: string; unit: string; digits: number }[] = [
  { key: "exceedance_days_per_year", label: "Temperature exceedance days / year", unit: "days", digits: 1 },
  { key: "precip_mm_per_year", label: "Precipitation / year", unit: "mm", digits: 0 },
  { key: "wet_days_per_year", label: "Wet days / year", unit: "days", digits: 1 },
  { key: "high_rain_days_per_year", label: "High-rainfall days / year", unit: "days", digits: 2 },
  { key: "mean_temp_c", label: "Mean temperature", unit: "°C", digits: 2 },
];

export function CompoundExperiment() {
  return (
    <ToolFrame<CompoundRes>
      tool="compound"
      title="Compound Climate Experiment"
      question="What happens across a grid of combined temperature and precipitation assumptions?"
      fields={[
        ...PERIOD,
        { key: "t_min", label: "Lowest temperature offset", kind: "number", min: -3, max: 5, step: 0.5, unit: "°C" },
        { key: "t_max", label: "Highest temperature offset", kind: "number", min: -3, max: 5, step: 0.5, unit: "°C" },
        { key: "t_step", label: "Temperature step", kind: "number", min: 0.5, max: 4, step: 0.5, unit: "°C" },
        { key: "p_min", label: "Lowest precipitation multiplier", kind: "number", min: 0, max: 2, step: 0.1, unit: "×" },
        { key: "p_max", label: "Highest precipitation multiplier", kind: "number", min: 0, max: 2, step: 0.1, unit: "×" },
        { key: "p_step", label: "Precipitation step", kind: "number", min: 0.1, max: 1, step: 0.1, unit: "×" },
        T_THRESH, WET, HEAVY,
      ]}
      defaults={{ ...BASE_PERIOD, t_min: -1, t_max: 3, t_step: 1, p_min: 0.6, p_max: 1.4, p_step: 0.2, threshold_c: 35, wet_threshold_mm: 1, heavy_threshold_mm: 50 }}
      render={(d) => <CompoundView d={d} />}
    />
  );
}

function CompoundView({ d }: { d: CompoundRes }) {
  const [mk, setMk] = useState(0);
  const [sel, setSel] = useState<Cell | null>(null);
  const m = CELL_METRICS[mk];
  const vals = d.cells.map((c) => Number(c[m.key] ?? 0));
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const cell = (o: number, p: number) => d.cells.find((c) => c.temp_offset_c === o && c.precip_multiplier === p)!;
  const base = d.cells.find((c) => c.temp_offset_c === 0 && c.precip_multiplier === 1);
  return (
    <>
      <div className="seg" role="group" aria-label="Metric">
        {CELL_METRICS.map((x, i) => (
          <button key={x.key} aria-pressed={i === mk} onClick={() => setMk(i)}>{x.label}</button>
        ))}
      </div>
      <div className="matrix-wrap">
        <table className="matrix" aria-label={`${m.label} by temperature offset and precipitation multiplier`}>
          <thead>
            <tr>
              <th>ΔT ↓ / P × →</th>
              {d.multipliers.map((p) => <th key={p}>{p.toFixed(2)}×</th>)}
            </tr>
          </thead>
          <tbody>
            {d.offsets.map((o) => (
              <tr key={o}>
                <th>{fmtSigned(o, 1, "°C")}</th>
                {d.multipliers.map((p) => {
                  const c = cell(o, p);
                  const v = Number(c[m.key] ?? 0);
                  const isBase = o === 0 && p === 1;
                  return (
                    <td key={p}>
                      <button className={`mcell${isBase ? " base" : ""}${sel === c ? " sel" : ""}`} style={{ background: rampColor(v, lo, hi), color: rampText(v, lo, hi) }} onClick={() => setSel(c)} aria-label={`${fmtSigned(o, 1, "°C")}, ${p.toFixed(2)}×: ${v.toFixed(m.digits)} ${m.unit}`}>
                        {v.toFixed(m.digits)}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note-d">
        {m.label} ({m.unit}). The outlined cell is the historical baseline (0 °C, 1.00×){base ? `: ${Number(base[m.key]).toFixed(m.digits)} ${m.unit}` : ""}. Select a cell for all its metrics.
      </p>
      {sel && (
        <div className="kpis">
          {CELL_METRICS.map((x) => (
            <Kpi key={x.key} label={`${x.label} at ${fmtSigned(sel.temp_offset_c, 1, "°C")}, ${sel.precip_multiplier.toFixed(2)}×`} base={base ? Number(base[x.key]) : null} scen={Number(sel[x.key])} unit={x.unit} digits={x.digits} />
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- Tool 5
type AnalogRes = SimEnvelope & { target: { mean_temp_c: number; total_precip_mm: number }; period_mean: { mean_temp_c: number; total_precip_mm: number }; outside_historical_range: Record<string, boolean>; analogs: { year: number; similarity: number; distance_z: number; mean_temp_c: number; total_precip_mm: number }[]; all_years: { year: number; mean_temp_c: number; total_precip_mm: number; distance_z: number }[]; excluded_year_units: Record<string, string> };

export function AnalogFinder() {
  return (
    <ToolFrame<AnalogRes>
      tool="analogs"
      title="Historical Analog Finder"
      question="Which past years or seasons already looked most like these assumptions?"
      fields={[
        ...PERIOD, T_OFFSET, P_MULT,
        { key: "unit", label: "Compare", kind: "select", options: [{ value: "annual", label: "Whole year" }, { value: "winter", label: "Winter (Jan–Feb)" }, { value: "pre_monsoon", label: "Pre-monsoon (Mar–May)" }, { value: "monsoon", label: "Monsoon (Jun–Sep)" }, { value: "post_monsoon", label: "Post-monsoon (Oct–Dec)" }] },
        { key: "temp_weight", label: "Weight on temperature", kind: "slider", min: 0, max: 3, step: 0.5 },
        { key: "precip_weight", label: "Weight on precipitation", kind: "slider", min: 0, max: 3, step: 0.5 },
        { key: "n", label: "Number of analogues", kind: "number", min: 1, max: 15, step: 1 },
      ]}
      defaults={{ area: "lucknow", start_year: 1981, end_year: 2025, temp_offset_c: 1, precip_multiplier: 1.2, unit: "annual", temp_weight: 1, precip_weight: 1, n: 5 }}
      render={(d) => <AnalogView d={d} />}
    />
  );
}

function AnalogView({ d }: { d: AnalogRes }) {
  const top = new Set(d.analogs.map((a) => a.year));
  const data = useMemo(() => [
    { type: "scatter", mode: "markers", name: "Historical years", x: d.all_years.filter((y) => !top.has(y.year)).map((y) => y.total_precip_mm), y: d.all_years.filter((y) => !top.has(y.year)).map((y) => y.mean_temp_c), text: d.all_years.filter((y) => !top.has(y.year)).map((y) => String(y.year)), marker: { color: BASE, size: 7 }, hovertemplate: "%{text}: %{y:.2f} °C, %{x:.0f} mm<extra></extra>" },
    { type: "scatter", mode: "markers+text", name: "Closest analogues", x: d.analogs.map((y) => y.total_precip_mm), y: d.analogs.map((y) => y.mean_temp_c), text: d.analogs.map((y) => String(y.year)), textposition: "top center", marker: { color: SCEN, size: 11 }, hovertemplate: "%{text}: %{y:.2f} °C, %{x:.0f} mm<extra></extra>" },
    { type: "scatter", mode: "markers", name: "Scenario target", x: [d.target.total_precip_mm], y: [d.target.mean_temp_c], marker: { color: AMBER, size: 16, symbol: "x" }, hovertemplate: "Target: %{y:.2f} °C, %{x:.0f} mm<extra></extra>" },
  ], [d]); // eslint-disable-line
  const out = Object.entries(d.outside_historical_range).filter(([, v]) => v).map(([k]) => (k === "mean_temp_c" ? "temperature" : "precipitation"));
  return (
    <>
      <div className="kpis">
        <Kpi label="Target mean temperature" base={d.period_mean.mean_temp_c} scen={d.target.mean_temp_c} unit="°C" digits={2} />
        <Kpi label="Target precipitation total" base={d.period_mean.total_precip_mm} scen={d.target.total_precip_mm} unit="mm" digits={0} />
      </div>
      {out.length > 0 && <p className="amber-note">The target {out.join(" and ")} lies outside every year in this record. The “closest” years are still unlike it.</p>}
      <Chart {...dark} data={data} layout={{ xaxis: { title: { text: "precipitation total (mm)" } }, yaxis: { title: { text: "mean temperature (°C)" } } }} ariaLabel="Historical years by temperature and precipitation, with the scenario target" />
      <table className="dtable">
        <caption>Closest historical analogues (similarity = 1 / (1 + distance); 1 = identical)</caption>
        <thead><tr><th>Year</th><th className="num">Mean T (°C)</th><th className="num">Precip (mm)</th><th className="num">Distance (z)</th><th>Similarity</th></tr></thead>
        <tbody>
          {d.analogs.map((a) => (
            <tr key={a.year}>
              <td>{a.year}</td>
              <td className="num">{a.mean_temp_c.toFixed(2)}</td>
              <td className="num">{a.total_precip_mm.toFixed(0)}</td>
              <td className="num">{a.distance_z.toFixed(2)}</td>
              <td><span className="simbar" style={{ width: `${Math.round(a.similarity * 100)}%` }} /> {a.similarity.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {Object.keys(d.excluded_year_units).length > 0 && (
        <p className="note-d">Excluded because of missing days: {Object.entries(d.excluded_year_units).map(([y, why]) => `${y} (${why})`).join("; ")}.</p>
      )}
    </>
  );
}

// ---------------------------------------------------------------- Tool 6
type Boot = { replicates: number[]; median: number; p05: number; p95: number; observed_mean: number };
type UncRes = SimEnvelope & { baseline: Record<string, Boot>; scenario: Record<string, Boot>; sensitivity: { by_temp_offset: Record<string, number>[]; by_precip_multiplier: Record<string, number>[] } };
const BOOT: { key: string; label: string; unit: string; digits: number }[] = [
  { key: "exceedance_days", label: "Temperature exceedance days per year", unit: "days", digits: 1 },
  { key: "total_precip_mm", label: "Precipitation per year", unit: "mm", digits: 0 },
  { key: "high_rain_days", label: "High-rainfall days per year", unit: "days", digits: 2 },
  { key: "wet_days", label: "Wet days per year", unit: "days", digits: 1 },
  { key: "mean_temp_c", label: "Annual mean temperature", unit: "°C", digits: 2 },
];

export function UncertaintyLab() {
  return (
    <ToolFrame<UncRes>
      tool="uncertainty"
      title="Uncertainty & Sensitivity Lab"
      question="How much do the results move with year-to-year variability, and with the assumptions?"
      fields={[...PERIOD, T_OFFSET, P_MULT, T_THRESH, HEAVY,
        { key: "n_boot", label: "Resamples", kind: "number", min: 100, max: 5000, step: 100 },
        { key: "seed", label: "Random seed (recorded)", kind: "number", min: 0, max: 2147483647, step: 1 }]}
      defaults={{ ...BASE_PERIOD, temp_offset_c: 2, precip_multiplier: 0.8, threshold_c: 35, heavy_threshold_mm: 50, n_boot: 1000, seed: 20261115 }}
      render={(d) => <UncView d={d} />}
    />
  );
}

function UncView({ d }: { d: UncRes }) {
  const [mk, setMk] = useState(0);
  const m = BOOT[mk];
  const b = d.baseline[m.key];
  const s = d.scenario[m.key];
  const h = pairedHistogram(b.replicates, s.replicates, 24);
  const hist = [
    { type: "bar", name: "Historical", x: h.centers, y: h.a, marker: { color: BASE }, opacity: 0.8 },
    { type: "bar", name: "Hypothetical", x: h.centers, y: h.b, marker: { color: SCEN }, opacity: 0.8 },
  ];
  const band = (x: Boot) => [{ type: "line", x0: x.p05, x1: x.p95, yref: "paper", y0: 0.98, y1: 0.98, line: { color: AMBER, width: 4 } }];
  const sensT = [
    { type: "scatter", mode: "lines+markers", name: "Exceedance days / year", x: d.sensitivity.by_temp_offset.map((r) => r.temp_offset_c), y: d.sensitivity.by_temp_offset.map((r) => r.exceedance_days_per_year), line: { color: SCEN } },
  ];
  const sensP = [
    { type: "scatter", mode: "lines+markers", name: "Precipitation / year", x: d.sensitivity.by_precip_multiplier.map((r) => r.precip_multiplier), y: d.sensitivity.by_precip_multiplier.map((r) => r.precip_mm_per_year), line: { color: SCEN } },
    { type: "scatter", mode: "lines+markers", name: "High-rainfall days / year", x: d.sensitivity.by_precip_multiplier.map((r) => r.precip_multiplier), y: d.sensitivity.by_precip_multiplier.map((r) => r.high_rain_days_per_year), yaxis: "y2", line: { color: AMBER, dash: "dot" } },
  ];
  return (
    <>
      <div className="seg" role="group" aria-label="Metric">
        {BOOT.map((x, i) => <button key={x.key} aria-pressed={i === mk} onClick={() => setMk(i)}>{x.label}</button>)}
      </div>
      <div className="kpis">
        <div className="kpi">
          <div className="kpi-label">Historical: median (5th–95th percentile of resamples)</div>
          <div className="kpi-row"><span className="kpi-base">{b.median.toFixed(m.digits)}</span><span className="kpi-unit">{m.unit}</span></div>
          <div className="kpi-diff amber">{b.p05.toFixed(m.digits)} – {b.p95.toFixed(m.digits)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Hypothetical: median (5th–95th percentile of resamples)</div>
          <div className="kpi-row"><span className="kpi-scen">{s.median.toFixed(m.digits)}</span><span className="kpi-unit">{m.unit}</span></div>
          <div className="kpi-diff amber">{s.p05.toFixed(m.digits)} – {s.p95.toFixed(m.digits)}</div>
        </div>
      </div>
      <p className="chart-cap">Distribution of {b.replicates.length} resampled period means (amber bars mark the 5th–95th percentile spans)</p>
      <Chart {...dark} data={hist} layout={{ barmode: "overlay", bargap: 0.02, xaxis: { title: { text: `${m.label} (${m.unit})` } }, yaxis: { title: { text: "resamples" } }, shapes: [...band(b), ...band(s)] }} ariaLabel="Resampling distributions" />
      <div className="two">
        <div>
          <p className="chart-cap">Sensitivity to the temperature offset (precipitation unchanged)</p>
          <Chart {...dark} small data={sensT} layout={{ showlegend: false, xaxis: { title: { text: "temperature offset (°C)" } }, yaxis: { title: { text: "days / year" } } }} ariaLabel="Sensitivity to temperature offset" />
        </div>
        <div>
          <p className="chart-cap">Sensitivity to the precipitation multiplier (temperature unchanged)</p>
          <Chart {...dark} small data={sensP} layout={{ xaxis: { title: { text: "precipitation multiplier (×)" } }, yaxis: { title: { text: "mm / year" } }, yaxis2: { title: { text: "days / year" }, overlaying: "y", side: "right", showgrid: false }, margin: { l: 52, r: 52, t: 8, b: 32 } }} ariaLabel="Sensitivity to precipitation multiplier" />
        </div>
      </div>
    </>
  );
}
