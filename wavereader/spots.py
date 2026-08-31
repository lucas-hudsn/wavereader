"""Load, validate and search surf breaks.

Source of truth is ``data/break_details.json`` (records keyed by
``(name, region)``; identity fields anchored to ``data/breaks.json``).

Validation pass lives here rather than hand-edits: coords plausible for
the named region, ranges sane, spot-check ~10 records against local
knowledge.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "break_details.json"
VALID_REGIONS = {"NSW", "QLD", "VIC", "WA", "SA", "TAS"}
VALID_SKILL_LEVELS = {
    "beginner",
    "beginner to intermediate",
    "beginner to advanced",
    "intermediate",
    "intermediate to advanced",
    "intermediate to expert",
    "advanced",
    "advanced to expert",
    "expert",
    "expert only",
    "elite/professional only",
}

# Approximate bounding boxes per Australian state/territory (lat_min, lng_min, lat_max, lng_max).
_REGION_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "NSW": (-37.5, 147.5, -26.0, 154.5),
    "QLD": (-29.0, 138.0, -10.0, 154.5),
    "VIC": (-39.5, 140.5, -36.0, 150.5),
    "WA": (-36.0, 113.0, -15.0, 130.0),
    "SA": (-38.5, 135.5, -34.0, 142.5),
    "TAS": (-44.0, 144.0, -39.0, 149.5),
}


class Coordinates(BaseModel):
    lat: float
    lng: float


class IdealSwell(BaseModel):
    size_ft_min: float
    size_ft_max: float
    direction: str

    @field_validator("size_ft_min")
    @classmethod
    def size_min_lt_max(cls, v: float) -> float:
        return v

    @model_validator(mode="after")
    def check_swell_sizes(self) -> "IdealSwell":
        if self.size_ft_min >= self.size_ft_max:
            raise ValueError("size_ft_min must be strictly less than size_ft_max")
        return self


class IdealWind(BaseModel):
    strength_kt_max: float
    direction: str

    @field_validator("strength_kt_max")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("strength_kt_max must be positive")
        return v


class AdditionalDetails(BaseModel):
    break_type: str
    break_direction: str
    break_surface: str
    bottom_type: str
    skill_level: str
    best_season: str
    hazards: str
    other_notes: str

    @field_validator("skill_level")
    @classmethod
    def valid_skill(cls, v: str) -> str:
        if v not in VALID_SKILL_LEVELS:
            raise ValueError(f"skill_level '{v}' not in known levels")
        return v


class Break(BaseModel):
    name: str
    region: str
    short_description: str
    coordinates: Coordinates
    ideal_swell: IdealSwell
    ideal_wind: IdealWind
    ideal_tide: str
    additional_details: AdditionalDetails

    @field_validator("region")
    @classmethod
    def valid_region(cls, v: str) -> str:
        if v not in VALID_REGIONS:
            raise ValueError(f"region '{v}' not in {VALID_REGIONS}")
        return v

    @field_validator("coordinates")
    @classmethod
    def coords_in_bounds(cls, v: Coordinates, info: dict) -> Coordinates:
        region = info.data.get("region")
        if region and region in _REGION_BOUNDS:
            lo_lat, lo_lng, hi_lat, hi_lng = _REGION_BOUNDS[region]
            if not (lo_lat <= v.lat <= hi_lat and lo_lng <= v.lng <= hi_lng):
                raise ValueError(
                    f"coords ({v.lat}, {v.lng}) outside plausible range for {region}"
                )
        return v


def _load_raw() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def load_breaks(path: Path | str | None = None) -> list[Break]:
    """Load and validate ``data/break_details.json``.

    Raises on validation failure so broken data is caught early.
    """
    p = Path(path) if path else DATA_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    breaks: list[Break] = []
    for i, record in enumerate(raw):
        try:
            breaks.append(Break.model_validate(record))
        except Exception as exc:
            raise ValueError(
                f"Invalid record at index {i}: {record.get('name', '?')} "
                f"({record.get('region', '?')})"
            ) from exc
    return breaks


def find_spots(
    query: str = "",
    region: str | None = None,
    skill: str | None = None,
    limit: int = 10,
) -> list[Break]:
    """Search breaks by name/region and optional skill filter.

    Case-insensitive substring match over name and region.
    """
    all_breaks = load_breaks()
    q = query.lower().strip()
    results: list[Break] = []
    for b in all_breaks:
        if q and q not in b.name.lower() and q not in b.region.lower():
            continue
        if region and b.region != region:
            continue
        if skill:
            skill_lower = skill.lower()
            if skill_lower not in b.additional_details.skill_level.lower():
                continue
        results.append(b)
        if len(results) >= limit:
            break
    return results


def get_spot(name: str, region: str) -> Break | None:
    """Return the full knowledge-base record for one break, keyed by (name, region)."""
    for b in load_breaks():
        if b.name == name and b.region == region:
            return b
    return None