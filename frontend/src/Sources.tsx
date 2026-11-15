import { useEffect, useMemo, useState } from "react";
import { ArbitrationCard } from "./Arbitration";
import Chart from "./Chart";
import { multiApi, PrecipComparison, SourceMetadata } from "./api";
import { formatP, signed, sourceKindLabel, sourceLabel } from "./format";

type Load<T> = { state: "loading" } | { state: "ok"; data: T } | { state: "error"; message: string };

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): Load<T> {
  const [v, setV] = useState<Load<T>>({ state: "loading" });
  useEffect(() => {
    let live = true;
    setV({ state: "loading" });
    fn()
      .then((data) => live && setV({ state: "ok", data }))
      .catch((e) => live && setV({ state: "error", message: String(e.message ?? e) }));
    return () => {
      live = false;
    };
  }, deps);
  return v;
}

export function SourcesView({ area, areaLabel }: { area: string; areaLabel: string }) {
  const sources = useLoad(() => multiApi.sources(), []);
  const precip = useLoad(() => multiApi.precip(area), [area]);
  return (
    <>
      <section className="banner" aria-label="About this view">
        <strong>Data sources:</strong> every dataset EarthSignal holds, described with one common set of
        metadata, and a like-for-like check of NASA POWER (MERRA-2 reanalysis) precipitation against NASA GPM IMERG
        (satellite-gauge). The two are <strong>related products</strong>, not independent: agreement is consistency, not
        validation.
      </section>
      {sources.state === "ok" && <SourceCatalog rows={sources.data} />}
      {sources.state === "error" && <section className="card notice">Sources unavailable: {sources.message}</section>}
      {precip.state === "loading" && <section className="card loading">Loading precipitation comparison…</section>}
      {precip.state === "error" && (
        <section className="card notice">
          <h2>Precipitation comparison unavailable</h2>
          <p>{precip.message}</p>
        </section>
      )}
      {precip.state === "ok" && <PrecipCard c={precip.data} area={area} areaLabel={areaLabel} />}
      <ArbitrationCard area={area} areaLabel={areaLabel} />
    </>
  );
}

function SourceCatalog({ rows }: { rows: SourceMetadata[] }) {
  const [sel, setSel] = useState(0);
  const s = rows[Math.min(sel, rows.length - 1)];
  const coverage = useMemo(
    () =>
      rows.map((r, i) => ({
        type: "scatter",
        mode: "lines",
        name: sourceLabel(r),
        x: [r.time_coverage.start, r.time_coverage.end],
        y: [i, i],
        line: { color: COVERAGE_COLOR[r.source_type] ?? "--muted", width: 10 },
        hovertemplate: `${sourceLabel(r)}<br>%{x|%Y-%m-%d}<extra></extra>`,
      })),
    [rows],
  );
  const covLayout = useMemo(
    () => ({
      showlegend: false,
      yaxis: { tickvals: rows.map((_, i) => i), ticktext: rows.map((r) => sourceLabel(r)), automargin: true },
      xaxis: { type: "date" },
    }),
    [rows],
  );
  return (
    <section className="card">
      <div className="card-head">
        <h2>Data sources</h2>
        <span className="badge">{rows.length} datasets</span>
      </div>
      <h3>Time coverage</h3>
      <Chart data={coverage} layout={covLayout} ariaLabel="Time coverage of each dataset" small />
      <h3>Resolution and support</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Dataset</th>
              <th scope="col">Values are</th>
              <th scope="col">Spatial resolution</th>
              <th scope="col">Spatial support</th>
              <th scope="col">Time step / standard</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.dataset_id} className={i === sel ? "selected" : undefined}>
                <th scope="row">
                  <button className="linkish" onClick={() => setSel(i)} aria-pressed={i === sel}>
                    {sourceLabel(r)}
                  </button>
                </th>
                <td>{sourceKindLabel(r.source_type)}</td>
                <td>{r.spatial_resolution}</td>
                <td>{r.spatial_support}</td>
                <td>
                  {r.temporal_resolution} · {r.time_standard}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Metadata: {sourceLabel(s)}</h3>
      <dl className="prov">
        <dt>Provider</dt>
        <dd>{s.provider}</dd>
        <dt>Distributor</dt>
        <dd>{s.distributor}</dd>
        <dt>Product</dt>
        <dd>
          {s.product_id} · version {s.product_version}
        </dd>
        <dt>Variables</dt>
        <dd>
          {s.variables.map((v) => (
            <div key={v.name}>
              <code>{v.name}</code> ({v.units}, {sourceKindLabel(s.source_type)}){v.definition ? `: ${v.definition}` : ""}
            </div>
          ))}
        </dd>
        <dt>Coverage</dt>
        <dd>
          {s.time_coverage.start} to {s.time_coverage.end}
          {s.time_coverage.final_run_end ? ` (IMERG Final run ends ${s.time_coverage.final_run_end})` : ""}
        </dd>
        <dt>Retrieved</dt>
        <dd>{s.retrieved_at_utc.replace("T", " ").slice(0, 19)} UTC</dd>
        <dt>Access</dt>
        <dd>{s.access}</dd>
        <dt>Processing</dt>
        <dd>
          <ol className="compact">
            {s.processing_history.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ol>
        </dd>
        <dt>Limitations</dt>
        <dd>
          <ul className="compact">
            {s.quality_limitations.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </dd>
        <dt>Citation</dt>
        <dd>{s.citation}</dd>
        {s.usage_notice && (
          <>
            <dt>Usage notice</dt>
            <dd>{s.usage_notice}</dd>
          </>
        )}
        <dt>Dataset ID</dt>
        <dd className="url">{s.dataset_id}</dd>
      </dl>
    </section>
  );
}

const COVERAGE_COLOR: Record<string, string> = {
  nasa_power_met: "--annual",
  nasa_power_imerg: "--trend",
  imd_gridded: "--text",
  noaa_gsod: "--muted",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function PrecipCard({ c, area, areaLabel }: { c: PrecipComparison; area: string; areaLabel: string }) {
  const x = useMemo(() => c.series.months.map((m) => `${m}-15`), [c]);
  const lines = useMemo(
    () => [
      { type: "scatter", mode: "lines", name: "NASA POWER / MERRA-2 (reanalysis)", x, y: c.series.merra2_mm,
        line: { color: "--annual", width: 1.5 }, hovertemplate: "%{x|%b %Y}: %{y:.0f} mm<extra>MERRA-2</extra>" },
      { type: "scatter", mode: "lines", name: "GPM IMERG area mean (satellite-gauge)", x, y: c.series.imerg_mm,
        line: { color: "--trend", width: 1.5 }, hovertemplate: "%{x|%b %Y}: %{y:.0f} mm<extra>IMERG</extra>" },
    ],
    [c, x],
  );
  const seasonal = useMemo(() => {
    const mm = c.monthly.mean_by_calendar_month_mm;
    const keys = Array.from({ length: 12 }, (_, i) => String(i + 1));
    return [
      { type: "bar", name: "MERRA-2", x: MONTHS, y: keys.map((k) => mm.merra2[k]), marker: { color: "--annual" } },
      { type: "bar", name: "IMERG", x: MONTHS, y: keys.map((k) => mm.imerg[k]), marker: { color: "--trend" } },
    ];
  }, [c]);
  const lineLayout = useMemo(() => ({ yaxis: { title: { text: "mm / month" } } }), []);
  const barLayout = useMemo(() => ({ barmode: "group", yaxis: { title: { text: "mean mm / month" } } }), []);
  const m = c.monthly;
  const k = c.contingency;
  const t = c.trend_comparison;
  return (
    <section className="card">
      <div className="card-head">
        <h2>Precipitation: POWER vs GPM IMERG ({areaLabel})</h2>
        <span className="badge">{sourceKindLabel("nasa_power_met")} vs {sourceKindLabel("nasa_power_imerg")}</span>
      </div>
      <p className="note">
        Same area (IMERG averaged over the MERRA-2 cell), same UTC days, same units, {c.period.first_day} to{" "}
        {c.period.last_day} (IMERG Final run ends {c.period.final_run_end}; later IMERG values are excluded).
      </p>
      <Chart data={lines} layout={lineLayout} ariaLabel="Monthly precipitation totals, MERRA-2 versus IMERG" />
      <div className="stats">
        <Stat label="Monthly totals: correlation" value={`r ${m.pearson_r.toFixed(2)}`} sub={`${m.n} complete months; anomaly r ${m.anomaly_pearson_r.toFixed(2)}`} />
        <Stat label="MERRA-2 / IMERG (monthly)" value={`× ${m.ratio_merra2_over_imerg?.toFixed(2)}`} sub={`${signed(m.bias_merra2_minus_imerg, 1)} mm/month`} />
        <Stat label="Daily correlation" value={`r ${c.daily.pearson_r.toFixed(2)}`} sub={`RMSE ${c.daily.rmse.toFixed(1)} mm/day`} />
        <Stat label={`Wet days (≥ ${k.threshold_mm_day} mm)`} value={`${(k.wet_day_fraction_merra2 * 100).toFixed(0)}% vs ${(k.wet_day_fraction_imerg * 100).toFixed(0)}%`} sub={`MERRA-2 vs IMERG · CSI ${k.csi?.toFixed(2)}`} />
      </div>
      <div className="two-charts">
        <div>
          <p className="chart-title">Mean seasonal cycle (complete months)</p>
          <Chart data={seasonal} layout={barLayout} ariaLabel="Mean monthly precipitation by calendar month" small />
        </div>
        <div>
          {t && (
            <>
              <p className="chart-title">
                Annual-mean trend {t.merra2.period[0]}–{t.merra2.period[1]} (mm/day per decade)
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Series</th>
                      <th scope="col">Sen's slope</th>
                      <th scope="col">95% CI</th>
                      <th scope="col">Corrected p</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ["MERRA-2", t.merra2],
                        ["IMERG", t.imerg],
                        ["Difference", t.difference_merra2_minus_imerg],
                      ] as const
                    ).map(([name, r]) => (
                      <tr key={name}>
                        <th scope="row">{name}</th>
                        <td className="num">{signed(r.sen_slope_per_decade)}</td>
                        <td className="num">
                          {signed(r.ci95_per_decade[0])} to {signed(r.ci95_per_decade[1])}
                        </td>
                        <td className={`num ${r.significant_at_0_05 ? "sig" : "nonsig"}`}>{formatP(r.modified_mk_p_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
      <h3>What this shows</h3>
      <ul className="limits diag">
        {c.diagnostics.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <p className="notice-inline">
        <strong>Independence:</strong> {c.independence_note}
      </p>
      <details>
        <summary>Method</summary>
        <ul className="limits">
          {c.method.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      </details>
      <h3>Limitations</h3>
      <ul className="limits">
        {c.metadata.quality_limitations.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <p className="downloads">
        Download comparison results:{" "}
        <a href={multiApi.csvUrl(area, "monthly")} download>
          monthly CSV
        </a>{" "}
        ·{" "}
        <a href={multiApi.csvUrl(area, "daily")} download>
          daily CSV
        </a>
      </p>
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}
