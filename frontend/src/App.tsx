import { useEffect, useMemo, useState } from "react";
import Chart from "./Chart";
import { api, ApiError, Health, Provenance, TimeSeries, TrendResponse } from "./api";
import { dataKindLabel, formatP, senLine, signed, unitLabel } from "./format";

const VARIABLES = [
  { id: "T2M", label: "Air temperature (2 m)" },
  { id: "PRECTOTCORR", label: "Precipitation (corrected)" },
];

type Load<T> = { state: "loading" } | { state: "ok"; data: T } | { state: "error"; status?: number; message: string };

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): Load<T> {
  const [v, setV] = useState<Load<T>>({ state: "loading" });
  useEffect(() => {
    let live = true;
    setV({ state: "loading" });
    fn()
      .then((data) => live && setV({ state: "ok", data }))
      .catch((e) =>
        live && setV({ state: "error", status: e instanceof ApiError ? e.status : undefined, message: String(e.message ?? e) }),
      );
    return () => {
      live = false;
    };
  }, deps);
  return v;
}

export default function App() {
  const [variable, setVariable] = useState("T2M");
  const health = useLoad<Health>(() => api.health(), []);
  const series = useLoad<TimeSeries>(() => api.timeseries(variable, "monthly"), [variable]);
  const trend = useLoad<TrendResponse>(() => api.trend(variable), [variable]);
  const prov = useLoad<Provenance>(() => api.provenance(), []);

  return (
    <main>
      <header>
        <h1>EarthSignal</h1>
        <p className="tagline">Understand Reality. Simulate Possibilities. Anticipate Tomorrow.</p>
        <p className="sub">
          Lucknow, Uttar Pradesh: historical climate from NASA POWER
          <span className={`status ${health.state === "ok" ? "up" : "down"}`}>
            API {health.state === "ok" ? `online · v${health.data.version}` : health.state === "loading" ? "…" : "offline"}
          </span>
        </p>
      </header>

      <nav className="tabs" aria-label="Variable">
        {VARIABLES.map((v) => (
          <button key={v.id} aria-pressed={variable === v.id} onClick={() => setVariable(v.id)}>
            {v.label}
          </button>
        ))}
      </nav>

      {series.state === "error" && (
        <section className="card notice">
          <h2>No data loaded</h2>
          <p>{series.message}</p>
          <p>
            Run <code>.venv\Scripts\python -m earthsignal.data.ingest</code> from the project root, then reload.
          </p>
        </section>
      )}

      {series.state === "ok" && <SeriesCard ts={series.data} trend={trend.state === "ok" ? trend.data : null} />}
      {trend.state === "ok" && <TrendCard t={trend.data} />}
      {trend.state === "error" && series.state === "ok" && (
        <section className="card notice">
          <h2>Trend unavailable</h2>
          <p>{trend.message}</p>
        </section>
      )}
      {prov.state === "ok" && <ProvenanceCard p={prov.data} />}
    </main>
  );
}

function SeriesCard({ ts, trend }: { ts: TimeSeries; trend: TrendResponse | null }) {
  const u = unitLabel(ts.units);
  const data = useMemo(() => {
    const traces: unknown[] = [
      {
        type: "scatter",
        mode: "lines",
        name: "Monthly mean",
        x: ts.dates.map((d) => `${d}-15`),
        y: ts.values,
        line: { color: getVar("--series"), width: 1 },
        connectgaps: false,
        hovertemplate: `%{x|%b %Y}: %{y:.2f} ${u}<extra></extra>`,
      },
    ];
    if (trend) {
      const yrs = trend.annual_means.years;
      traces.push({
        type: "scatter",
        mode: "lines+markers",
        name: "Annual mean",
        x: yrs.map((y) => `${y}-07-01`),
        y: trend.annual_means.values,
        line: { color: getVar("--annual"), width: 2 },
        marker: { size: 5 },
        hovertemplate: `%{x|%Y}: %{y:.2f} ${u}<extra></extra>`,
      });
      const r = trend.result;
      const ends = [yrs[0], yrs[yrs.length - 1]];
      traces.push({
        type: "scatter",
        mode: "lines",
        name: `Sen's slope ${signed(r.sen_slope_per_decade)} ${u}/decade`,
        x: ends.map((y) => `${y}-07-01`),
        y: senLine(ends, r.sen_slope_per_decade, r.sen_intercept),
        line: { color: getVar("--trend"), width: 2, dash: "dash" },
        hoverinfo: "skip",
      });
    }
    return traces;
  }, [ts, trend, u]);
  const layout = useMemo(() => ({ yaxis: { title: { text: `${ts.longname} (${u})` } }, height: 380 }), [ts, u]);

  return (
    <section className="card">
      <div className="card-head">
        <h2>{ts.longname}</h2>
        <span className="badge">{dataKindLabel(ts.data_kind)}</span>
      </div>
      <Chart data={data} layout={layout} ariaLabel={`${ts.longname} monthly and annual means for Lucknow`} />
      <p className="note">{ts.aggregation_note} {ts.data_kind_note}</p>
    </section>
  );
}

function TrendCard({ t }: { t: TrendResponse }) {
  const r = t.result;
  const u = unitLabel(r.units);
  const [lo, hi] = r.sen_slope_ci95_per_decade;
  return (
    <section className="card">
      <div className="card-head">
        <h2>
          Trend {r.period_start_year}–{r.period_end_year}
        </h2>
        <span className="badge">{dataKindLabel("derived_statistic")}</span>
      </div>
      <div className="stats">
        <Stat label="Sen's slope" value={`${signed(r.sen_slope_per_decade)} ${u}/decade`} sub={`95% CI ${signed(lo)} to ${signed(hi)}`} />
        <Stat label="Modified Mann-Kendall p" value={formatP(r.modified_mk_p_value)} sub={r.significant_at_0_05 ? "significant at 0.05" : "not significant at 0.05"} />
        <Stat label="Change over period" value={`${signed(r.total_change_over_period)} ${u}`} sub={`${r.n_years} annual means`} />
        <Stat label="OLS cross-check" value={`${signed(r.ols_slope_per_decade)} ${u}/decade`} sub={`p ${formatP(r.ols_p_value)} · DW ${r.durbin_watson.toFixed(2)}`} />
      </div>
      <p className="note">
        {r.method}. Lag-1 autocorrelation (detrended) {r.lag1_autocorrelation_detrended.toFixed(2)}. Years after{" "}
        {t.analysis_cutoff} are excluded, per NASA POWER guidance to end trend analyses about 2 months behind near real time.
        {Object.keys(r.excluded_years).length > 0 && ` Excluded: ${Object.entries(r.excluded_years).map(([y, why]) => `${y} (${why})`).join("; ")}.`}
      </p>
      <h3>Interpretation checks</h3>
      <ul className="limits diag">
        {r.diagnostics.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <h3>Limitations</h3>
      <ul className="limits">
        {r.limitations.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </section>
  );
}

function ProvenanceCard({ p }: { p: Provenance }) {
  return (
    <section className="card">
      <h2>Data provenance</h2>
      <dl className="prov">
        <dt>Provider</dt>
        <dd>{p.provider}</dd>
        <dt>API</dt>
        <dd>
          {p.api_version}; sources reported: {p.data_sources_reported_by_api.join(", ")}
        </dd>
        <dt>Retrieved</dt>
        <dd>{p.retrieved_at_utc}</dd>
        <dt>Grid cell</dt>
        <dd>
          {p.returned_coordinates.latitude}° N, {p.returned_coordinates.longitude}° E · {p.spatial_resolution} · {p.time_standard}
        </dd>
        {Object.entries(p.variables).map(([k, v]) => (
          <div key={k} className="row">
            <dt>{k}</dt>
            <dd>
              {v.longname} ({unitLabel(v.units)}): {v.definition} · coverage {p.validation.variables[k]?.first_valid} to{" "}
              {p.validation.variables[k]?.last_valid}
            </dd>
          </div>
        ))}
        <dt>Method</dt>
        <dd>{p.methodology_summary}</dd>
        <dt>Request</dt>
        <dd className="url">{p.request_url}</dd>
        <dt>Dataset</dt>
        <dd className="url">{p.dataset_id}</dd>
      </dl>
      <p className="note">
        {p.citation} {p.citation_data_reference}{" "}
        <a href={p.documentation.methodology} target="_blank" rel="noreferrer">
          POWER methodology
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

function getVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
