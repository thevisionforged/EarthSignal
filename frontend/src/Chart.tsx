import { useEffect, useRef } from "react";
import Plotly from "plotly.js-basic-dist-min";

interface Props {
  data: unknown[];
  layout: Record<string, unknown>;
  ariaLabel: string;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function Chart({ data, layout, ariaLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const text = cssVar("--text");
    const grid = cssVar("--grid");
    const themed = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: text, family: "system-ui, sans-serif", size: 12 },
      margin: { l: 56, r: 16, t: 16, b: 40 },
      legend: { orientation: "h", y: -0.18 },
      ...layout,
      xaxis: { gridcolor: grid, zeroline: false, ...(layout.xaxis as object) },
      yaxis: { gridcolor: grid, zeroline: false, ...(layout.yaxis as object) },
    };
    Plotly.react(el, data, themed, { responsive: true, displaylogo: false });
  }, [data, layout]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} className="chart" role="img" aria-label={ariaLabel} />;
}
