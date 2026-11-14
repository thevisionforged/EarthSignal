export type DataKind = "derived_estimate" | "derived_statistic" | "observed" | "forecast" | "hypothetical";

export interface Health {
  status: string;
  version: string;
  datasets_available: number;
}

export interface TimeSeries {
  dataset_id: string;
  variable: string;
  longname: string;
  units: string;
  resolution: string;
  data_kind: DataKind;
  data_kind_note: string;
  aggregation_note: string;
  dates: string[];
  values: (number | null)[];
}

export interface TrendResult {
  variable: string;
  units: string;
  period_start_year: number;
  period_end_year: number;
  n_years: number;
  excluded_years: Record<string, string>;
  sen_slope_per_decade: number;
  sen_slope_ci95_per_decade: [number, number];
  sen_intercept: number;
  mk_p_value: number;
  modified_mk_p_value: number;
  variance_inflation_factor: number;
  lag1_autocorrelation_detrended: number;
  ols_slope_per_decade: number;
  ols_p_value: number;
  durbin_watson: number;
  total_change_over_period: number;
  significant_at_0_05: boolean;
  method: string;
  diagnostics: string[];
  limitations: string[];
}

export interface TrendResponse {
  dataset_id: string;
  analysis_cutoff: string;
  annual_means: { years: number[]; values: (number | null)[] };
  result: TrendResult;
}

export interface Provenance {
  dataset_id: string;
  provider: string;
  api_version: string;
  data_sources_reported_by_api: string[];
  data_kind_note: string;
  methodology_summary: string;
  spatial_resolution: string;
  time_standard: string;
  request_url: string;
  retrieved_at_utc: string;
  returned_coordinates: { latitude: number; longitude: number; elevation_m: number };
  variables: Record<string, { units: string; longname: string; definition: string | null }>;
  documentation: Record<string, string>;
  citation: string;
  citation_data_reference: string;
  validation: { variables: Record<string, { n_valid: number; n_days: number; first_valid: string; last_valid: string }> };
  // (fields not used by the UI are omitted)
}

export interface SeasonRow {
  season: string;
  label: string;
  months: number[];
  result: TrendResult;
  season_means: { years: number[]; values: (number | null)[] };
  bh_adjusted_p: number;
  significant_after_fdr_0_05: boolean;
}

export interface SeasonalResponse {
  dataset_id: string;
  variable: string;
  analysis_cutoff: string;
  season_definition: string;
  multiple_testing: string;
  seasons: SeasonRow[];
}

export interface WindowRow {
  start_year: number;
  end_year: number;
  n_years: number;
  sen_slope_per_decade: number;
  ci95_per_decade: [number, number];
  modified_mk_p_value: number;
  significant_at_0_05: boolean;
}

export interface SensitivityResponse {
  dataset_id: string;
  variable: string;
  units: string;
  analysis_cutoff: string;
  vary_start: WindowRow[];
  vary_end: WindowRow[];
  min_window_years: number;
  diagnostics: string[];
  source_periods: { last_merra2_day: string; first_geosit_day: string | null; probed_at_utc: string } | null;
  geosit_in_trend_window: boolean | null;
  note: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch (e) {
    throw new ApiError(0, `Network error: ${String(e)}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJson<Health>("/api/health"),
  timeseries: (variable: string, resolution: string) =>
    getJson<TimeSeries>(`/api/timeseries?variable=${variable}&resolution=${resolution}`),
  trend: (variable: string) => getJson<TrendResponse>(`/api/trend?variable=${variable}`),
  provenance: () => getJson<Provenance>("/api/provenance"),
  seasonal: (variable: string) => getJson<SeasonalResponse>(`/api/seasonal?variable=${variable}`),
  sensitivity: (variable: string) => getJson<SensitivityResponse>(`/api/sensitivity?variable=${variable}`),
};
