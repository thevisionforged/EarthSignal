"""Common dataset metadata interface (Milestone 3, Phase 4; DECISIONS D-018).

Every dataset EarthSignal holds is described by the same `DatasetMetadata` model, whatever its
provider. Existing provenance files (NASA POWER, NOAA GSOD) are never rewritten. Adapters derive
the common description from them when it is requested. New dataset types (POWER-served IMERG)
write the common block directly into their provenance.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DataKind = Literal["observed", "derived_estimate", "derived_statistic", "forecast", "hypothetical"]


class VariableInfo(BaseModel):
    name: str
    units: str
    definition: str | None = None
    data_kind: DataKind


class DatasetMetadata(BaseModel):
    dataset_id: str
    source_type: Literal["nasa_power_met", "noaa_gsod", "nasa_power_imerg"]
    provider: str
    distributor: str
    product_id: str
    product_version: str
    variables: list[VariableInfo] = Field(min_length=1)
    spatial_resolution: str
    spatial_support: str  # e.g. "single 0.5 x 0.625 deg grid cell", "station point", "area mean of ..."
    geographic_coverage: dict[str, Any]
    temporal_resolution: str
    time_standard: str
    time_coverage: dict[str, str | None]
    retrieved_at_utc: str
    processing_history: list[str] = Field(min_length=1)
    citation: str
    quality_limitations: list[str] = Field(min_length=1)
    access: str
    usage_notice: str | None = None


def from_power_met(prov: dict[str, Any]) -> DatasetMetadata:
    v = prov["validation"]["variables"]
    starts = [x["first_valid"] for x in v.values() if x.get("first_valid")]
    ends = [x["last_valid"] for x in v.values() if x.get("last_valid")]
    return DatasetMetadata(
        dataset_id=prov["dataset_id"],
        source_type="nasa_power_met",
        provider="NASA GMAO MERRA-2 reanalysis (GEOS-IT for the most recent weeks)",
        distributor=prov["provider"],
        product_id="POWER Daily API, point (meteorology)",
        product_version=prov["api_version"],
        variables=[
            VariableInfo(name=k, units=x["units"], definition=x.get("definition"), data_kind="derived_estimate")
            for k, x in prov["variables"].items()
        ],
        spatial_resolution=prov["spatial_resolution"],
        spatial_support="single MERRA-2 grid cell containing the request point",
        geographic_coverage={"request_point": {k: prov["requested"][k] for k in ("latitude", "longitude")}},
        temporal_resolution="daily",
        time_standard=prov["time_standard"],
        time_coverage={"start": min(starts) if starts else None, "end": max(ends) if ends else None},
        retrieved_at_utc=prov["retrieved_at_utc"],
        processing_history=[f"{s['step']}: {s['detail']}" for s in prov["processing_history"]],
        citation=f"{prov['citation']} {prov.get('citation_data_reference', '')}".strip(),
        quality_limitations=[
            prov["data_kind_note"],
            "NASA validation against GSOD: daily T2M RMSE 2.10 C (R^2 0.97); daily precipitation RMSE 3.69 mm/day (R^2 0.39).",
            "Recent weeks come from GEOS-IT and are later replaced by MERRA-2 values.",
        ],
        access="Public NASA POWER API; no login required.",
    )


def from_gsod(prov: dict[str, Any]) -> DatasetMetadata:
    years = sorted(int(y) for y in prov["per_year_coverage"])
    hist = prov["station_metadata_history"]
    return DatasetMetadata(
        dataset_id=prov["dataset_id"],
        source_type="noaa_gsod",
        provider=f"Station {prov['station']} (national meteorological service via WMO exchange)",
        distributor=prov["provider"],
        product_id=prov["product"],
        product_version="not versioned (operational archive)",
        variables=[
            VariableInfo(name="tmean_c", units="C", definition="Daily mean air temperature (GSOD TEMP, converted from F)", data_kind="observed"),
            VariableInfo(name="prcp_mm", units="mm", definition="Daily precipitation (GSOD PRCP, converted from inches; not used for comparison)", data_kind="observed"),
        ],
        spatial_resolution="point (weather station)",
        spatial_support=f"station point {hist[-1]['lat']} N, {hist[-1]['lon']} E" if hist else "station point",
        geographic_coverage={"station": hist[-1] if hist else None},
        temporal_resolution="daily",
        time_standard=prov["time_standard"],
        time_coverage={"start": hist[0]["from"] if hist else str(years[0]), "end": hist[-1]["to"] if hist else str(years[-1])},
        retrieved_at_utc=prov["retrieved_at_utc"],
        processing_history=prov["processing_history"],
        citation="NOAA National Centers for Environmental Information, Global Surface Summary of the Day (GSOD), station "
        f"{prov['station']}, accessed {prov['retrieved_at_utc'][:10]}.",
        quality_limitations=[
            "Observations per daily mean rose from about 6-8 (before 1996) to 20-24 (from 2005); the record is not homogeneous.",
            "Precipitation reports are mostly missing (flag I) or partial-day; not usable for comparison.",
            "UTC days; a point measurement, not an area average.",
        ],
        access="Public NOAA NCEI HTTPS; no login required.",
        usage_notice=prov["licence_notice"],
    )


def describe(prov: dict[str, Any]) -> DatasetMetadata:
    """Common metadata for any EarthSignal provenance record."""
    if "metadata" in prov:  # new-style datasets carry the common block directly
        return DatasetMetadata.model_validate(prov["metadata"])
    if prov.get("source_type") == "noaa_gsod":
        return from_gsod(prov)
    return from_power_met(prov)
