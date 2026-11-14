declare module "plotly.js-basic-dist-min" {
  // Minimal surface used by Chart.tsx
  const Plotly: {
    react: (el: HTMLElement, data: unknown[], layout: unknown, config?: unknown) => Promise<unknown>;
    purge: (el: HTMLElement) => void;
  };
  export default Plotly;
}
