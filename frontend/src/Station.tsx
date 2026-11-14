import { useMemo } from "react";
import Chart from "./Chart";
import { StationComparison } from "./api";
import { dataKindLabel, formatP, signed } from "./format";

export function StationCard({ c }: { c: StationComparison }) {
  const m = c.metrics_primary;
  const t = c.trend_comparison;
  const x = useMemo(() => c.monthly.months.map((d) => `${d}-15`), [c]);
  const data = useMemo(
    () => [
      {
        type: "scatter",
        mode: "lines",
        name: "NASA POWER, western cell (reanalysis)",
        x,
        y: c.monthly.power,
        line: { color: "--annual", width: 1.5 },
        connectgaps: false,
        hovertemplate: "%{x|%b %Y}: %{y:.2f} °C<extra>POWER</extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: `Station, excluded (< ${c.rules.min_obs_primary} obs/day)`,
        x,
        y: c.monthly.station_all.map((v, i) => (c.monthly.station_primary[i] == null ? v : null)),
        line: { color: "--muted", width: 1, dash: "dot" },
        connectgaps: false,
        hovertemplate: "%{x|%b %Y}: %{y:.2f} °C<extra>station, not used</extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "Station, used in comparison (observed)",
        x,
        y: c.monthly.station_primary,
        line: { color: "--trend", width: 1.5 },
        connectgaps: false,
        hovertemplate: "%{x|%b %Y}: %{y:.2f} °C<extra>station</extra>",
      },
    ],
    [c, x],
  );
  const layout = useMemo(() => ({ yaxis: { title: { text: "°C" } } }), []);

  return (
    <section className="card">
      <div className="card-head">
        <h2>Check against a weather station (temperature)</h2>
        <span className="badge">{dataKindLabel("observed")} vs {dataKindLabel("derived_estimate")}</span>
      </div>
      <p className="note">
        NOAA GSOD station {c.station.id} (Lucknow airport) compared with the NASA POWER grid cell that contains it (the
        western cell). This cell is used regardless of the cell selected above.
      </p>
      <Chart data={data} layout={layout} ariaLabel="Monthly mean temperature: NASA POWER western cell versus Lucknow airport station" />
      <div className="stats">
        <div className="stat">
          <div className="stat-label">Mean difference (POWER − station)</div>
          <div className="stat-value">{signed(m.mean_bias)} °C</div>
          <div className="stat-sub">
            {m.n_months} paired months, {m.first_month} to {m.last_month}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">RMSE / correlation</div>
          <div className="stat-value">
            {m.rmse.toFixed(2)} °C · r {m.pearson_r.toFixed(3)}
          </div>
          <div className="stat-sub">monthly means</div>
        </div>
        <div className="stat">
          <div className="stat-label">Anomaly correlation</div>
          <div className="stat-value">r {m.anomaly_pearson_r.toFixed(2)}</div>
          <div className="stat-sub">seasonal cycle removed</div>
        </div>
      </div>
      {t && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">
                  Trend, {t.years[0]}–{t.years[t.years.length - 1]} ({t.station.n_years} years)
                </th>
                <th scope="col">Sen's slope / decade</th>
                <th scope="col">95% CI</th>
                <th scope="col">Corrected p</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["Station (observed)", t.station],
                  ["POWER western cell", t.power],
                  ["Difference POWER − station", t.difference_power_minus_station],
                ] as const
              ).map(([name, r]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  <td className="num">{signed(r.sen_slope_per_decade)} °C</td>
                  <td className="num">
                    {signed(r.ci95_per_decade[0])} to {signed(r.ci95_per_decade[1])}
                  </td>
                  <td className={`num ${r.significant_at_0_05 ? "sig" : "nonsig"}`}>{formatP(r.modified_mk_p_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3>What this shows</h3>
      <ul className="limits diag">
        {c.diagnostics.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <h3>Limitations</h3>
      <ul className="limits">
        {c.limitations.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      <p className="notice-inline">
        <strong>Data notice:</strong> {c.licence_notice}
      </p>
    </section>
  );
}
