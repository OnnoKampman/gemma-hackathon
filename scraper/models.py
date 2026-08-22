"""Event record matching the Event schema in product-spec.md §12."""

from dataclasses import dataclass, field
from typing import Optional

CSV_COLUMNS = [
    "id",
    "title",
    "organisation",
    "block",
    "address",
    "lat_lng",
    "datetime",
    "recurrence",
    "cost",
    "languages",
    "accessibility_notes",
    "group_size",
    "has_role",
    "role_description",
    "skills_wanted",
    "source",
    "source_verified_at",
]


@dataclass
class Event:
    id: str
    title: str
    organisation: str
    block: str = ""
    address: str = ""
    lat_lng: str = ""
    datetime: str = ""
    recurrence: str = ""
    cost: str = ""
    languages: str = ""
    accessibility_notes: str = ""
    group_size: str = ""
    has_role: str = "no"
    role_description: str = ""
    skills_wanted: str = ""
    source: str = ""
    source_verified_at: str = ""

    def to_row(self) -> dict:
        return {col: getattr(self, col) for col in CSV_COLUMNS}
