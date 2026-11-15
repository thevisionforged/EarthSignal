import { useEffect, useState } from "react";
import { api, m4Api, multiApi } from "./api";
import { Finding, rainfallFinding, stationFinding, temperatureFinding } from "./findings";

type State = { findings: Finding[]; nSources: number } | { error: string } | null;

export function OverviewView({ go }: { go: (view: "analysis" | "sources") => void }) {
  const [state, setState] = useState<State>(null);
  useEffect(() => {
    let live = true;
    Promise.all([
      api.trend("lucknow", "T2M"),
      api.trend("lucknow_airport", "T2M"),
      api.stationComparison(),
      m4Api.arbitration("lucknow"),
      m4Api.arbitration("lucknow_airport"),
      multiApi.sources(),
    ])
      .then(([te, tw, st, ae, aw, src]) => {
        if (!live) return;
        const findings: Finding[] = [temperatureFinding(te.result, tw.result)];
        if (st.trend_comparison) {
          findings.push(stationFinding(st.trend_comparison.difference_power_minus_station, st.trend_comparison.years));
        }
        findings.push(rainfallFinding(ae, aw));
        setState({ findings, nSources: src.length });
      })
      .catch((e) => live && setState({ error: String(e.message ?? e) }));
    return () => {
      live = false;
    };
  }, []);

  return (
    <>
      <section className="card hero">
        <h2>What EarthSignal found for Lucknow</h2>
        <p className="note">
          Each finding below is generated from the live analysis results. Nothing is typed in by hand. Every number traces
          back to a stored NASA, NOAA or IMD download with its provenance.
        </p>
        {state === null && <p className="loading">Computing findings…</p>}
        {state && "error" in state && <p className="notice-inline">Findings unavailable: {state.error}</p>}
        {state && "findings" in state && (
          <ol className="findings">
            {state.findings.map((f) => (
              <li key={f.key}>
                <p className="finding-head">{f.headline}</p>
                <p className="note">{f.evidence}</p>
                <button className="linkish" onClick={() => go(f.view)}>
                  See the evidence →
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>
      <section className="card">
        <h2>How it works</h2>
        <ul className="limits">
          <li>
            <strong>Data:</strong> NASA POWER (MERRA-2 reanalysis, temperature and rainfall, 1981–present) and NASA GPM IMERG
            (satellite rainfall), cross-checked against NOAA airport-station temperature and IMD rain-gauge grids
            {state && "nSources" in state ? `: ${state.nSources} datasets in total` : ""}.
          </li>
          <li>
            <strong>Provenance:</strong> raw downloads are kept unmodified with checksums. Each dataset records its source,
            version, units, coverage and processing steps.
          </li>
          <li>
            <strong>Statistics:</strong> trends use a Mann-Kendall test corrected for year-to-year correlation, robustness
            windows, a multiple-testing correction for seasons, and break dates fixed in advance from documentation.
          </li>
          <li>
            <strong>Honesty:</strong> values are labelled as reanalysis, satellite, gauge-grid or station data. Results that
            fail robustness checks are reported as such. No forecasts are shown.
          </li>
        </ul>
      </section>
    </>
  );
}
