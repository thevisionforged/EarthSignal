import { ReactNode, useEffect, useState } from "react";
import { ApiError } from "../api";
import { clampStep, deleteConfig, loadSaved, Params, saveConfig, SavedConfig, simUrl } from "./logic";

export interface Field {
  key: string;
  label: string;
  kind: "slider" | "number" | "select" | "text";
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  options?: { value: string; label: string }[];
  help?: string;
}

export interface SimEnvelope {
  inputs: Record<string, unknown>;
  data_version: { dataset_id: string; retrieved_at_utc: string; api_version: string; time_standard: string; provider: string };
  years_used: number[];
  years_excluded: number[];
  data_kind: string;
  formulas: Record<string, string>;
  limitations: string[];
  label_note?: string;
  method?: string;
}

export const AREA_FIELD: Field = {
  key: "area", label: "Study area (POWER grid cell)", kind: "select",
  options: [{ value: "lucknow", label: "Eastern cell (city centre)" }, { value: "lucknow_airport", label: "Western cell (airport)" }],
};
export const START_FIELD: Field = { key: "start_year", label: "Baseline start year", kind: "number", min: 1981, max: 2025, step: 1 };
export const END_FIELD: Field = { key: "end_year", label: "Baseline end year", kind: "number", min: 1981, max: 2025, step: 1 };

interface Props<T> {
  tool: string;
  title: string;
  question: string;
  fields: Field[];
  defaults: Params;
  presets?: { label: string; params: Params }[];
  render: (data: T, applied: Params) => ReactNode;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export function ToolFrame<T extends SimEnvelope>({ tool, title, question, fields, defaults, presets, render }: Props<T>) {
  const [draft, setDraft] = useState<Params>(defaults);
  const [applied, setApplied] = useState<Params>(defaults);
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [saved, setSaved] = useState<SavedConfig[]>(() => loadSaved().filter((s) => s.tool === tool));
  const [saveName, setSaveName] = useState("");
  const dirty = JSON.stringify(draft) !== JSON.stringify(applied);

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    getJson<T>(simUrl(tool, applied))
      .then((data) => live && setState({ data, loading: false }))
      .catch((e) => live && setState({ error: String(e.message ?? e), loading: false }));
    return () => {
      live = false;
    };
  }, [tool, applied]);

  const set = (f: Field, raw: string) => {
    let v: string | number = raw;
    if (f.kind === "slider" || f.kind === "number") {
      v = clampStep(Number(raw), f.min ?? -Infinity, f.max ?? Infinity, f.step ?? 1);
    }
    setDraft((d) => ({ ...d, [f.key]: v }));
  };

  const doSave = () => {
    const name = saveName.trim() || `${title} ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;
    saveConfig({ name, tool, params: draft, savedAt: new Date().toISOString() });
    setSaved(loadSaved().filter((s) => s.tool === tool));
    setSaveName("");
  };

  return (
    <div className="tool">
      <div className="tool-head">
        <h2>{title}</h2>
        <p className="tool-q">{question}</p>
      </div>
      <div className="tool-body">
        <aside className="controls" aria-label={`${title} controls`}>
          {presets && (
            <div className="presets" role="group" aria-label="Presets">
              {presets.map((p) => (
                <button key={p.label} className="chip" onClick={() => setDraft((d) => ({ ...d, ...p.params }))}>
                  {p.label}
                </button>
              ))}
            </div>
          )}
          {fields.map((f) => (
            <label key={f.key} className="field">
              <span className="field-label">
                {f.label}
                {f.kind === "slider" && (
                  <b className="field-value">
                    {String(draft[f.key])}
                    {f.unit ? ` ${f.unit}` : ""}
                  </b>
                )}
              </span>
              {f.kind === "select" ? (
                <select value={String(draft[f.key])} onChange={(e) => set(f, e.target.value)}>
                  {f.options!.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : f.kind === "text" ? (
                <input type="text" maxLength={60} value={String(draft[f.key])} onChange={(e) => set(f, e.target.value)} />
              ) : f.kind === "slider" ? (
                <input type="range" min={f.min} max={f.max} step={f.step} value={Number(draft[f.key])} onChange={(e) => set(f, e.target.value)} />
              ) : (
                <input type="number" min={f.min} max={f.max} step={f.step} value={Number(draft[f.key])} onChange={(e) => set(f, e.target.value)} />
              )}
              {f.help && <span className="field-help">{f.help}</span>}
            </label>
          ))}
          <div className="actions">
            <button className="run" onClick={() => setApplied(draft)} disabled={!dirty && !state.error}>
              {state.loading ? "Running…" : "Run experiment"}
            </button>
            <button
              className="ghost"
              onClick={() => {
                setDraft(defaults);
                setApplied(defaults);
              }}
            >
              Reset
            </button>
          </div>
          {dirty && <p className="pending">Inputs changed: press Run experiment to update the results.</p>}
          <a className="csv" href={simUrl(tool, applied, "csv")} download>
            ⬇ Download results (CSV)
          </a>
          <details className="saved">
            <summary>Saved configurations ({saved.length})</summary>
            <div className="save-row">
              <input type="text" placeholder="Name this configuration" value={saveName} maxLength={60} onChange={(e) => setSaveName(e.target.value)} />
              <button className="ghost" onClick={doSave}>
                Save
              </button>
            </div>
            <p className="field-help">Stored only in this browser. Nothing is sent to a server.</p>
            {saved.map((s) => (
              <div key={s.name} className="saved-item">
                <button className="linkish" onClick={() => setDraft({ ...defaults, ...s.params })}>
                  {s.name}
                </button>
                <button
                  className="linkish danger"
                  aria-label={`Delete ${s.name}`}
                  onClick={() => {
                    deleteConfig(tool, s.name);
                    setSaved(loadSaved().filter((x) => x.tool === tool));
                  }}
                >
                  ✕
                </button>
              </div>
            ))}
          </details>
        </aside>
        <section className="results" aria-live="polite">
          {state.error && <p className="err">Could not run: {state.error}</p>}
          {state.data && (
            <>
              <div className={`kind ${state.data.data_kind}`}>
                {state.data.data_kind === "hypothetical"
                  ? "HYPOTHETICAL: historical record with a uniform change applied (not a forecast or projection)"
                  : "DERIVED STATISTIC from the historical record"}
              </div>
              {render(state.data, applied)}
              {state.data.label_note && <p className="amber-note">{state.data.label_note}</p>}
              <Disclosure d={state.data} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Disclosure({ d }: { d: SimEnvelope }) {
  return (
    <details className="disclosure">
      <summary>Methodology, formulas, limitations and provenance</summary>
      {d.method && <p>{d.method}</p>}
      <ul>
        {Object.entries(d.formulas).map(([k, v]) => (
          <li key={k}>
            <code>{v}</code>
          </li>
        ))}
      </ul>
      <h4>Limitations</h4>
      <ul>
        {d.limitations.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      <h4>Provenance</h4>
      <p>
        {d.data_version.provider}; dataset <code>{d.data_version.dataset_id}</code>, POWER API {d.data_version.api_version}, retrieved{" "}
        {d.data_version.retrieved_at_utc.slice(0, 19).replace("T", " ")} UTC, daily values in {d.data_version.time_standard}. Years used:{" "}
        {d.years_used.length ? `${d.years_used[0]}–${d.years_used[d.years_used.length - 1]} (${d.years_used.length})` : "none"}
        {d.years_excluded.length ? `; excluded as incomplete: ${d.years_excluded.join(", ")}` : ""}.
      </p>
      <p>Reproduce: the same inputs and the same dataset id give identical results. Inputs: <code>{JSON.stringify(d.inputs)}</code></p>
    </details>
  );
}

export function Kpi({ label, base, scen, unit, digits = 1, pct }: { label: string; base: number | null; scen: number | null; unit: string; digits?: number; pct?: number | null }) {
  const diff = base !== null && scen !== null ? scen - base : null;
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-row">
        <span className="kpi-base">{base === null ? "n/a" : base.toFixed(digits)}</span>
        <span className="kpi-arrow">→</span>
        <span className="kpi-scen">{scen === null ? "n/a" : scen.toFixed(digits)}</span>
        <span className="kpi-unit">{unit}</span>
      </div>
      <div className="kpi-diff">
        {diff === null ? "" : `${diff > 0 ? "+" : ""}${diff.toFixed(digits)} ${unit}`}
        {pct !== null && pct !== undefined ? ` (${pct > 0 ? "+" : ""}${pct.toFixed(1)}%)` : ""}
      </div>
    </div>
  );
}
