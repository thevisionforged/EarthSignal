import { useEffect, useMemo, useState } from "react";
import Chart from "./Chart";
import { RobustnessCard, SeasonalCard } from "./Analysis";
import {
  api,
  ApiError,
  Area,
  Health,
  Provenance,
  SeasonalResponse,
  SensitivityResponse,
  StationComparison,
  TimeSeries,
  TrendResponse,
} from "./api";
import { OverviewView } from "./Overview";
import { SimulationStudio } from "./sim/Studio";
import { ResponseView } from "./response/Response";
import { ForecastView } from "./forecast/Forecast";
import { SourcesView } from "./Sources";
import { StationCard } from "./Station";
import { dataKindLabel, formatP, loadProblem, senLine, shortAreaLabel, signed, trendLineLabel, unitLabel } from "./format";

const VARIABLES = [
  { id: "T2M", label: "Air temperature (2 m)", short: "Temperature" },
  { id: "PRECTOTCORR", label: "Precipitation (corrected)", short: "Precipitation" },
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
  const [area, setArea] = useState("lucknow");
  const [view, setView] = useState<"overview" | "analysis" | "sources" | "studio" | "response" | "forecast">("overview");
  const health = useLoad<Health>(() => api.health(), []);
  const areas = useLoad<Area[]>(() => api.areas(), []);
  const series = useLoad<TimeSeries>(() => api.timeseries(area, variable, "monthly"), [area, variable]);
  const trend = useLoad<TrendResponse>(() => api.trend(area, variable), [area, variable]);
  const prov = useLoad<Provenance>(() => api.provenance(area), [area]);
  const seasonal = useLoad<SeasonalResponse>(() => api.seasonal(area, variable), [area, variable]);
  const sens = useLoad<SensitivityResponse>(() => api.sensitivity(area, variable), [area, variable]);
  const station = useLoad<StationComparison>(() => api.stationComparison(), []);
  const varLabel = VARIABLES.find((v) => v.id === variable)?.short ?? variable;
  const areaInfo = areas.state === "ok" ? areas.data.find((a) => a.key === area) : undefined;

  return (
    <main>
      <header>
        <h1>EarthSignal</h1>
        <p className="tagline">Understand Reality. Simulate Possibilities. Anticipate Tomorrow.</p>
        <p className="sub">
          Lucknow, Uttar Pradesh, India: historical climate, 1981 to present
          <span className={`status ${health.state === "ok" ? "up" : "down"}`}>
            API {health.state === "ok" ? `online · v${health.data.version}` : health.state === "loading" ? "…" : "offline"}
          </span>
        </p>
      </header>

      <nav className="tabs views" aria-label="View">
        <button aria-pressed={view === "overview"} onClick={() => setView("overview")}>
          Key findings
        </button>
        <button aria-pressed={view === "analysis"} onClick={() => setView("analysis")}>
          Climate analysis
        </button>
        <button aria-pressed={view === "sources"} onClick={() => setView("sources")}>
          Data sources &amp; precipitation check
        </button>
        <button aria-pressed={view === "studio"} onClick={() => setView("studio")}>
          Simulation Studio
        </button>
        <button aria-pressed={view === "response"} onClick={() => setView("response")}>
          Response Intelligence
        </button>
        <button aria-pressed={view === "forecast"} onClick={() => setView("forecast")}>
          Anticipate: temperature outlook
        </button>
      </nav>

      {(view === "analysis" || view === "sources") && (
        <>
      <nav className="tabs" aria-label="Grid cell">
        {(areas.state === "ok" ? areas.data : []).map((a) => (
          <button key={a.key} aria-pressed={area === a.key} onClick={() => setArea(a.key)} disabled={!a.dataset_id}>
            {a.label}
          </button>
        ))}
      </nav>
      {areaInfo && <p className="note area-note">{areaInfo.note}</p>}
        </>
      )}

      {view === "studio" ? (
        <SimulationStudio />
      ) : view === "response" ? (
        <ResponseView />
      ) : view === "forecast" ? (
        <ForecastView />
      ) : view === "overview" ? (
        <OverviewView
          go={(v: "analysis" | "sources") => {
            setView(v);
            window.scrollTo(0, 0);
          }}
        />
      ) : view === "sources" ? (
        <SourcesView area={area} areaLabel={shortAreaLabel(area)} />
      ) : (
        <>
      <section className="banner" aria-label="About this data">
        <strong>About these values:</strong> they are <strong>NASA POWER reanalysis estimates</strong> (NASA GMAO
        MERRA-2, extended to near real time with GEOS-IT). That is weather-model output constrained by observations and
        averaged over a ~55 × 62 km grid cell. Lucknow straddles the boundary between two cells, so both are available
        below. They are <strong>not</strong> thermometer or rain-gauge readings. No forecasts are shown.
      </section>


      <nav className="tabs" aria-label="Variable">
        {VARIABLES.map((v) => (
          <button key={v.id} aria-pressed={variable === v.id} onClick={() => setVariable(v.id)}>
            {v.label}
          </button>
        ))}
      </nav>

      {series.state === "loading" && <section className="card loading" aria-busy="true">Loading {varLabel.toLowerCase()} data…</section>}

      {series.state === "error" &&
        (loadProblem(series.status) === "no-data" ? (
          <section className="card notice">
            <h2>No data ingested yet</h2>
            <p>{series.message}</p>
            <p>
              Run <code>.venv\Scripts\python -m earthsignal.data.ingest --area {area}</code> from the project root, then
              reload.
            </p>
          </section>
        ) : (
          <section className="card notice">
            <h2>Backend not reachable</h2>
            <p>
              Start it from the project root with{" "}
              <code>.venv\Scripts\python -m uvicorn earthsignal.api.main:app --app-dir backend --port 8000</code>, then
              reload.
            </p>
            <p className="note">Detail: {series.message}</p>
          </section>
        ))}

      {series.state === "ok" && <SeriesCard ts={series.data} trend={trend.state === "ok" ? trend.data : null} />}
      {trend.state === "ok" && <TrendCard t={trend.data} label={varLabel} />}
      {trend.state === "error" && series.state === "ok" && (
        <section className="card notice">
          <h2>Trend unavailable</h2>
          <p>{trend.message}</p>
        </section>
      )}
      {sens.state === "ok" && <RobustnessCard s={sens.data} label={varLabel} />}
      {seasonal.state === "ok" && <SeasonalCard s={seasonal.data} label={varLabel} />}
      {station.state === "ok" && <StationCard c={station.data} />}
      {prov.state === "ok" && <ProvenanceCard p={prov.data} />}
        </>
      )}

      <footer className="note">
        EarthSignal · AstraelForge · TheVisionForged. Data: NASA LaRC POWER Project; NASA GPM IMERG (GES DISC); NOAA NCEI GSOD.
      </footer>
    </main>
  );
}

function SeriesCard({ ts, trend }: { ts: TimeSeries; trend: TrendResponse | null }) {
  const u = unitLabel(ts.units);
  const data = useMemo(() => {
    const traces: Record<string, unknown>[] = [
      {
        type: "scatter",
        mode: "lines",
        name: "Monthly mean",
        x: ts.dates.map((d) => `${d}-15`),
        y: ts.values,
        line: { color: "--series", width: 1 },
        connectgaps: false,
        hovertemplate: `%{x|%b %Y}: %{y:.2f} ${u}<extra>monthly mean</extra>`,
      },
    ];
    if (trend) {
      const yrs = trend.annual_means.years;
      const r = trend.result;
      traces.push({
        type: "scatter",
        mode: "lines+markers",
        name: "Annual mean",
        x: yrs.map((y) => `${y}-07-01`),
        y: trend.annual_means.values,
        line: { color: "--annual", width: 2 },
        marker: { color: "--annual", size: 5 },
        hovertemplate: `%{x|%Y}: %{y:.2f} ${u}<extra>annual mean</extra>`,
      });
      const ends = [yrs[0], yrs[yrs.length - 1]];
      traces.push({
        type: "scatter",
        mode: "lines",
        name: trendLineLabel(r.sen_slope_per_decade, u, r.significant_at_0_05),
        x: ends.map((y) => `${y}-07-01`),
        y: senLine(ends, r.sen_slope_per_decade, r.sen_intercept),
        line: { color: r.significant_at_0_05 ? "--trend" : "--muted", width: 2, dash: r.significant_at_0_05 ? "dash" : "dot" },
        hoverinfo: "skip",
      });
    }
    return traces;
  }, [ts, trend, u]);
  const layout = useMemo(() => ({ yaxis: { title: { text: u } } }), [u]);
  const monthlyRate = ts.units === "mm/day" ? " Precipitation is shown as a mean daily rate (mm/day), not a monthly total." : "";

  return (
    <section className="card">
      <div className="card-head">
        <h2>{ts.longname}</h2>
        <span className="badge">{dataKindLabel(ts.data_kind)}</span>
      </div>
      <Chart data={data} layout={layout} ariaLabel={`${ts.longname}: monthly and annual means for Lucknow`} />
      <p className="note">
        {ts.aggregation_note}
        {monthlyRate} {ts.data_kind_note}
      </p>
    </section>
  );
}

function TrendCard({ t, label }: { t: TrendResponse; label: string }) {
  const r = t.result;
  const u = unitLabel(r.units);
  const [lo, hi] = r.sen_slope_ci95_per_decade;
  return (
    <section className="card">
      <div className="card-head">
        <h2>
          {label} trend, {r.period_start_year}–{r.period_end_year}
        </h2>
        <span className="badge">{dataKindLabel("derived_statistic")}</span>
      </div>
      <p className={`verdict ${r.significant_at_0_05 ? "sig" : "nonsig"}`}>
        {r.significant_at_0_05
          ? `Statistically significant monotonic trend (corrected p = ${formatP(r.modified_mk_p_value)}).`
          : `No statistically significant monotonic trend (corrected p = ${formatP(r.modified_mk_p_value)}).`}
      </p>
      <div className="stats">
        <Stat label="Sen's slope" value={`${signed(r.sen_slope_per_decade)} ${u}/decade`} sub={`95% CI ${signed(lo)} to ${signed(hi)}`} />
        <Stat label="Corrected Mann-Kendall p" value={formatP(r.modified_mk_p_value)} sub={`uncorrected p ${formatP(r.mk_p_value)}`} />
        <Stat label="Implied change over period" value={`${signed(r.total_change_over_period)} ${u}`} sub={`${r.n_years} annual means`} />
        <Stat label="OLS cross-check" value={`${signed(r.ols_slope_per_decade)} ${u}/decade`} sub={`p ${formatP(r.ols_p_value)} · Durbin-Watson ${r.durbin_watson.toFixed(2)}`} />
      </div>
      <h3>Interpretation checks</h3>
      <ul className="limits diag">
        {r.diagnostics.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <details>
        <summary>How to read these numbers</summary>
        <ul className="limits">
          <li>
            <strong>Sen's slope</strong> is the median of the slopes between every pair of years. It is robust to
            outliers. The 95% CI is the range of slopes consistent with the data.
          </li>
          <li>
            <strong>Mann-Kendall p</strong> is the probability of a monotonic pattern at least this strong arising by
            chance if there were no trend. The <em>corrected</em> value accounts for neighbouring years being similar
            (autocorrelation, Yue &amp; Wang 2004), and only this value decides "significant" here.
          </li>
          <li>
            <strong>OLS</strong> (a straight-line fit) is shown for comparison only. It assumes independent years. A
            Durbin-Watson value well below 2 means that assumption is violated.
          </li>
          <li>
            A confidence interval that excludes 0 can still accompany a non-significant corrected p-value, because the
            interval does not account for autocorrelation.
          </li>
        </ul>
      </details>
      <p className="note">
        {r.method}. Detrended lag-1 autocorrelation {r.lag1_autocorrelation_detrended.toFixed(2)}. Years ending after{" "}
        {t.analysis_cutoff} are excluded, following NASA POWER guidance to end trend analyses about 2 months behind near
        real time.
        {Object.keys(r.excluded_years).length > 0 &&
          ` Excluded: ${Object.entries(r.excluded_years).map(([y, why]) => `${y} (${why})`).join("; ")}.`}
      </p>
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
          POWER Daily API {p.api_version}; sources reported by the API: {p.data_sources_reported_by_api.join(", ")}
        </dd>
        <dt>Retrieved</dt>
        <dd>{p.retrieved_at_utc.replace("T", " ").slice(0, 19)} UTC</dd>
        <dt>Grid cell</dt>
        <dd>
          {p.returned_coordinates.latitude}° N, {p.returned_coordinates.longitude}° E · {p.spatial_resolution} · daily
          values in {p.time_standard === "LST" ? "Local Solar Time" : p.time_standard}
        </dd>
        {Object.entries(p.variables).map(([k, v]) => (
          <div key={k} className="row">
            <dt>{k}</dt>
            <dd>
              {v.longname} ({unitLabel(v.units)}): "{v.definition}" Valid data {p.validation.variables[k]?.first_valid} to{" "}
              {p.validation.variables[k]?.last_valid} ({p.validation.variables[k]?.n_valid.toLocaleString()} of{" "}
              {p.validation.variables[k]?.n_days.toLocaleString()} days).
            </dd>
          </div>
        ))}
        <dt>Method</dt>
        <dd>{p.methodology_summary}</dd>
        <dt>Request</dt>
        <dd className="url">{p.request_url}</dd>
        <dt>Dataset ID</dt>
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
