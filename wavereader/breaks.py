"""Surf-break catalogue: load, validate, resolve (wavereader v2 core port).

Ported from ``app/breaks_data.py`` with the pandas dependency dropped:
plain ``json`` + lists throughout. Every record is validated against
``data/surf-break-schema.json`` via jsonschema; invalid records are
skipped (with a count available) unless ``strict=True``.

Public surface::

    load_breaks(path=...) -> list[dict]
    resolve_break(name, region=None, breaks=None) -> dict | None
    filter_breaks(breaks, state=None, region=None, skill=None) -> list[dict]
    get_coords(break_) -> (lat, lng)

Deterministic only: no LLM, no network.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import jsonschema

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "australia-surf-breaks-enriched.json"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "surf-break-schema.json"

ALL = "All"

_SCHEMA_CACHE: dict | None = None


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    """Load (and memoize) the surf-break JSON schema."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def is_valid_break(break_: dict, schema: dict | None = None) -> bool:
    """True when a record conforms to the surf-break schema."""
    try:
        jsonschema.validate(instance=break_, schema=schema or load_schema())
    except jsonschema.ValidationError:
        return False
    return True


def load_breaks(path: Path = DATA_PATH, strict: bool = False) -> list[dict]:
    """Load the enriched break catalogue as a list of validated records.

    Handles the legacy ``{"name | state | region": {...}}`` dict format
    and drops ``error`` rows, mirroring the v1 loader. Records failing
    schema validation are skipped (``strict=True`` raises instead).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        records = list(data.values())
    else:
        records = list(data)

    schema = load_schema()
    out: list[dict] = []
    skipped = 0
    for rec in records:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        if rec.get("error") is not None:
            # v1 semantics: rows carrying an "error" marker are dropped.
            skipped += 1
            continue
        try:
            jsonschema.validate(instance=rec, schema=schema)
        except jsonschema.ValidationError:
            if strict:
                raise
            skipped += 1
            continue
        out.append(rec)
    out.sort(key=lambda b: (str(b.get("state", "")), str(b.get("region", "")), str(b.get("name", ""))))
    load_breaks.last_skipped = skipped  # type: ignore[attr-defined]
    return out


# Count of records skipped by the most recent load_breaks() call.
load_breaks.last_skipped = 0  # type: ignore[attr-defined]


def filter_breaks(
    breaks: list[dict],
    state: str | None = None,
    region: str | None = None,
    skill: str | None = None,
) -> list[dict]:
    """Filter breaks by state / region / skill level ("All"/None = no filter)."""
    out = list(breaks)
    if state and state != ALL:
        out = [b for b in out if str(b.get("state", "")).lower() == state.lower()]
    if region and region != ALL:
        out = [b for b in out if str(b.get("region", "")).lower() == region.lower()]
    if skill and skill != ALL:
        out = [b for b in out if str(b.get("skillLevel", "")).lower() == skill.lower()]
    return out


def _norm(text: str | None) -> str:
    return str(text or "").strip().lower()


def resolve_break(
    name: str, region: str | None = None, breaks: list[dict] | None = None
) -> dict | None:
    """Resolve a break by name (fuzzy, case-insensitive), optionally scoped to a region.

    Match order: exact name (+ region when given) → substring match →
    difflib close match. Returns the record dict, or None when nothing
    matches.
    """
    pool = breaks if breaks is not None else load_breaks()
    want = _norm(name)
    if not want:
        return None
    if region is not None:
        scoped = [b for b in pool if _norm(b.get("region")) == _norm(region)]
        if scoped:
            pool = scoped

    for b in pool:
        if _norm(b.get("name")) == want:
            return b
    for b in pool:
        if want in _norm(b.get("name")):
            return b
    names = [_norm(b.get("name")) for b in pool]
    close = difflib.get_close_matches(want, names, n=1, cutoff=0.6)
    if close:
        for b in pool:
            if _norm(b.get("name")) == close[0]:
                return b
    return None


def get_coords(break_: dict) -> tuple[float | None, float | None]:
    """Return ``(lat, lng)`` (None on missing coords)."""
    try:
        lat = float(break_["location"]["coordinates"]["lat"])
    except (KeyError, TypeError, ValueError):
        lat = None
    try:
        lng = float(break_["location"]["coordinates"]["lng"])
    except (KeyError, TypeError, ValueError):
        lng = None
    return lat, lng


__all__ = [
    "DATA_PATH",
    "SCHEMA_PATH",
    "ALL",
    "load_schema",
    "is_valid_break",
    "load_breaks",
    "filter_breaks",
    "resolve_break",
    "get_coords",
]
