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

export interface Area {
  key: string;
  label: string;
  name: string;
  latitude: number;
  longitude: number;
  note: string;
  default: boolean;
  dataset_id: string | null;
  grid_elevation_m: number | null;
}

interface TrendSummary {
  sen_slope_per_decade: number;
  ci95_per_decade: [number, number];
  modified_mk_p_value: number;
  significant_at_0_05: boolean;
  n_years: number;
}

export interface StationComparison {
  power_dataset_id: string;
  power_area: string;
  station_dataset_id: string;
  station: {
    id: string;
    metadata_history: { from: string; to: string; name: string; lat: number; lon: number; elev_m: number }[];
    retrieved_at_utc: string;
    data_kind: string;
    time_standard: string;
  };
  variable: string;
  metrics_primary: {
    n_months: number;
    first_month: string;
    last_month: string;
    mean_bias: number;
    mae: number;
    rmse: number;
    pearson_r: number;
    anomaly_pearson_r: number;
    anomaly_rmse: number;
  };
  trend_comparison: {
    years: number[];
    contiguous: boolean;
    power: TrendSummary;
    station: TrendSummary;
    difference_power_minus_station: TrendSummary;
    method: string;
  } | null;
  monthly: {
    months: string[];
    power: (number | null)[];
    station_all: (number | null)[];
    station_primary: (number | null)[];
    station_obs_median: (number | null)[];
  };
  rules: { min_obs_primary: number; month_min_coverage: number };
  diagnostics: string[];
  limitations: string[];
  licence_notice: string;
}

const q = (params: Record<string, string>) => new URLSearchParams(params).toString();

export const api = {
  health: () => getJson<Health>("/api/health"),
  areas: () => getJson<Area[]>("/api/areas"),
  timeseries: (area: string, variable: string, resolution: string) =>
    getJson<TimeSeries>(`/api/timeseries?${q({ area, variable, resolution })}`),
  trend: (area: string, variable: string) => getJson<TrendResponse>(`/api/trend?${q({ area, variable })}`),
  provenance: (area: string) => getJson<Provenance>(`/api/provenance?${q({ area })}`),
  seasonal: (area: string, variable: string) => getJson<SeasonalResponse>(`/api/seasonal?${q({ area, variable })}`),
  sensitivity: (area: string, variable: string) =>
    getJson<SensitivityResponse>(`/api/sensitivity?${q({ area, variable })}`),
  stationComparison: () => getJson<StationComparison>(`/api/station-comparison?${q({ area: "lucknow_airport" })}`),
};

// ---------------- Milestone 3: multi-source ----------------

export interface SourceMetadata {
  dataset_id: string;
  source_type: "nasa_power_met" | "noaa_gsod" | "nasa_power_imerg";
  provider: string;
  distributor: string;
  product_id: string;
  product_version: string;
  variables: { name: string; units: string; definition: string | null; data_kind: string }[];
  spatial_resolution: string;
  spatial_support: string;
  geographic_coverage: Record<string, unknown>;
  temporal_resolution: string;
  time_standard: string;
  time_coverage: { start: string | null; end: string | null; final_run_end?: string | null };
  retrieved_at_utc: string;
  processing_history: string[];
  citation: string;
  quality_limitations: string[];
  access: string;
  usage_notice: string | null;
  area: string | null;
}

interface PairStats {
  n: number;
  mean_merra2: number;
  mean_imerg: number;
  bias_merra2_minus_imerg: number;
  ratio_merra2_over_imerg: number | null;
  rmse: number;
  pearson_r: number;
  spearman_rho: number;
}

interface TrendLite {
  sen_slope_per_decade: number;
  ci95_per_decade: [number, number];
  modified_mk_p_value: number;
  significant_at_0_05: boolean;
  n_years: number;
  period: [number, number];
}

export interface PrecipComparison {
  area: string;
  imerg_dataset_id: string;
  metadata: SourceMetadata;
  coverage: { days: number; area_mean_valid_days: number; merra2_valid_days: number; days_after_final_run_end: number };
  period: { first_day: string; last_day: string; final_run_end: string };
  daily: PairStats & { units: string };
  contingency: {
    threshold_mm_day: number;
    wet_day_fraction_merra2: number;
    wet_day_fraction_imerg: number;
    pod: number | null;
    far: number | null;
    csi: number | null;
    frequency_bias: number | null;
  };
  monthly: PairStats & {
    units: string;
    anomaly_pearson_r: number;
    mean_by_calendar_month_mm: { merra2: Record<string, number>; imerg: Record<string, number> };
  };
  annual: (PairStats & { years: number[] }) | null;
  series: { months: string[]; merra2_mm: number[]; imerg_mm: number[] };
  trend_comparison: { merra2: TrendLite; imerg: TrendLite; difference_merra2_minus_imerg: TrendLite } | null;
  era_step_2014: { available: boolean; mean_diff_pre_mm?: number; mean_diff_post_mm?: number; mann_whitney_p?: number };
  scale_sensitivity?: { monthly_r_area_mean: number; monthly_r_point_cell: number };
  diagnostics: string[];
  method: string[];
  independence_note: string;
}

export const multiApi = {
  sources: () => getJson<SourceMetadata[]>("/api/sources"),
  precip: (area: string) => getJson<PrecipComparison>(`/api/precip-comparison?${q({ area })}`),
  csvUrl: (area: string, level: "monthly" | "daily") => `/api/precip-comparison.csv?${q({ area, level })}`,
};
