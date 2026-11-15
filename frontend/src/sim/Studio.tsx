import { useEffect, useState } from "react";
import { AnalogFinder, CompoundExperiment, HeatExplorer, RainSimulator, ScenarioBuilder, UncertaintyLab } from "./Tools";
import "./studio.css";

const TOOLS = [
  { key: "scenario", label: "Scenario Builder", icon: "◐", C: ScenarioBuilder },
  { key: "heat", label: "Heat Stress", icon: "☀", C: HeatExplorer },
  { key: "rain", label: "Rainfall Stress", icon: "☂", C: RainSimulator },
  { key: "compound", label: "Compound Matrix", icon: "▦", C: CompoundExperiment },
  { key: "analogs", label: "Analog Finder", icon: "⌖", C: AnalogFinder },
  { key: "uncertainty", label: "Uncertainty Lab", icon: "≈", C: UncertaintyLab },
] as const;

export function SimulationStudio() {
  const [active, setActive] = useState<(typeof TOOLS)[number]["key"]>("scenario");
  useEffect(() => {
    document.body.classList.add("studio-mode");
    return () => document.body.classList.remove("studio-mode");
  }, []);
  const Tool = TOOLS.find((t) => t.key === active)!.C;
  return (
    <section className="studio" aria-label="Simulation Studio">
      <header className="studio-head">
        <div>
          <p className="studio-eyebrow">SIMULATION STUDIO</p>
          <h1>What-if experiments on Lucknow’s historical record</h1>
          <p className="studio-sub">
            Six tools that apply your assumptions to real NASA POWER daily data (1981–2025, both grid cells). Results are{" "}
            <b>hypothetical what-ifs</b> or <b>derived statistics</b>, never forecasts or impact predictions.
          </p>
        </div>
      </header>
      <nav className="studio-tabs" aria-label="Simulation tools">
        {TOOLS.map((t, i) => (
          <button key={t.key} aria-pressed={active === t.key} onClick={() => setActive(t.key)}>
            <span className="ti" aria-hidden="true">{t.icon}</span>
            <span className="tn">{i + 1}</span> {t.label}
          </button>
        ))}
      </nav>
      <Tool key={active} />
    </section>
  );
}
