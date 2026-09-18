from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import gpxpy
from defusedxml import ElementTree as SafeElementTree

from .domain import Observation

MAX_GPX_BYTES = 20 * 1024 * 1024
MAX_GPX_POINTS = 200_000
MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 100_000


def _parse_csv_value(raw: str) -> float | str:
    try:
        return float(raw)
    except ValueError:
        return raw


def _stable_observation_id(source_type: str, raw_hash: str, identity: str) -> str:
    digest = hashlib.sha256(f"{source_type}|{raw_hash}|{identity}".encode("utf-8")).hexdigest()
    return f"{source_type.lower()}:{digest}"


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
            observation_id=str(record.get("observation_id") or uuid4()),
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
    def parse(self, data: bytes, source_id: str = "gpx-import") -> tuple[Observation, ...]:
        if len(data) > MAX_GPX_BYTES:
            raise ValueError(f"GPX exceeds maximum size of {MAX_GPX_BYTES} bytes")
        raw_hash = hashlib.sha256(data).hexdigest()

        # Fail closed on DTD/entities before passing the document to the feature-complete GPX parser.
        SafeElementTree.fromstring(data)
        document = gpxpy.parse(io.BytesIO(data))

        observations: list[Observation] = []
        point_index = 0
        for track_index, track in enumerate(document.tracks):
            for segment_index, segment in enumerate(track.segments):
                for point in segment.points:
                    point_index += 1
                    if point_index > MAX_GPX_POINTS:
                        raise ValueError(f"GPX exceeds maximum point count of {MAX_GPX_POINTS}")
                    if point.time is None:
                        continue
                    identity = (
                        f"{track_index}|{segment_index}|{point_index}|{point.time.isoformat()}|"
                        f"{point.latitude:.8f}|{point.longitude:.8f}"
                    )
                    observations.append(
                        Observation(
                            observation_id=_stable_observation_id("GPX", raw_hash, identity),
                            metric="gps_point",
                            value=f"{point.latitude:.8f},{point.longitude:.8f}",
                            unit=None,
                            observed_at=point.time,
                            recorded_at=datetime.now(UTC),
                            source_id=source_id,
                            source_type="GPX",
                            raw_hash=raw_hash,
                            quality="imported",
                            metadata={
                                "latitude": point.latitude,
                                "longitude": point.longitude,
                                "elevation_m": point.elevation,
                                "track_index": track_index,
                                "segment_index": segment_index,
                                "point_index": point_index,
                            },
                        )
                    )
        return tuple(observations)


class CSVObservationImporter:
    REQUIRED_COLUMNS = {"metric", "value", "observed_at"}

    def parse(self, text: str, source_id: str = "csv-import") -> tuple[Observation, ...]:
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_CSV_BYTES:
            raise ValueError(f"CSV exceeds maximum size of {MAX_CSV_BYTES} bytes")
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = set(reader.fieldnames or ())
        missing = self.REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")

        out: list[Observation] = []
        raw_hash = hashlib.sha256(encoded).hexdigest()
        for row_index, row in enumerate(reader, start=1):
            if row_index > MAX_CSV_ROWS:
                raise ValueError(f"CSV exceeds maximum row count of {MAX_CSV_ROWS}")
            identity = "|".join(
                (
                    str(row_index),
                    row["metric"],
                    row["value"],
                    row.get("unit") or "",
                    row["observed_at"],
                )
            )
            out.append(
                HealthConnectContract.normalize(
                    {
                        "observation_id": _stable_observation_id("CSV", raw_hash, identity),
                        "metric": row["metric"],
                        "value": _parse_csv_value(row["value"]),
                        "unit": row.get("unit") or None,
                        "observed_at": row["observed_at"],
                        "source_id": source_id,
                        "source_type": "CSV",
                        "raw_hash": raw_hash,
                        "quality": "imported",
                        "metadata": {"row_index": row_index},
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
