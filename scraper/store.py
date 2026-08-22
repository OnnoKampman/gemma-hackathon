"""CSV-backed event store. Upserts by event id, matching the Event schema columns."""

from __future__ import annotations

import csv
import os
from typing import Iterable

from .models import CSV_COLUMNS, Event


class CsvEventStore:
    def __init__(self, path: str):
        self.path = path
        self._rows: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._rows[row["id"]] = row

    def upsert(self, events: Iterable[Event]) -> tuple[int, int]:
        added, updated = 0, 0
        for event in events:
            row = event.to_row()
            if row["id"] in self._rows:
                updated += 1
            else:
                added += 1
            self._rows[row["id"]] = row
        return added, updated

    def save(self) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in sorted(self._rows.values(), key=lambda r: r["id"]):
                writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})
        os.replace(tmp_path, self.path)

    def __len__(self) -> int:
        return len(self._rows)
