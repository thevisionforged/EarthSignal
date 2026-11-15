import { useEffect, useMemo, useState } from "react";
import Chart from "../Chart";
import { baselineSkill, departureWords, ForecastDay, isoToday, LeadResult, mean, METHOD_LABEL, pct, splitByToday, weekSummary } from "./logic";
import "./forecast.css";

interface ForecastRes {
  area: string;
  units: string;
  data_kind: string;
  evaluation: { per_lead: LeadResult[]; horizon_days: number; n_passing: number; dev_years: number[]; holdout_years: number[] };
  forecast: { origin: string; origin_value: number; days: ForecastDay[]; recent: { dates: string[]; values: (number | null)[] } } | null;
  origin_provisional: boolean | null;
  no_forecast_reason: string | null;
  data_version: { dataset_id: string; retrieved_at_utc: string; api_version: string };
  method: string[];
  limitations: string[];
}

export function ForecastView() {
  const [area, setArea] = useState("lucknow");
  const [res, setRes] = useState<ForecastRes | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const today = isoToday();

  useEffect(() => {
    setRes(null);
    setErr(null);
    fetch(`/api/forecast?area=${area}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
        return r.json();
      })
      .then(setRes)
      .catch((e) => setErr(String(e.message)));
  }, [area]);

  return (
    <section className="fc" aria-label="Anticipate: temperature forecast">
      <header>
        <p className="fc-eyebrow">ANTICIPATE</p>
        <h1>Temperature outlook for the coming weeks</h1>
        <p className="fc-plain">
          <b>In plain English:</b> from the latest NASA data, EarthSignal estimates Lucknow’s daily average temperature for the next few
          weeks. We only show it because it passed a fair test set in advance: on 12 years it had never seen, it beat the best simple
          method. It is a statistical outlook, <b>not an official weather forecast</b>. IMD forecasts always come first.
        </p>
      </header>
      <div className="seg-l fc-cells" role="group" aria-label="Grid cell">
        <button aria-pressed={area === "lucknow"} onClick={() => setArea("lucknow")}>Eastern cell (city centre)</button>
        <button aria-pressed={area === "lucknow_airport"} onClick={() => setArea("lucknow_airport")}>Western cell (airport)</button>
      </div>
      {err && <p className="fc-err" role="alert">{err}</p>}
      {!res && !err && <p className="loading">Running the forecast test (about 10 seconds the first time)…</p>}
      {res && <Body res={res} today={today} />}
    </section>
  );
}

function Body({ res, today }: { res: ForecastRes; today: string }) {
  const fcst = res.forecast;
  const ev = res.evaluation;
  const split = fcst ? splitByToday(fcst.days, today) : { past: [], future: [] };
  const week = weekSummary(split.future.slice(0, 7));
  return (
    <>
      <div className="fc-badges">
        <span className="badge forecast">FORECAST</span>
        <span className="badge">statistical · NASA POWER daily mean 2 m temperature</span>
        {res.origin_provisional && <span className="badge warn">starts from provisional data</span>}
      </div>

      {!fcst && (
        <section className="card">
          <h2>No forecast shown</h2>
          <p>{res.no_forecast_reason} The scorecard below shows the test results.</p>
        </section>
      )}

      {fcst && (
        <>
          <div className="fc-kpis">
            <div className="card fc-kpi">
              <p className="lbl">Next 7 days, average</p>
              <p className="num">{week ? `${week.forecast.toFixed(1)} °C` : "–"}</p>
              <p className="sub">{week ? `${week.diff >= 0 ? "+" : ""}${week.diff.toFixed(1)} °C vs usual (${week.usual.toFixed(1)} °C): ${departureWords(week.diff)}` : "No future days in the outlook."}</p>
            </div>
            <div className="card fc-kpi">
              <p className="lbl">Outlook length</p>
              <p className="num">{ev.horizon_days} days</p>
              <p className="sub">The test passed for every lead from 1 to {ev.horizon_days} days ahead.</p>
            </div>
            <div className="card fc-kpi">
              <p className="lbl">Based on NASA data up to</p>
              <p className="num">{fcst.origin}</p>
              <p className="sub">
                {split.past.length > 0
                  ? `${split.past.length} forecast day(s) are already past and waiting for NASA data (the data runs a few days behind).`
                  : "NASA data runs a few days behind real time."}
              </p>
            </div>
          </div>
          <section className="card">
            <h2>The outlook</h2>
            <OutlookChart res={res} today={today} />
            <p className="note">
              Shaded band: where 90% of past forecasts at the same lead landed (5th–95th percentile of 2014–2025 errors). In earlier years
              ({ev.dev_years[0]}–{ev.dev_years[1]}) the band contained the actual value {pct(mean(ev.per_lead.map((r) => r.band_coverage_dev)))} of the time.
            </p>
            <DayTable days={fcst.days} today={today} />
            <a className="fc-csv" href={`/api/forecast?area=${res.area}&format=csv`} download>⬇ Download the forecast (CSV)</a>
          </section>
        </>
      )}

      <section className="card">
        <h2>How we know it works</h2>
        <p className="fc-plain">
          We wrote the test down before running it (decision D-026): two candidate methods were compared on {ev.dev_years[0]}–{ev.dev_years[1]},
          and the better one was then judged <b>once</b> on {ev.holdout_years[0]}–{ev.holdout_years[1]} against “damped persistence”, the
          strongest simple method. <b>{ev.n_passing} of 30</b> lead times passed.
        </p>
        <SkillChart ev={ev} />
        <p className="note">
          Higher is better. 0% = no better than the usual temperature for the date; 100% = perfect. The gain over damped persistence is real
          but modest, and beyond about two weeks both are close to the seasonal average.
        </p>
        <Scorecard ev={ev} />
      </section>

      <details className="card">
        <summary>Method, limitations and data</summary>
        <h3>Method</h3>
        <ul className="limits">{res.method.map((m) => <li key={m}>{m}</li>)}</ul>
        <h3>Limitations</h3>
        <ul className="limits">{res.limitations.map((m) => <li key={m}>{m}</li>)}</ul>
        <p className="note">
          Data: NASA POWER {res.data_version.dataset_id} (retrieved {res.data_version.retrieved_at_utc.slice(0, 10)}, API {res.data_version.api_version}).
          Values are reanalysis estimates, not thermometer readings.
        </p>
      </details>
    </>
  );
}

function OutlookChart({ res, today }: { res: ForecastRes; today: string }) {
  const f = res.forecast!;
  const data = useMemo(() => {
    const x = [f.origin, ...f.days.map((d) => d.date)];
    const y = [f.origin_value, ...f.days.map((d) => d.forecast)];
    return [
      { type: "scatter", mode: "lines", x: f.recent.dates, y: f.recent.values, name: "Recent (NASA data)", line: { color: "--text", width: 2 } },
      { type: "scatter", mode: "lines", x: f.days.map((d) => d.date), y: f.days.map((d) => d.high), line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
      { type: "scatter", mode: "lines", x: f.days.map((d) => d.date), y: f.days.map((d) => d.low), fill: "tonexty", fillcolor: "rgba(31,111,92,0.18)", line: { width: 0 }, name: "90% range" },
      { type: "scatter", mode: "lines", x, y, name: "Forecast", line: { color: "--accent", width: 3 } },
      { type: "scatter", mode: "lines", x: [...f.recent.dates, ...f.days.map((d) => d.date)], y: [...f.recent.dates.map(() => null), ...f.days.map((d) => d.climatology)], name: "Usual for the date", line: { color: "--muted", dash: "dot" } },
    ];
  }, [f]);
  const layout = useMemo(
    () => ({
      yaxis: { title: { text: "°C (daily mean)" } },
      legend: { orientation: "h", y: -0.2 },
      shapes: [{ type: "line", xref: "x", yref: "paper", x0: today, x1: today, y0: 0, y1: 1, line: { color: "#C2502C", width: 1, dash: "dash" } }],
      annotations: [{ x: today, y: 1, xref: "x", yref: "paper", text: "today", showarrow: false, yanchor: "bottom", font: { size: 11, color: "#C2502C" } }],
    }),
    [today],
  );
  return <Chart data={data} layout={layout} ariaLabel="Recent temperatures, the forecast with its 90% range, and the usual temperature for each date" />;
}

function DayTable({ days, today }: { days: ForecastDay[]; today: string }) {
  return (
    <div className="fc-table-wrap">
      <table className="fc-table">
        <thead>
          <tr><th>Date</th><th>Forecast</th><th>90% range</th><th>Usual</th><th></th></tr>
        </thead>
        <tbody>
          {days.slice(0, 14).map((d) => (
            <tr key={d.date} className={d.date < today ? "past" : ""}>
              <td>{d.date}</td>
              <td><b>{d.forecast.toFixed(1)} °C</b></td>
              <td>{d.low.toFixed(1)}–{d.high.toFixed(1)}</td>
              <td>{d.climatology.toFixed(1)}</td>
              <td className="tag">{d.date < today ? "already past: awaiting NASA data" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {days.length > 14 && <p className="note">Showing 14 of {days.length} days; the CSV has all of them.</p>}
    </div>
  );
}

function SkillChart({ ev }: { ev: ForecastRes["evaluation"] }) {
  const data = useMemo(() => {
    const x = ev.per_lead.map((r) => r.lead_days);
    return [
      { type: "scatter", mode: "lines+markers", x, y: ev.per_lead.map((r) => r.holdout.skill_vs_climatology * 100), name: "EarthSignal forecast", line: { color: "--accent", width: 3 }, marker: { size: 5, color: ev.per_lead.map((r) => (r.passes ? "--accent" : "#C2502C")) } },
      { type: "scatter", mode: "lines", x, y: ev.per_lead.map((r) => baselineSkill(r) * 100), name: "Damped persistence (bar to beat)", line: { color: "--muted", dash: "dash" } },
    ];
  }, [ev]);
  return (
    <Chart
      small
      data={data}
      layout={{ xaxis: { title: { text: "days ahead" } }, yaxis: { title: { text: "skill vs usual temperature (%)" } }, legend: { orientation: "h", y: -0.3 } }}
      ariaLabel="Forecast skill by lead time compared with damped persistence"
    />
  );
}

function Scorecard({ ev }: { ev: ForecastRes["evaluation"] }) {
  const show = ev.per_lead.filter((r) => [1, 2, 3, 5, 7, 10, 14, 21, 30].includes(r.lead_days) || !r.passes);
  return (
    <div className="fc-table-wrap">
      <table className="fc-table">
        <thead>
          <tr><th>Days ahead</th><th>Method chosen</th><th>Typical error (RMSE)</th><th>Bar to beat</th><th>Improvement</th><th>Result</th></tr>
        </thead>
        <tbody>
          {show.map((r) => (
            <tr key={r.lead_days}>
              <td>{r.lead_days}</td>
              <td>{METHOD_LABEL[r.chosen] ?? r.chosen}</td>
              <td>{r.holdout.rmse.chosen.toFixed(2)} °C</td>
              <td>{r.holdout.rmse.baseline.toFixed(2)} °C</td>
              <td>{pct(r.holdout.skill_vs_baseline, 1)}</td>
              <td className={r.passes ? "pass" : "fail"}>{r.passes ? "Passed" : "Did not pass"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">Selected lead times shown, plus every lead that failed. “Improvement” = reduction in mean squared error vs the bar to beat, on the 2014–2025 hold-out years.</p>
    </div>
  );
}
