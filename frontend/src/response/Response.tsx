import { useCallback, useEffect, useMemo, useState } from "react";
import Chart from "../Chart";
import { ACTION_LABEL, EventRow, eventTitle, frequencyText, needsReason, severityText, sortEvents, SortKey, STATUS_LABEL, verdictLabel } from "./logic";
import "./response.css";

interface EventsRes {
  events: EventRow[];
  per_year: { years: number[]; counts: number[] };
  threshold: { kind: string; value?: number; values?: number[]; units: string };
  explain: string;
  method: string[];
  note: string;
}
interface Check { label: string; verdict: string; detail: string; independent: boolean }
interface Investigation {
  event: EventRow;
  summary: string;
  checks: Check[];
  corroboration: { independent_corroborated: number; independent_available: number; independent_total: number; other_cell_agrees: boolean };
  window: { dates: string[]; values: (number | null)[]; threshold: number[]; units: string };
  method: string[];
  data: string[];
  explain: string;
}
interface Case {
  id: string;
  title: string;
  status: string;
  event: EventRow;
  evidence_snapshot: Investigation;
  notes: { at: string; text: string }[];
  audit: { at: string; action: string; from?: string; status: string; note?: string }[];
  updated_at: string;
}
interface CasesRes { cases: Case[]; statuses: Record<string, string>; transitions: Record<string, string[]> }

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let d = res.statusText;
    try {
      d = (await res.json()).detail ?? d;
    } catch {
      /* non-JSON */
    }
    throw new Error(typeof d === "string" ? d : JSON.stringify(d));
  }
  return res.json() as Promise<T>;
}
const post = <T,>(url: string, body: unknown) => call<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const STEPS = [
  { n: 1, title: "Detect", plain: "Scan 45 years of NASA data for unusually hot spells and extreme rainfall." },
  { n: 2, title: "Investigate", plain: "Check each event against independent sources: a weather station, satellite rain and rain gauges." },
  { n: 3, title: "Respond", plain: "Open a case, record a decision with a reason, and export an evidence brief for review." },
];

export function ResponseView() {
  const [area, setArea] = useState("lucknow");
  const [kind, setKind] = useState<"heat" | "rain">("heat");
  const [sort, setSort] = useState<SortKey>("severity");
  const [events, setEvents] = useState<EventsRes | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<EventRow | null>(null);
  const [inv, setInv] = useState<Investigation | null>(null);
  const [cases, setCases] = useState<CasesRes | null>(null);
  const [activeCase, setActiveCase] = useState<string | null>(null);
  const step = activeCase ? 3 : selected ? 2 : 1;

  const loadCases = useCallback(() => call<CasesRes>("/api/cases").then(setCases).catch((e) => setErr(String(e.message))), []);
  useEffect(() => {
    loadCases();
  }, [loadCases]);
  useEffect(() => {
    setEvents(null);
    setSelected(null);
    setInv(null);
    call<EventsRes>(`/api/response/events?area=${area}&kind=${kind}`).then(setEvents).catch((e) => setErr(String(e.message)));
  }, [area, kind]);
  useEffect(() => {
    if (!selected) return;
    setInv(null);
    call<Investigation>(`/api/response/investigate?area=${selected.area}&kind=${selected.kind}&event_id=${encodeURIComponent(selected.id)}`)
      .then(setInv)
      .catch((e) => setErr(String(e.message)));
  }, [selected]);

  const openCase = async () => {
    if (!selected) return;
    try {
      const c = await post<Case>("/api/cases", { area: selected.area, kind: selected.kind, event_id: selected.id });
      await loadCases();
      setActiveCase(c.id);
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };

  const existingCase = selected && cases ? cases.cases.find((c) => c.event.id === selected.id) : undefined;

  return (
    <section className="ri" aria-label="Response Intelligence">
      <header className="ri-head">
        <p className="ri-eyebrow">RESPONSE INTELLIGENCE</p>
        <h1>From detection to decision</h1>
        <p className="ri-plain">
          <b>In plain English:</b> EarthSignal finds unusual weather events in Lucknow’s NASA record, checks whether other
          sources saw the same thing, and lets an analyst record a reasoned decision. It is an <b>analyst’s case file</b>, not a
          public warning system, and it makes no forecasts.
        </p>
      </header>

      <ol className="stepper">
        {STEPS.map((s) => (
          <li key={s.n} className={s.n === step ? "on" : s.n < step ? "done" : ""}>
            <span className="num">{s.n}</span>
            <span>
              <b>{s.title}</b>
              <br />
              <small>{s.plain}</small>
            </span>
          </li>
        ))}
      </ol>
      {err && (
        <p className="ri-err" role="alert">
          {err} <button className="linkish" onClick={() => setErr(null)}>dismiss</button>
        </p>
      )}

      <div className="ri-grid">
        {/* ---------------- STEP 1: DETECT */}
        <section className="card ri-card">
          <h2>1 · Detect</h2>
          <div className="ri-controls">
            <div className="seg-l" role="group" aria-label="Event type">
              <button aria-pressed={kind === "heat"} onClick={() => setKind("heat")}>Heat episodes</button>
              <button aria-pressed={kind === "rain"} onClick={() => setKind("rain")}>Extreme rainfall</button>
            </div>
            <div className="seg-l" role="group" aria-label="Grid cell">
              <button aria-pressed={area === "lucknow"} onClick={() => setArea("lucknow")}>Eastern cell (city centre)</button>
              <button aria-pressed={area === "lucknow_airport"} onClick={() => setArea("lucknow_airport")}>Western cell (airport)</button>
            </div>
          </div>
          {events && <p className="ri-explain"><b>What counts as an event:</b> {events.explain}</p>}
          {events && <YearChart ev={events} kind={kind} />}
          {events && (
            <>
              <div className="ri-listhead">
                <b>{events.events.length} events found</b>
                <span>
                  Sort:{" "}
                  <button className="linkish" aria-pressed={sort === "severity"} onClick={() => setSort("severity")}>most severe</button> ·{" "}
                  <button className="linkish" aria-pressed={sort === "recent"} onClick={() => setSort("recent")}>most recent</button>
                </span>
              </div>
              <ul className="ri-events">
                {sortEvents(events.events, sort).slice(0, 25).map((e) => (
                  <li key={e.id}>
                    <button className={selected?.id === e.id ? "sel" : ""} onClick={() => { setSelected(e); setActiveCase(null); }}>
                      <span className="rank">#{e.rank}</span>
                      <span className="what">{eventTitle(e)}</span>
                      <span className="sev">{severityText(e)}</span>
                      {e.provisional && <span className="prov">provisional data</span>}
                      {cases?.cases.some((c) => c.event.id === e.id) && <span className="hascase">has a case</span>}
                    </button>
                  </li>
                ))}
              </ul>
              <p className="note">Showing up to 25. {events.note}</p>
            </>
          )}
          {!events && !err && <p className="loading">Scanning the record…</p>}
        </section>

        {/* ---------------- STEP 2: INVESTIGATE */}
        <section className="card ri-card">
          <h2>2 · Investigate</h2>
          {!selected && <p className="ri-empty">Choose an event on the left to see its evidence.</p>}
          {selected && !inv && <p className="loading">Gathering evidence…</p>}
          {inv && (
            <>
              <h3 className="ri-title">{eventTitle(inv.event)}</h3>
              <p className="ri-summary">{inv.summary}</p>
              <WindowChart inv={inv} />
              <h3 className="ri-sub">Cross-checks</h3>
              <ul className="checks">
                {inv.checks.map((c) => (
                  <li key={c.label} className={c.verdict}>
                    <span className="badge-v">{verdictLabel(c.verdict)}</span>
                    <b>{c.label}</b>
                    <br />
                    <small>{c.detail}</small>
                  </li>
                ))}
              </ul>
              <p className="note">{frequencyText(inv.event)} Ranking and frequency describe this record only, not future chances.</p>
              <details>
                <summary>How this was worked out</summary>
                <ul className="limits">{inv.method.map((m) => <li key={m}>{m}</li>)}</ul>
                <p className="note">Data: {inv.data.join("; ")}</p>
              </details>
              <div className="ri-actions">
                {existingCase ? (
                  <button className="ri-btn" onClick={() => setActiveCase(existingCase.id)}>Go to {existingCase.id} →</button>
                ) : (
                  <button className="ri-btn" onClick={openCase}>Open a case for this event →</button>
                )}
              </div>
            </>
          )}
        </section>

        {/* ---------------- STEP 3: RESPOND */}
        <section className="card ri-card ri-wide">
          <h2>3 · Respond</h2>
          {cases && <CasePanel cases={cases} activeId={activeCase} setActive={setActiveCase} reload={loadCases} onError={setErr} />}
        </section>
      </div>
    </section>
  );
}

function YearChart({ ev, kind }: { ev: EventsRes; kind: string }) {
  const data = useMemo(() => [{ type: "bar", x: ev.per_year.years, y: ev.per_year.counts, marker: { color: kind === "heat" ? "--trend" : "--annual" }, hovertemplate: "%{x}: %{y} event(s)<extra></extra>" }], [ev, kind]);
  return (
    <>
      <p className="chart-title">Events per year</p>
      <Chart small data={data} layout={{ showlegend: false, yaxis: { title: { text: "events" } } }} ariaLabel="Detected events per year" />
    </>
  );
}

function WindowChart({ inv }: { inv: Investigation }) {
  const x = inv.window.dates;
  const data = useMemo(
    () => [
      inv.event.kind === "heat"
        ? { type: "scatter", mode: "lines+markers", name: "Daily mean temperature", x, y: inv.window.values, line: { color: "--trend" }, marker: { size: 4 } }
        : { type: "bar", name: "Daily rainfall", x, y: inv.window.values, marker: { color: "--annual" } },
      { type: "scatter", mode: "lines", name: inv.event.kind === "heat" ? "Unusual-heat line (95th pct for the date)" : "Extreme-rain line (99th pct)", x, y: inv.window.threshold, line: { color: "--muted", dash: "dash" } },
    ],
    [inv, x],
  );
  const layout = useMemo(
    () => ({
      yaxis: { title: { text: inv.window.units } },
      shapes: [{ type: "rect", xref: "x", yref: "paper", x0: inv.event.start, x1: inv.event.end, y0: 0, y1: 1, fillcolor: "rgba(194,80,44,0.12)", line: { width: 0 } }],
    }),
    [inv],
  );
  return <Chart small data={data} layout={layout} ariaLabel="The event with two weeks either side, against its threshold" />;
}

function CasePanel({ cases, activeId, setActive, reload, onError }: { cases: CasesRes; activeId: string | null; setActive: (id: string | null) => void; reload: () => Promise<void>; onError: (s: string) => void }) {
  const active = cases.cases.find((c) => c.id === activeId) ?? null;
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  useEffect(() => {
    setReason("");
    setNote("");
  }, [activeId]);

  const move = async (to: string) => {
    if (!active) return;
    try {
      await post(`/api/cases/${active.id}/status`, { to, note: reason });
      setReason("");
      await reload();
    } catch (e) {
      onError(String((e as Error).message));
    }
  };
  const addNote = async () => {
    if (!active || !note.trim()) return;
    try {
      await post(`/api/cases/${active.id}/notes`, { text: note });
      setNote("");
      await reload();
    } catch (e) {
      onError(String((e as Error).message));
    }
  };

  return (
    <div className="cases">
      <div className="case-list">
        <p className="ri-plain"><b>Cases</b> are an analyst’s working records. They are stored only on this computer.</p>
        {cases.cases.length === 0 && <p className="ri-empty">No cases yet. Open one from an event in step 2.</p>}
        <ul>
          {cases.cases.map((c) => (
            <li key={c.id}>
              <button className={c.id === activeId ? "sel" : ""} onClick={() => setActive(c.id)}>
                <b>{c.id}</b> {c.title}
                <span className={`status s-${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="case-detail">
        {!active && <p className="ri-empty">Select a case to record a decision.</p>}
        {active && (
          <>
            <h3 className="ri-title">
              {active.id}: {active.title} <span className={`status s-${active.status}`}>{STATUS_LABEL[active.status]}</span>
            </h3>
            <p className="note">{cases.statuses[active.status]}</p>
            <p className="ri-summary small">{active.evidence_snapshot.summary}</p>
            <label className="ri-field">
              Reason for the decision (required to confirm, dismiss, flag or escalate)
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} rows={2} placeholder="e.g. Airport station and IMD gauges both recorded the extreme." />
            </label>
            <div className="ri-actions wrap">
              {(cases.transitions[active.status] ?? []).map((to) => {
                const blocked = needsReason(active.status, to) && reason.trim().length < 5;
                return (
                  <button key={to} className={`ri-btn ${to}`} disabled={blocked} title={blocked ? "Write a reason first" : cases.statuses[to]} onClick={() => move(to)}>
                    {ACTION_LABEL[to] ?? to}
                  </button>
                );
              })}
            </div>
            <label className="ri-field">
              Add a note
              <span className="note-row">
                <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Anything worth recording" />
                <button className="ri-btn ghost" onClick={addNote} disabled={!note.trim()}>Add</button>
              </span>
            </label>
            <h3 className="ri-sub">Audit trail</h3>
            <ol className="audit">
              {active.audit.map((a, i) => (
                <li key={i}>
                  <span className="at">{a.at.replace("T", " ").replace("+00:00", " UTC")}</span> {a.action === "status" ? `${STATUS_LABEL[a.from ?? ""] ?? a.from} → ${STATUS_LABEL[a.status]}` : a.action === "note" ? "Note added" : "Case opened"}
                  {a.note ? <em>: {a.note}</em> : null}
                </li>
              ))}
            </ol>
            <a className="ri-btn link" href={`/api/cases/${active.id}/brief`} download>⬇ Download evidence brief (Markdown)</a>
          </>
        )}
      </div>
    </div>
  );
}
