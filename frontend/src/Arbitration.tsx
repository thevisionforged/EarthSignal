import { useEffect, useMemo, useState } from "react";
import Chart from "./Chart";
import { Arbitration, m4Api } from "./api";
import { formatP, signed } from "./format";

export function ArbitrationCard({ area, areaLabel }: { area: string; areaLabel: string }) {
  const [state, setState] = useState<{ ok?: Arbitration; err?: string }>({});
  useEffect(() => {
    let live = true;
    setState({});
    m4Api
      .arbitration(area)
      .then((d) => live && setState({ ok: d }))
      .catch((e) => live && setState({ err: String(e.message ?? e) }));
    return () => {
      live = false;
    };
  }, [area]);

  if (state.err) return <section className="card notice">Gauge-reference check unavailable: {state.err}</section>;
  if (!state.ok) return <section className="card loading">Loading gauge-reference check…</section>;
  return <ArbitrationBody a={state.ok} areaLabel={areaLabel} />;
}

const NAMES = { merra2: "NASA POWER / MERRA-2", imerg: "GPM IMERG", imd: "IMD rain gauges (reference)" } as const;

function ArbitrationBody({ a, areaLabel }: { a: Arbitration; areaLabel: string }) {
  const x = a.annual.years;
  const lines = useMemo(
    () => [
      { type: "scatter", mode: "lines+markers", name: NAMES.imd, x, y: a.annual.imd, line: { color: "--text", width: 2.5 }, marker: { size: 5 } },
      { type: "scatter", mode: "lines+markers", name: NAMES.merra2, x, y: a.annual.merra2, line: { color: "--annual", width: 1.5 }, marker: { size: 4 } },
      { type: "scatter", mode: "lines+markers", name: NAMES.imerg, x, y: a.annual.imerg, line: { color: "--trend", width: 1.5 }, marker: { size: 4 } },
    ],
    [a, x],
  );
  const layout = useMemo(
    () => ({
      yaxis: { title: { text: "mm / year" } },
      xaxis: { dtick: 2 },
      shapes: [2006, 2014].map((yr) => ({
        type: "line", x0: yr, x1: yr, yref: "paper", y0: 0, y1: 1, line: { dash: "dot", width: 1, color: "#888" },
      })),
      annotations: [
        { x: 2006, y: 1, yref: "paper", text: "2006 CPC gauge switch", showarrow: false, xanchor: "left", font: { size: 10 } },
        { x: 2014, y: 0.92, yref: "paper", text: "2014 TRMM→GPM", showarrow: false, xanchor: "left", font: { size: 10 } },
      ],
    }),
    [],
  );
  const gauges = a.cpc_gauge_counts;
  const gaugeData = useMemo(() => {
    if (!gauges) return [];
    const byYear = new Map<number, { nb: number[]; glob: number[]; v: string }>();
    gauges.forEach((g) => {
      const y = Number(g.date.slice(0, 4));
      const r = byYear.get(y) ?? { nb: [], glob: [], v: g.version };
      r.nb.push(g.gauges_in_neighbourhood);
      r.glob.push(g.gauges_global);
      byYear.set(y, r);
    });
    const ys = [...byYear.keys()].sort();
    const mean = (v: number[]) => v.reduce((s, z) => s + z, 0) / v.length;
    return [
      { type: "bar", name: "Gauges within ±2° of the cell", x: ys, y: ys.map((y) => mean(byYear.get(y)!.nb)),
        marker: { color: ys.map((y) => (byYear.get(y)!.v === "RT" ? "--trend" : "--annual")) },
        hovertemplate: "%{x}: %{y:.1f} gauges near Lucknow<extra></extra>" },
      { type: "scatter", mode: "lines+markers", name: "Global gauges (thousands, right axis)", x: ys,
        y: ys.map((y) => mean(byYear.get(y)!.glob) / 1000), yaxis: "y2", line: { color: "--muted", width: 1.5 },
        marker: { color: "--muted", size: 4 }, hovertemplate: "%{x}: %{y:.1f}k gauges worldwide<extra></extra>" },
    ];
  }, [gauges]);
  const gaugeLayout = useMemo(
    () => ({
      yaxis: { title: { text: "gauges near Lucknow" } },
      yaxis2: { title: { text: "global (thousands)" }, overlaying: "y", side: "right", rangemode: "tozero", showgrid: false },
      xaxis: { dtick: 2 },
      margin: { l: 52, r: 52, t: 8, b: 32 },
    }),
    [],
  );

  return (
    <section className="card">
      <div className="card-head">
        <h2>Which product matches the rain gauges? ({areaLabel})</h2>
        <span className="badge">Derived statistic</span>
      </div>
      <p className="note">
        Annual rainfall totals {a.period[0]}–{a.period[1]} from all three sources over the same MERRA-2 cell. IMD's gridded
        rain-gauge analysis is used as the reference, not as truth.
      </p>
      <Chart data={lines} layout={layout} ariaLabel="Annual rainfall: IMD gauges, MERRA-2 and IMERG" />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Versus IMD gauges</th>
              <th scope="col">Annual r</th>
              <th scope="col">Mean ratio</th>
              <th scope="col">Drift (mm/yr per decade)</th>
              <th scope="col">Shift across 2006</th>
              <th scope="col">Shift across 2014</th>
            </tr>
          </thead>
          <tbody>
            {(["merra2", "imerg"] as const).map((p) => {
              const v = a.vs_reference[p];
              const b = (y: string) => {
                const br = v.breaks[y];
                return br?.available ? `${signed(br.mean_pre_mm!, 0)} → ${signed(br.mean_post_mm!, 0)} (p ${formatP(br.mann_whitney_p!)})` : "n/a";
              };
              return (
                <tr key={p}>
                  <th scope="row">{NAMES[p]}</th>
                  <td className="num">{v.annual_r.toFixed(2)}</td>
                  <td className="num">× {v.mean_ratio.toFixed(2)}</td>
                  <td className={`num ${v.difference_trend.significant_at_0_05 ? "sig" : "nonsig"}`}>
                    {signed(v.difference_trend.sen_slope_per_decade, 0)} (p {formatP(v.difference_trend.modified_mk_p_value)})
                  </td>
                  <td className="num">{b("2006")}</td>
                  <td className="num">{b("2014")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h3>What this shows</h3>
      <ul className="limits diag">
        {a.verdicts.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      {gauges && (
        <>
          <h3>Rain gauges behind MERRA-2's correction (CPC Unified, sampled monsoon days)</h3>
          <Chart data={gaugeData} layout={gaugeLayout} ariaLabel="CPC gauge counts near Lucknow by year" small />
          <p className="note">
            Gauges in the CPC Unified analysis (the input to MERRA-2's corrected precipitation over land, NASA
            TM-2014-104606 Vol. 35), averaged over 15 July and 15 August each year. Bar colour marks the CPC version:
            retrospective (to 2005) and real-time (from 2006). The global network halves at 2006, but the count near Lucknow
            does not change. A loss of local gauges therefore does not explain the 2006 shift. The rise from 2016 was not
            a pre-registered date and is not tested.
          </p>
        </>
      )}
      <details>
        <summary>Method and caveats</summary>
        <ul className="limits">
          {a.method.map((m) => (
            <li key={m}>{m}</li>
          ))}
          {a.reference_metadata.quality_limitations.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
        <p className="note">Reference citation: {a.reference_metadata.citation}</p>
      </details>
    </section>
  );
}
