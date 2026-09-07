"""Bridge enriched surf-break records to the scoring module's spot shape.

Mapping (``data/australia-surf-breaks-enriched.json`` ->
``wavereader/scoring.py``):

- ``name`` / ``region`` pass through verbatim (``region`` defaults to ``""``
  when missing; used by ``rank_spots_this_week`` as the ``(name, region)``
  forecast key).
- ``idealSwell.direction`` (list of compass points) is joined with ``"/"``
  because ``scoring._dir_to_deg`` natively parses slash-separated bearings
  (cyclic mean). Empty/missing lists default to ``"E"`` so ``_dir_to_deg``
  never raises ``ValueError``.
- ``idealSwell.sizeRangeFt.{min,max}`` become ``size_ft_min`` /
  ``size_ft_max`` floats for ``_score_swell_size``.
- ``idealWind.direction`` is joined the same way for ``_score_wind``'s
  offshore reference. ``strength_kt_max`` is a flat ``15.0`` (user
  decision): the schema carries no wind-strength threshold, and the final
  limit is ``min(spot_max, skill_profile_max)`` inside ``_score_wind``.
- ``skillLevel`` is normalised via :func:`normalize_skill` since scoring
  only knows ``beginner/intermediate/advanced/expert``.
- Coordinates are read-only helpers (:func:`get_coords`); scoring itself
  needs no lat/lng (forecast lookup happens elsewhere).

Deterministic only: no LLM, no network.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_DIRECTION = "E"
DEFAULT_WIND_MAX_KT = 15.0

_SCORING_SKILLS = frozenset({"beginner", "intermediate", "advanced", "expert"})
_FALLBACK_SKILL = "intermediate"


def normalize_skill(skill: str | None) -> str:
    """Normalise an enriched ``skillLevel`` to a scoring skill tier."""
    if skill is None:
        return _FALLBACK_SKILL
    s = str(skill).strip().lower()
    if s in ("pro-only", "pro only", "pro"):
        return "expert"
    if s in _SCORING_SKILLS:
        return s
    return _FALLBACK_SKILL


def _join_direction(directions) -> str:
    """Join a compass-point list with ``/``; default to ``"E"`` when empty."""
    if not directions:
        return DEFAULT_DIRECTION
    if isinstance(directions, str):
        text = directions.strip()
        return text if text else DEFAULT_DIRECTION
    parts = [str(d).strip() for d in directions if str(d).strip()]
    return "/".join(parts) if parts else DEFAULT_DIRECTION


def enriched_to_scoring_spot(break_: dict) -> dict:
    """Convert one enriched break record to the ``scoring.py`` spot shape."""
    swell = break_.get("idealSwell", {}) or {}
    size = swell.get("sizeRangeFt", {}) or {}
    wind = break_.get("idealWind", {}) or {}
    return {
        "name": break_.get("name", ""),
        "region": break_.get("region", ""),
        "ideal_swell": {
            "direction": _join_direction(swell.get("direction")),
            "size_ft_min": float(size.get("min", 0.0)),
            "size_ft_max": float(size.get("max", 0.0)),
        },
        "ideal_wind": {
            "direction": _join_direction(wind.get("direction")),
            "strength_kt_max": float(DEFAULT_WIND_MAX_KT),
        },
    }


def get_coords(break_: dict) -> tuple[float | None, float | None]:
    """Return ``(lat, lng)`` mirroring ``main.py`` ``_lat``/``_lng`` logic."""
    try:
        lat = float(break_["location"]["coordinates"]["lat"])
    except (KeyError, TypeError, ValueError):
        lat = None
    try:
        lng = float(break_["location"]["coordinates"]["lng"])
    except (KeyError, TypeError, ValueError):
        lng = None
    return lat, lng


def break_skill(break_: dict) -> str:
    """Return the normalised skill tier for an enriched break record."""
    return normalize_skill(break_.get("skillLevel"))


__all__ = [
    "DEFAULT_DIRECTION",
    "DEFAULT_WIND_MAX_KT",
    "normalize_skill",
    "enriched_to_scoring_spot",
    "get_coords",
    "break_skill",
]
