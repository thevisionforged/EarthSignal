import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-basic-dist-min";

interface Props {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
  ariaLabel: string;
  small?: boolean;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Re-renders when the OS colour scheme changes, so chart colours follow the page theme. */
function useColorSchemeVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const bump = () => setVersion((v) => v + 1);
    mq.addEventListener("change", bump);
    return () => mq.removeEventListener("change", bump);
  }, []);
  return version;
}

/** Trace colours may be given as CSS custom-property names (e.g. "--trend"); resolve them here. */
function resolveColors(trace: Record<string, unknown>): Record<string, unknown> {
  const out = { ...trace };
  const fix = (part: Record<string, unknown> | undefined) => {
    if (!part) return part;
    const next = { ...part };
    if (typeof next.color === "string" && next.color.startsWith("--")) next.color = cssVar(next.color);
    if (next.line) next.line = fix(next.line as Record<string, unknown>);
    return next;
  };
  for (const key of ["line", "marker", "error_y"]) {
    if (out[key]) out[key] = fix(out[key] as Record<string, unknown>);
  }
  return out;
}

export default function Chart({ data, layout, ariaLabel, small = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const scheme = useColorSchemeVersion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const grid = cssVar("--grid");
    const themed = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: cssVar("--text"), family: "system-ui, sans-serif", size: 12 },
      margin: { l: 52, r: 12, t: 8, b: 32 },
      legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom" },
      autosize: true,
      ...layout,
      xaxis: { gridcolor: grid, zeroline: false, automargin: true, ...(layout.xaxis as object) },
      yaxis: { gridcolor: grid, zeroline: false, automargin: true, ...(layout.yaxis as object) },
    };
    Plotly.react(el, data.map(resolveColors), themed, { responsive: true, displaylogo: false });
  }, [data, layout, scheme]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} className={small ? "chart small" : "chart"} role="img" aria-label={ariaLabel} />;
}
