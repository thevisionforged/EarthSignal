import { useMemo } from "react";
import Chart from "./Chart";
import { SeasonalResponse, SensitivityResponse, WindowRow } from "./api";
import { dataKindLabel, formatP, signed, unitLabel } from "./format";

export function SeasonalCard({ s, label }: { s: SeasonalResponse; label: string }) {
  const u = unitLabel(s.seasons[0]?.result.units ?? "");
  return (
    <section className="card">
      <div className="card-head">
        <h2>{label} trends by season</h2>
        <span className="badge">{dataKindLabel("derived_statistic")}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Season</th>
              <th scope="col">Years</th>
              <th scope="col">Sen's slope / decade</th>
              <th scope="col">95% CI</th>
              <th scope="col">Corrected p</th>
              <th scope="col">FDR-adjusted p</th>
              <th scope="col">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {s.seasons.map((row) => {
              const r = row.result;
              return (
                <tr key={row.season}>
                  <th scope="row">{row.label}</th>
                  <td>
                    {r.period_start_year}–{r.period_end_year} ({r.n_years})
                  </td>
                  <td className="num">
                    {signed(r.sen_slope_per_decade)} {u}
                  </td>
                  <td className="num">
                    {signed(r.sen_slope_ci95_per_decade[0])} to {signed(r.sen_slope_ci95_per_decade[1])}
                  </td>
                  <td className="num">{formatP(r.modified_mk_p_value)}</td>
                  <td className="num">{formatP(row.bh_adjusted_p)}</td>
                  <td className={row.significant_after_fdr_0_05 ? "sig" : "nonsig"}>
                    {row.significant_after_fdr_0_05 ? "Significant" : "Not significant"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">
        Seasons follow the India Meteorological Department definitions. The verdict uses the FDR-adjusted p-value
        (Benjamini-Hochberg across the four seasons), because testing four seasons raises the chance that at least
        one looks significant by luck. Seasons ending after {s.analysis_cutoff} are excluded.
      </p>
    </section>
  );
}

function windowTrace(rows: WindowRow[], key: "start_year" | "end_year", name: string, color: string) {
  return {
    type: "scatter",
    mode: "markers",
    name,
    x: rows.map((r) => r[key]),
    y: rows.map((r) => r.sen_slope_per_decade),
    error_y: {
      type: "data",
      symmetric: false,
      array: rows.map((r) => r.ci95_per_decade[1] - r.sen_slope_per_decade),
      arrayminus: rows.map((r) => r.sen_slope_per_decade - r.ci95_per_decade[0]),
      thickness: 1,
      width: 0,
      color,
    },
    marker: {
      color,
      size: 7,
      symbol: rows.map((r) => (r.significant_at_0_05 ? "circle" : "circle-open")),
      line: { color, width: 1.5 },
    },
    customdata: rows.map((r) => [r.start_year, r.end_year, formatP(r.modified_mk_p_value)]),
    hovertemplate: "%{customdata[0]}–%{customdata[1]}: %{y:+.2f}/decade, corrected p %{customdata[2]}<extra></extra>",
  };
}

export function RobustnessCard({ s, label }: { s: SensitivityResponse; label: string }) {
  const u = unitLabel(s.units);
  const last = s.vary_start[0]?.end_year;
  const first = s.vary_end[0]?.start_year;
  const startData = useMemo(() => [windowTrace(s.vary_start, "start_year", `Start year varies (end ${last})`, "--annual")], [s, last]);
  const endData = useMemo(() => [windowTrace(s.vary_end, "end_year", `End year varies (start ${first})`, "--trend")], [s, first]);
  const zeroLine = useMemo(
    () => ({
      yaxis: { title: { text: `${u} / decade` }, zeroline: true, zerolinecolor: "#888" },
      showlegend: false,
    }),
    [u],
  );
  const sp = s.source_periods;
  return (
    <section className="card">
      <div className="card-head">
        <h2>How robust is the {label.toLowerCase()} trend?</h2>
        <span className="badge">{dataKindLabel("derived_statistic")}</span>
      </div>
      <h3>Robustness checks</h3>
      <ul className="limits diag">
        {s.diagnostics.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <div className="two-charts">
        <div>
          <p className="chart-title">Changing the start year (end fixed at {last})</p>
          <Chart data={startData} layout={zeroLine} ariaLabel={`Sen's slope for each start year, ${label}`} small />
        </div>
        <div>
          <p className="chart-title">Changing the end year (start fixed at {first})</p>
          <Chart data={endData} layout={zeroLine} ariaLabel={`Sen's slope for each end year, ${label}`} small />
        </div>
      </div>
      <p className="note">
        Each point is Sen's slope for one window of at least {s.min_window_years} years, with its 95% CI. Filled points
        are significant after the autocorrelation correction; open points are not. {s.note}
      </p>
      <p className="note">
        {sp
          ? `Data source check: NASA POWER served MERRA-2 up to ${sp.last_merra2_day} and GEOS-IT from ${sp.first_geosit_day ?? "n/a"} (probed ${sp.probed_at_utc.slice(0, 10)}). ${
              s.geosit_in_trend_window === false
                ? "The trend window contains only MERRA-2 data."
                : "Part of the trend window uses GEOS-IT data."
            }`
          : "Data source check not run (python -m earthsignal.data.source_probe)."}
      </p>
    </section>
  );
}
