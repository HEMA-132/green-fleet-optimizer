"""Global Fishing Watch API client and preprocessing pipeline."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class GFWApiClient:
    """Thin client for the Global Fishing Watch v3 API."""

    DEFAULT_DATASET = "public-global-vessel-identity:latest"

    def __init__(self, token: str | None = None, base_url: str | None = None, timeout: int = 30):
        self.base_url = (base_url or "https://gateway.api.globalfishingwatch.org/v3").rstrip("/")
        self.timeout = timeout
        self.token = token or self._resolve_token()
        if not self.token:
            raise ValueError("GFW_API_TOKEN is not configured. Set it in the environment or in the project .env file.")

    @staticmethod
    def _resolve_token() -> str:
        repo_root = Path(__file__).resolve().parents[2]
        load_dotenv(repo_root / ".env")
        return str(os.getenv("GFW_API_TOKEN", "")).strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "green-fleet-optimizer/1.0",
        }

    def request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_params = dict(params or {})

        response = requests.Session().get(url, params=request_params, headers=self._headers(), timeout=self.timeout)
        if response.status_code == 429:
            raise RuntimeError("Global Fishing Watch API rate limit reached. Please retry later.")
        if response.status_code in {401, 403}:
            raise PermissionError(f"Authentication failed for GFW request: {response.text[:250]}")
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"Non-JSON response from GFW API: {response.text[:250]}") from exc
        return payload

    def search_vessels(
        self,
        query: str,
        limit: int = 25,
        offset: int | None = None,
        dataset: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        dataset_name = dataset or self.DEFAULT_DATASET
        params: dict[str, Any] = {
            "query": query,
            "limit": int(limit),
            "datasets[0]": dataset_name,
        }
        if offset is not None and offset != 0:
            params["offset"] = int(offset)
        params.update({key: value for key, value in kwargs.items() if value is not None})
        logger.info("Querying GFW vessel search endpoint for query=%s", query)
        return self.request("vessels/search", params=params)


class GFWDataPreprocessor:
    """Fetch GFW vessel data, store raw responses, and normalize to the GreenFleet pipeline."""

    def __init__(self, client: GFWApiClient | None = None, output_dir: str | Path = "data/processed/gfw"):
        self.client = client or GFWApiClient()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = Path("data/raw/gfw")
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _source_provenance() -> dict[str, Any]:
        try:
            git_config = Path(".git/config").read_text(encoding="utf-8")
        except FileNotFoundError:
            git_config = ""

        remote_url = None
        for line in git_config.splitlines():
            if line.strip().startswith("url = "):
                remote_url = line.split("=", 1)[1].strip()
                break

        return {
            "project_repository_url": remote_url,
            "dataset_repository_url": "https://globalfishingwatch.org/our-apis/documentation",
            "dataset_source_note": "Global Fishing Watch vessel-identity API accessed via official v3 endpoints and bearer-token authentication.",
            "source_file_path": "data/raw/gfw/gfw_vessel_search_raw.json",
        }

    @staticmethod
    def _normalize_payload(entries: list[dict[str, Any]]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            self_reported = entry.get("selfReportedInfo") if isinstance(entry.get("selfReportedInfo"), dict) else {}
            registry_entries = entry.get("registryInfo") if isinstance(entry.get("registryInfo"), list) else []
            registry = registry_entries[0] if registry_entries else {}
            if not isinstance(registry, dict):
                registry = {}

            row = {
                "vessel_id": (
                    entry.get("id")
                    or self_reported.get("id")
                    or registry.get("id")
                    or entry.get("vessel_id")
                    or ""
                ),
                "vessel_type": (
                    entry.get("vesselType")
                    or self_reported.get("vesselType")
                    or registry.get("vesselType")
                    or entry.get("shiptype")
                    or self_reported.get("shiptype")
                    or registry.get("shiptype")
                    or ""
                ),
                "name": (
                    self_reported.get("shipname")
                    or registry.get("shipname")
                    or entry.get("shipname")
                    or entry.get("name")
                    or entry.get("vessel_name")
                    or ""
                ),
                "flag": (
                    registry.get("flag")
                    or self_reported.get("flag")
                    or entry.get("flag")
                    or ""
                ),
                "mmsi": (
                    self_reported.get("mmsi")
                    or registry.get("mmsi")
                    or entry.get("mmsi")
                    or ""
                ),
                "imo": (
                    self_reported.get("imo")
                    or registry.get("imo")
                    or entry.get("imo")
                    or ""
                ),
                "speed_knots": (
                    entry.get("speedKnots")
                    or self_reported.get("speedKnots")
                    or registry.get("speedKnots")
                ),
                "updated_at": (
                    entry.get("updatedAt")
                    or self_reported.get("updatedAt")
                    or registry.get("updatedAt")
                    or entry.get("updated_at")
                ),
            }
            rows.append({key: (str(value).strip() if isinstance(value, str) else value) for key, value in row.items()})
        return pd.DataFrame(rows)

    def process(self, query: str, limit: int = 25, offset: int = 0, dataset: str | None = None) -> dict[str, Any]:
        raw_response = self.client.search_vessels(query=query, limit=limit, offset=offset, dataset=dataset)
        raw_path = self.raw_dir / "gfw_vessel_search_raw.json"
        raw_path.write_text(json.dumps(raw_response, indent=2, default=str), encoding="utf-8")

        entries = raw_response.get("entries") or raw_response.get("data") or raw_response.get("results") or []
        df = self._normalize_payload(entries)
        if df.empty:
            df = pd.DataFrame(columns=["vessel_id", "vessel_type", "name", "flag", "mmsi", "imo", "speed_knots", "updated_at"])

        df["speed_knots"] = pd.to_numeric(df["speed_knots"], errors="coerce")
        df["vessel_id"] = df["vessel_id"].replace({"": pd.NA})
        df["vessel_type"] = df["vessel_type"].replace({"": pd.NA})

        clean_csv_path = self.output_dir / "gfw_vessel_identity_clean.csv"
        clean_parquet_path = self.output_dir / "gfw_vessel_identity_clean.parquet"
        schema_path = self.output_dir / "schema.json"
        report_json_path = self.output_dir / "gfw_data_quality_report.json"
        report_md_path = self.output_dir / "gfw_data_quality_report.md"

        df.to_csv(clean_csv_path, index=False)
        df.to_parquet(clean_parquet_path, index=False)

        schema_mapping = {
            "vessel_id": "vessel_id",
            "vessel_type": "vessel_type",
            "route_id": None,
            "period": "updated_at",
            "distance": None,
            "fuel_type": None,
            "fuel_consumption": None,
            "co2_emissions": None,
            "weather_condition": None,
            "engine_efficiency": None,
            "speed": "speed_knots",
        }

        quality_record = {
            "dataset_name": "gfw_vessel_identity",
            "dataset_type": "GFW API",
            "source_provenance": self._source_provenance(),
            "original_row_count": int(raw_response.get("total") or len(df)),
            "processed_row_count": int(len(df)),
            "query": query,
            "limit": limit,
            "offset": offset,
            "dataset": dataset or self.client.DEFAULT_DATASET,
            "schema_mapping": schema_mapping,
            "raw_response_path": str(raw_path),
            "clean_csv_path": str(clean_csv_path),
            "clean_parquet_path": str(clean_parquet_path),
            "missing_values": df.isna().sum().to_dict(),
            "column_count": int(df.shape[1]),
            "columns_detected": list(df.columns),
            "transformations_performed": [
                "Requested vessel identity data from the official GFW v3 API",
                "Stored the raw API payload without modifying the source response",
                "Normalized the vessel payload into a tabular dataset",
                "Mapped fields into the GreenFleet canonical schema convention",
                "Persisted cleaned CSV, Parquet, and quality-report outputs",
            ],
        }

        schema_path.write_text(json.dumps(schema_mapping, indent=2), encoding="utf-8")
        report_json_path.write_text(json.dumps(quality_record, indent=2, default=str), encoding="utf-8")

        md_lines = [
            "# Global Fishing Watch Data Quality Report",
            "",
            f"- Dataset: {quality_record['dataset_name']}",
            f"- Query: {quality_record['query']}",
            f"- Dataset target: {quality_record['dataset']}",
            f"- Row count: {quality_record['processed_row_count']}",
            "",
            "## Provenance",
            "",
            f"- Project repo: {quality_record['source_provenance']['project_repository_url']}",
            f"- API docs: {quality_record['source_provenance']['dataset_repository_url']}",
            f"- Source note: {quality_record['source_provenance']['dataset_source_note']}",
            "",
            "## Schema mapping",
            "",
            json.dumps(quality_record["schema_mapping"], indent=2),
            "",
            "## Missing values",
            "",
            json.dumps(quality_record["missing_values"], indent=2),
            "",
            "## Transformations performed",
        ]
        for item in quality_record["transformations_performed"]:
            md_lines.append(f"- {item}")
        report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        return {
            "processed_rows": int(len(df)),
            "raw_response_path": str(raw_path),
            "clean_csv_path": str(clean_csv_path),
            "clean_parquet_path": str(clean_parquet_path),
            "schema_path": str(schema_path),
            "quality_report_json": str(report_json_path),
            "quality_report_md": str(report_md_path),
            "schema_mapping": schema_mapping,
            "dataframe": df,
        }
