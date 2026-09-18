from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .domain import Observation


class LocalObservationStore:
    """Reference local-first store. Production server target is PostgreSQL; Android target is encrypted Room."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                metric TEXT NOT NULL,
                value_json TEXT NOT NULL,
                unit TEXT,
                observed_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                raw_hash TEXT,
                quality TEXT NOT NULL,
                confidence REAL,
                metadata_json TEXT NOT NULL
            )
            """
        )

    def append(self, observations: Iterable[Observation]) -> int:
        count = 0
        for observation in observations:
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    observation.observation_id,
                    observation.metric,
                    json.dumps(observation.value),
                    observation.unit,
                    observation.observed_at.isoformat(),
                    observation.recorded_at.isoformat(),
                    observation.source_id,
                    observation.source_type,
                    observation.raw_hash,
                    observation.quality,
                    observation.confidence,
                    json.dumps(observation.metadata, sort_keys=True),
                ),
            )
            count += max(0, cursor.rowcount)
        self.conn.commit()
        return count

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM observations").fetchone()
        if row is None:
            raise RuntimeError("observation count query returned no row")
        return int(row[0])
