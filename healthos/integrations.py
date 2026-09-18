from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from defusedxml import ElementTree as ET

from .domain import Observation


def _parse_csv_value(raw: str) -> float | str:
    try:
        return float(raw)
    except ValueError:
        return raw


class HealthConnectContract:
    """Normalized contract consumed by the backend. Native Android code owns Health Connect permissions/read APIs."""

    REQUIRED_FIELDS = {"metric", "value", "observed_at", "source_id", "source_type"}

    @classmethod
    def normalize(cls, record: dict[str, Any]) -> Observation:
        missing = cls.REQUIRED_FIELDS - set(record)
        if missing:
            raise ValueError(f"Health Connect record missing fields: {sorted(missing)}")
        observed = record["observed_at"]
        if isinstance(observed, str):
            observed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        if not isinstance(observed, datetime):
            raise TypeError("observed_at must be an ISO datetime string or datetime")
        return Observation(
            observation_id=str(uuid4()),
            metric=str(record["metric"]),
            value=record["value"],
            unit=record.get("unit"),
            observed_at=observed,
            recorded_at=datetime.now(UTC),
            source_id=str(record["source_id"]),
            source_type=str(record["source_type"]),
            raw_hash=record.get("raw_hash"),
            quality=str(record.get("quality", "unknown")),
            confidence=record.get("confidence"),
            metadata=dict(record.get("metadata", {})),
        )


class GPXImporter:
    NS = {"gpx": "http://www.topografix.com/GPX/1/1"}

    def parse(self, data: bytes, source_id: str = "gpx-import") -> tuple[Observation, ...]:
        raw_hash = hashlib.sha256(data).hexdigest()
        root = ET.fromstring(data)
        obs: list[Observation] = []
        for trkpt in root.findall(".//gpx:trkpt", self.NS):
            lat, lon = trkpt.attrib.get("lat"), trkpt.attrib.get("lon")
            t = trkpt.find("gpx:time", self.NS)
            if lat is None or lon is None or t is None or t.text is None:
                continue
            dt = datetime.fromisoformat(t.text.replace("Z", "+00:00"))
            obs.append(
                Observation(
                    observation_id=str(uuid4()),
                    metric="gps_point",
                    value=f"{lat},{lon}",
                    unit=None,
                    observed_at=dt,
                    recorded_at=datetime.now(UTC),
                    source_id=source_id,
                    source_type="GPX",
                    raw_hash=raw_hash,
                    quality="imported",
                )
            )
        return tuple(obs)


class CSVObservationImporter:
    def parse(self, text: str, source_id: str = "csv-import") -> tuple[Observation, ...]:
        reader = csv.DictReader(io.StringIO(text))
        out: list[Observation] = []
        raw_hash = hashlib.sha256(text.encode()).hexdigest()
        for row in reader:
            out.append(
                HealthConnectContract.normalize(
                    {
                        "metric": row["metric"],
                        "value": _parse_csv_value(row["value"]),
                        "unit": row.get("unit") or None,
                        "observed_at": row["observed_at"],
                        "source_id": source_id,
                        "source_type": "CSV",
                        "raw_hash": raw_hash,
                        "quality": "imported",
                    }
                )
            )
        return tuple(out)


def fit_adapter_status() -> dict[str, str]:
    reason = " ".join(
        (
            "thread-safe parser with active codebase; preferred over fitparse",
            "whose maintainer recommends alternatives",
        )
    )
    return {
        "selected_library": "fitdecode",
        "reason": reason,
        "mode": "optional dependency adapter",
    }
