"""Wave climatology grounding (Worker B slice, v2-climate branch).

Pure functions over a per-break climate JSON profile built from the
Open-Meteo marine *archive* (ERA5 reanalysis). Deterministic: no LLM,
no Gradio imports.

Profiles live embedded in the break catalogue (``climate`` key on each
record of ``data/australia-surf-breaks-enriched.json``); the per-slug
files in ``data/climate/<slug>.json`` are the builder's output and the
fallback source for catalogues that predate the embed. Schema (per break
id-slug)::
    {
      "slug": str,
      "break_id": str,            # original dataset id ("Name | State | Region")
      "name": str,
      "latitude": float,          # archive query coords (seaward-offset)
      "longitude": float,
      "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
      "n_days": int,              # days in period
      "n_valid_direction": int,
      "n_valid_height": int,
      "direction_rose_pct": {"N": pct, ..., "NNW": pct},  # 16 bins, sum ~100
      "monthly": {
        "1": {"median_swell_height_m": float|None,
              "median_swell_period_s": float|None,
              "days_in_ideal_window": int,
              "n_days": int},
        ... "12": {...}
      },
      "ideal_window_ft": {"min": float|None, "max": float|None}
    }

NOTE (merge rewire): this module is intentionally self-contained and
imports nothing from Worker A's files (``wavereader.openmeteo``,
``wavereader.breaks``). No stubbed imports are needed here; the
seaward-offset STUB lives in ``scripts/build_climate.py`` instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict


COMPASS16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

SEASON_MONTHS: dict[str, list[int]] = {
    "summer": [12, 1, 2],
    "autumn": [3, 4, 5],
    "winter": [6, 7, 8],
    "spring": [9, 10, 11],
}

FT_TO_M = 0.3048


class Finding(TypedDict):
    field: str
    dataset_value: object
    climate_value: object
    severity: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_climate_dir() -> Path:
    return _repo_root() / "data" / "climate"


def slugify(break_id: str) -> str:
    """Deterministic id-slug: lowercase, runs of non-alphanumerics -> '-'."""
    slug = re.sub(r"[^a-z0-9]+", "-", break_id.lower()).strip("-")
    return slug or "break"


def direction_to_bin(deg: float) -> str:
    """Map a compass degree (0-360) to its 16-wind bin label."""
    idx = int(((float(deg) % 360.0) + 11.25) // 22.5) % 16
    return COMPASS16[idx]


def compute_rose(directions: list[float | None]) -> dict[str, float]:
    """16-bin swell-direction rose as percentages (sum ~100 over valid)."""
    counts = {label: 0 for label in COMPASS16}
    n_valid = 0
    for d in directions:
        if d is None:
            continue
        try:
            deg = float(d)
        except (TypeError, ValueError):
            continue
        if deg != deg:  # NaN guard without importing math
            continue
        counts[direction_to_bin(deg)] += 1
        n_valid += 1
    if n_valid == 0:
        return {label: 0.0 for label in COMPASS16}
    return {label: round(100.0 * counts[label] / n_valid, 2) for label in COMPASS16}


def _median(xs: list[float]) -> float | None:
    vals = sorted(x for x in xs if x is not None)
    # filter NaN-ish without math import
    vals = [x for x in vals if x == x]
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return float(vals[mid])
    return float((vals[mid - 1] + vals[mid]) / 2.0)


def compute_monthly_stats(
    dates: list[str],
    heights_m: list[float | None],
    periods_s: list[float | None],
    window_min_m: float | None = None,
    window_max_m: float | None = None,
) -> dict[int, dict]:
    """Group daily archive series by calendar month.

    Returns ``{month: {median_swell_height_m, median_swell_period_s,
    days_in_ideal_window, n_days}}`` for months 1..12. Nulls are ignored
    for medians; ``days_in_ideal_window`` counts days whose height falls
    inside ``[window_min_m, window_max_m]`` (0 when the window is None).
    """
    per_month_h: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    per_month_p: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    per_month_n: dict[int, int] = {m: 0 for m in range(1, 13)}
    per_month_win: dict[int, int] = {m: 0 for m in range(1, 13)}
    for i, ds in enumerate(dates):
        try:
            month = int(ds[5:7])
        except (ValueError, IndexError, TypeError):
            continue
        if month < 1 or month > 12:
            continue
        per_month_n[month] += 1
        h = heights_m[i] if i < len(heights_m) else None
        p = periods_s[i] if i < len(periods_s) else None
        if h is not None and h == h:
            try:
                hf = float(h)
            except (TypeError, ValueError):
                hf = None
            if hf is not None:
                per_month_h[month].append(hf)
                if (
                    window_min_m is not None
                    and window_max_m is not None
                    and window_min_m <= hf <= window_max_m
                ):
                    per_month_win[month] += 1
        if p is not None and p == p:
            try:
                per_month_p[month].append(float(p))
            except (TypeError, ValueError):
                pass
    out: dict[int, dict] = {}
    for m in range(1, 13):
        out[m] = {
            "median_swell_height_m": _median(per_month_h[m]),
            "median_swell_period_s": _median(per_month_p[m]),
            "days_in_ideal_window": per_month_win[m],
            "n_days": per_month_n[m],
        }
    return out


def build_profile(
    *,
    slug: str,
    break_id: str,
    name: str,
    latitude: float,
    longitude: float,
    start: str,
    end: str,
    dates: list[str],
    heights_m: list[float | None],
    directions_deg: list[float | None],
    periods_s: list[float | None],
    window_min_ft: float | None,
    window_max_ft: float | None,
) -> dict:
    """Assemble a climate profile dict from raw daily archive series."""
    rose = compute_rose(directions_deg)
    wmin_m = window_min_ft * FT_TO_M if window_min_ft is not None else None
    wmax_m = window_max_ft * FT_TO_M if window_max_ft is not None else None
    monthly = compute_monthly_stats(dates, heights_m, periods_s, wmin_m, wmax_m)
    n_valid_dir = sum(
        1 for d in directions_deg if d is not None and d == d
    )
    n_valid_h = sum(1 for h in heights_m if h is not None and h == h)
    return {
        "slug": slug,
        "break_id": break_id,
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "period": {"start": start, "end": end},
        "n_days": len(dates),
        "n_valid_direction": n_valid_dir,
        "n_valid_height": n_valid_h,
        "direction_rose_pct": rose,
        "monthly": {str(m): monthly[m] for m in range(1, 13)},
        "ideal_window_ft": {"min": window_min_ft, "max": window_max_ft},
    }


def load_climate(slug: str, climate_dir: str | Path | None = None) -> dict:
    """Load ``data/climate/<slug>.json`` (raises FileNotFoundError if absent)."""
    d = Path(climate_dir) if climate_dir is not None else default_climate_dir()
    path = d / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def break_id(break_: dict) -> str:
    """``"Name | State | Region"`` identity a slug/profile is keyed by."""
    return f"{break_.get('name', '')} | {break_.get('state', '')} | {break_.get('region', '')}"


def break_climate(break_: dict, climate_dir: str | Path | None = None) -> dict:
    """Climate profile for a break record: embedded copy, file fallback.

    Prefers the ``climate`` key embedded in the catalogue record (the
    normal path — no extra disk read); falls back to the per-slug
    ``data/climate/<slug>.json`` file for catalogues that predate the
    embed. Raises FileNotFoundError when neither source has a profile.
    """
    prof = break_.get("climate") if isinstance(break_, dict) else None
    if isinstance(prof, dict) and prof:
        return prof
    return load_climate(slugify(break_id(break_)), climate_dir)


def direction_rose(climate: dict) -> dict[str, float]:
    """Return the 16-bin direction rose (percentages) from a profile."""
    rose = climate.get("direction_rose_pct", {})
    return {label: float(rose.get(label, 0.0)) for label in COMPASS16}


def monthly_medians(climate: dict) -> dict[int, dict]:
    """Return ``{month: {median_swell_height_m, median_swell_period_s}}``."""
    monthly = climate.get("monthly", {})
    out: dict[int, dict] = {}
    for m in range(1, 13):
        entry = monthly.get(str(m), monthly.get(m, {})) or {}
        out[m] = {
            "median_swell_height_m": entry.get("median_swell_height_m"),
            "median_swell_period_s": entry.get("median_swell_period_s"),
        }
    return out


def top_rose_bins(climate: dict, n: int = 3) -> list[str]:
    rose = direction_rose(climate)
    ranked = sorted(rose.items(), key=lambda kv: kv[1], reverse=True)
    return [label for label, _ in ranked[:n]]


def top_months_by_window(climate: dict, n: int = 3) -> list[int]:
    monthly = climate.get("monthly", {}) or {}
    counts: list[tuple[int, int]] = []
    for m in range(1, 13):
        entry = monthly.get(str(m), monthly.get(m, {})) or {}
        try:
            c = int(entry.get("days_in_ideal_window", 0) or 0)
        except (TypeError, ValueError):
            c = 0
        counts.append((m, c))
    counts.sort(key=lambda mc: (-mc[1], mc[0]))
    return [m for m, _ in counts[:n]]


def monthly_window_pct(climate: dict) -> dict[int, float | None]:
    """Share of each month's days whose swell fell inside the ideal window (%).

    ``days_in_ideal_window / n_days * 100`` — the "how often is it good
    here in March" number, comparable across months. ``None`` for months
    with no calendar days in the record.
    """
    monthly = climate.get("monthly", {}) or {}
    out: dict[int, float | None] = {}
    for m in range(1, 13):
        entry = monthly.get(str(m), monthly.get(m, {})) or {}
        try:
            days = int(entry.get("days_in_ideal_window", 0) or 0)
            n = int(entry.get("n_days", 0) or 0)
        except (TypeError, ValueError):
            out[m] = None
            continue
        out[m] = round(100.0 * days / n, 1) if n > 0 else None
    return out


def dominant_directions(climate: dict, n: int = 2) -> list[tuple[str, float]]:
    """The ``n`` most frequent rose bins as ``(label, pct)`` pairs."""
    rose = direction_rose(climate)
    ranked = sorted(rose.items(), key=lambda kv: (-kv[1], COMPASS16.index(kv[0])))
    return [(label, pct) for label, pct in ranked[:n]]


def rose_top_share(climate: dict, n: int = 2) -> float:
    """Cumulative % of observed days carried by the top ``n`` rose bins."""
    rose = direction_rose(climate)
    top = sorted(rose.values(), reverse=True)[:n]
    return round(sum(top), 2)


def ideal_window_label(climate: dict) -> str:
    """Human label for the ideal size window, e.g. ``"4–12 ft"`` (or ``""``)."""
    window = climate.get("ideal_window_ft") or {}
    lo, hi = window.get("min"), window.get("max")
    if lo is None or hi is None:
        return ""
    return f"{float(lo):g}–{float(hi):g} ft"


def summarize(climate: dict) -> dict:
    """Plain-language digest of a profile (UI hints + agent tool output).

    Every number traces straight back to the raw profile — nothing is
    invented: the ideal size window, dominant swell directions with their
    share of days, best months ranked by share of in-window days, and the
    per-month % of days in the window.
    """
    pct = monthly_window_pct(climate)
    best = sorted(
        (m for m in range(1, 13) if pct[m] is not None),
        key=lambda m: (-pct[m], m),
    )[:3]
    dom = dominant_directions(climate, 2)
    return {
        "ideal_window_ft": ideal_window_label(climate) or None,
        "dominant_directions": [[label, share] for label, share in dom],
        "top_directions_share_pct": rose_top_share(climate, 2) if dom else None,
        "best_months_by_share": best,
        "monthly_window_pct": {m: pct[m] for m in range(1, 13)},
    }


def month_to_season(month: int) -> str:
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    raise ValueError(f"invalid month: {month!r}")


def _norm_dirs(dirs: object) -> list[str]:
    if not isinstance(dirs, list):
        return []
    out = []
    for d in dirs:
        if isinstance(d, str) and d.strip():
            out.append(d.strip().upper())
    return out


def audit_break(break_: dict, climate: dict) -> list[Finding]:
    """Compare dataset guesses against observed climate.

    (a) ``idealSwell.direction`` vs the top-3 rose bins: a Finding with
        ``field="idealSwell.direction"`` and ``severity="high"`` when there
        is zero overlap.
    (b) ``bestSeason`` vs the top months by ``days_in_ideal_window``: a
        Finding with ``field="bestSeason"`` and ``severity="medium"`` when
        none of the dataset seasons covers the top months.

    Returns ``[]`` when the data agree or when the climate profile has no
    usable observations (avoids false positives on archive misses).
    """
    findings: list[Finding] = []
    if not isinstance(break_, dict) or not isinstance(climate, dict):
        return findings
    if int(climate.get("n_valid_direction", 0) or 0) == 0:
        return findings

    # (a) direction check
    ideal = break_.get("idealSwell", {}) if isinstance(break_.get("idealSwell"), dict) else {}
    dataset_dirs = _norm_dirs(ideal.get("direction"))
    top3 = top_rose_bins(climate, 3)
    if not dataset_dirs:
        findings.append(
            {
                "field": "idealSwell.direction",
                "dataset_value": [],
                "climate_value": top3,
                "severity": "low",
            }
        )
    elif not (set(dataset_dirs) & set(top3)):
        findings.append(
            {
                "field": "idealSwell.direction",
                "dataset_value": dataset_dirs,
                "climate_value": top3,
                "severity": "high",
            }
        )

    # (b) season check — skip when there is no in-window signal at all
    monthly = climate.get("monthly", {}) or {}
    total_window = 0
    for m in range(1, 13):
        entry = monthly.get(str(m), monthly.get(m, {})) or {}
        try:
            total_window += int(entry.get("days_in_ideal_window", 0) or 0)
        except (TypeError, ValueError):
            pass
    if total_window == 0:
        return findings
    seasons_raw = break_.get("bestSeason", [])
    dataset_seasons = (
        [s.strip().lower() for s in seasons_raw if isinstance(s, str) and s.strip()]
        if isinstance(seasons_raw, list)
        else []
    )
    top_months = top_months_by_window(climate, 3)
    top_seasons = {month_to_season(m) for m in top_months}
    if not dataset_seasons:
        findings.append(
            {
                "field": "bestSeason",
                "dataset_value": [],
                "climate_value": top_months,
                "severity": "low",
            }
        )
    elif not (set(dataset_seasons) & top_seasons):
        findings.append(
            {
                "field": "bestSeason",
                "dataset_value": dataset_seasons,
                "climate_value": top_months,
                "severity": "medium",
            }
        )
    return findings


def filter_existing_slugs(
    slugs: list[str], climate_dir: str | Path | None = None, overwrite: bool = False
) -> list[str]:
    """Resumability helper: return slugs still needing a build.

    A slug needs a build when ``overwrite`` is true or its output file
    ``<climate_dir>/<slug>.json`` does not exist yet. Pure/offline.
    """
    if overwrite:
        return list(slugs)
    d = Path(climate_dir) if climate_dir is not None else default_climate_dir()
    return [s for s in slugs if not (d / f"{s}.json").exists()]


def climate_rose_fig(climate: dict, name: str):
    """Plotly polar bar chart of the 16-bin direction rose."""
    import plotly.graph_objects as go

    rose = direction_rose(climate)
    r = [rose[label] for label in COMPASS16]
    fig = go.Figure(
        data=[
            go.Barpolar(
                r=r,
                theta=COMPASS16,
                name=name,
                hovertemplate="%{theta}: %{r:.1f}%<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=f"{name} — swell direction rose (% of days)",
        polar={"angularaxis": {"direction": "clockwise", "rotation": 90}},
        showlegend=False,
        margin={"t": 60, "b": 20, "l": 20, "r": 20},
    )
    return fig
