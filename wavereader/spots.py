"""Load, validate and search surf breaks.

Source of truth is ``data/break_details.json`` (records keyed by
``(name, region)``; identity fields anchored to ``data/breaks.json``).

Validation pass lives here rather than hand-edits: coords plausible for the
named region, ranges sane, spot-check ~10 records against local knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass

# TODO: pydantic models for a break record (identity, coordinates,
# ideal_swell, ideal_wind, ideal_tide, additional_details).


@dataclass(frozen=True)
class Spot:
    name: str
    region: str


def load_breaks() -> list[dict]:
    """Load and validate ``data/break_details.json``.

    TODO: parse into pydantic models, run validation (coords vs region,
    sane ranges), raise on failure.
    """
    raise NotImplementedError


def find_spots(
    query: str = "",
    region: str | None = None,
    skill: str | None = None,
    limit: int = 10,
) -> list[Spot]:
    """Search breaks by name/city/region and optional skill filter.

    TODO: case-insensitive substring match over name/region; skill filter
    from knowledge-base suitability. Used by the find_spots tool and
    /spots endpoint.
    """
    raise NotImplementedError


def get_spot(spot: Spot) -> dict:
    """Return the full knowledge-base record for one break.

    TODO: keyed lookup by (name, region).
    """
    raise NotImplementedError
