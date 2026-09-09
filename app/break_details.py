"""Break details table + surf-cam overlay helpers (cams optional)."""

from __future__ import annotations

import pandas as pd

try:
    from app import surf_cams as _cams_mod

    CAMS = _cams_mod.load_cams()
    CAMS_MOD = _cams_mod
except Exception:  # noqa: BLE001 — cams are optional; the app works without them
    CAMS_MOD = None
    CAMS = {}

def _join(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def break_to_table(break_: dict) -> pd.DataFrame:
    """Flatten one break record into a Field/Value table."""
    loc = break_.get("location", {}) or {}
    coords = loc.get("coordinates", {}) or {}
    swell = break_.get("idealSwell", {}) or {}
    swell_size = swell.get("sizeRangeFt", {}) or {}
    wind = break_.get("idealWind", {}) or {}
    tide = break_.get("idealTide", {}) or {}
    rows = [
        ("Name", break_.get("name", "")),
        ("State", break_.get("state", "")),
        ("Region", break_.get("region", "")),
        ("Description", break_.get("description", "")),
        ("Skill level", break_.get("skillLevel", "")),
        ("Break type", break_.get("breakType", "")),
        ("Peak type", break_.get("peakType", "")),
        ("Latitude", coords.get("lat", "")),
        ("Longitude", coords.get("lng", "")),
        ("Ideal swell", _join(swell.get("direction", ""))),
        ("Swell size (ft)", f"{swell_size.get('min', '?')}–{swell_size.get('max', '?')}"),
        ("Ideal wind", f"{_join(wind.get('direction', ''))} ({wind.get('type', '')})"),
        ("Ideal tide", _join(tide.get("stage", ""))),
        ("Best season", _join(break_.get("bestSeason", ""))),
        ("Hazards", _join(break_.get("hazards", ""))),
        ("Crowd", break_.get("crowdFactor", "")),
        ("Surf cam", _cam_table_value(break_)),
    ]
    return pd.DataFrame(rows, columns=["Field", "Value"])


_CAM_EMPTY_MD = "_Pick a break — its surf-cam link will appear here when one is linked._"


CAMS_FALLBACK_MD = "_No public cam linked yet for this break._"


def _cam_entry(record: dict | None) -> dict | None:
    """Overlay entry for a break record, or None (cams optional)."""
    if CAMS_MOD is None:
        return None
    try:
        return CAMS_MOD.get_cam(record, CAMS)
    except Exception:  # noqa: BLE001 — never break the UI over cams
        return None


def _cam_markdown(record: dict | None) -> str:
    """Clickable cam link (or fallback) for the break-book cam box."""
    if CAMS_MOD is None:
        return CAMS_FALLBACK_MD
    try:
        return CAMS_MOD.cam_markdown(record, CAMS)
    except Exception:  # noqa: BLE001
        return CAMS_FALLBACK_MD


def _cam_table_value(record: dict | None) -> str:
    """Plain-text cam value for the details table (not clickable there)."""
    if CAMS_MOD is None:
        return "—"
    try:
        return CAMS_MOD.cam_table_value(record, CAMS)
    except Exception:  # noqa: BLE001
        return "—"
