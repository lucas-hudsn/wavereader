"""Scored surf-forecast helpers for one enriched break.

Loaded via importlib from main.py (like app/generate_surf_break.py), so no
``app`` package import is required. Pure functions only — no Gradio here.
"""

from __future__ import annotations

from typing import Any, Optional

import math

import plotly.graph_objects as go

from app.adapters import break_skill, enriched_to_scoring_spot, get_coords, normalize_skill

from app.forecasts import get_forecast
from app.scoring import SKILL_LEVELS, score_week

# Adapter: prefer wavereader.adapters when it exists, else local fallback
# with the same flat-15kt logic.
try:
    from app.adapters import (  # type: ignore
        break_skill,
        enriched_to_scoring_spot,
        get_coords,
        normalize_skill,
    )
except ImportError:  # local fallback (same contract)

    _FLAT_WIND_KT = 15.0

    def normalize_skill(skill: Any) -> str:
        s = str(skill or "").strip().lower()
        if s in SKILL_LEVELS:
            return s
        if s in ("pro-only", "pro", "expert+", "pro only"):
            return "expert"
        return "intermediate"

    def break_skill(break_: dict) -> str:
        return normalize_skill((break_ or {}).get("skillLevel"))

    def get_coords(break_: dict) -> tuple[float | None, float | None]:
        try:
            coords = (break_ or {}).get("location", {}).get("coordinates", {})
            return float(coords["lat"]), float(coords["lng"])
        except (KeyError, TypeError, ValueError, AttributeError):
            return None, None

    def _dir_to_str(direction: Any) -> str:
        if isinstance(direction, list):
            return "/".join(str(d) for d in direction if d)
        return str(direction or "S")

    def enriched_to_scoring_spot(break_: dict) -> dict:
        swell = (break_ or {}).get("idealSwell", {}) or {}
        size = swell.get("sizeRangeFt", {}) or {}
        wind = (break_ or {}).get("idealWind", {}) or {}
        return {
            "name": break_.get("name", "?"),
            "region": break_.get("region", "?"),
            "ideal_swell": {
                "size_ft_min": float(size.get("min", 1)),
                "size_ft_max": float(size.get("max", 4)),
                "direction": _dir_to_str(swell.get("direction", "S")),
            },
            "ideal_wind": {
                "direction": _dir_to_str(wind.get("direction", "N")),
                # Flat default: enriched breaks carry no wind-strength
                # number, so every spot scores against 15 kt.
                "strength_kt_max": float(
                    wind.get("strengthKtMax", wind.get("strength_kt_max", _FLAT_WIND_KT))
                ),
            },
        }


def get_scored_week(
    break_: dict, skill: str | None = None, days: int = 7
) -> dict[str, Any]:
    """Fetch + score a 7-day (default) hourly forecast for one break."""
    level = normalize_skill(skill) if skill else break_skill(break_)
    days = max(1, min(7, int(days)))
    lat, lng = get_coords(break_)
    if lat is None or lng is None:
        raise ValueError(f"Missing coordinates for break {break_.get('name', '?')!r}")
    spot = enriched_to_scoring_spot(break_)
    forecast = get_forecast(lat, lng, days)
    scored = score_week(forecast, spot, level)
    sun = (forecast.get("daily") or {}) if isinstance(forecast, dict) else {}
    sst_c = None
    for row in (forecast.get("hourly") or [])[:6]:
        if isinstance(row, dict) and row.get("sea_surface_temperature") is not None:
            try:
                sst_c = float(row.get("sea_surface_temperature"))
            except (TypeError, ValueError):
                sst_c = None
            break
    return {
        "forecast": forecast,
        "scored": scored,
        "spot": spot,
        "skill": level,
        "lat": lat,
        "lng": lng,
        "sun": sun,
        "sst_c": sst_c,
        "wetsuit_hint": _wetsuit_hint(sst_c),
    }


def _wetsuit_hint(sst_c) -> str | None:
    """Deterministic SST → wetsuit lookup (same table as agent_tools)."""
    try:
        sst = float(sst_c)
    except (TypeError, ValueError):
        return None
    if sst >= 22.0:
        return f"boardshorts / rashie (SST ~{sst:.1f}C)"
    if sst >= 19.0:
        return f"2mm spring suit (SST ~{sst:.1f}C)"
    if sst >= 16.0:
        return f"3/2mm full suit (SST ~{sst:.1f}C)"
    return f"4/3mm full suit + boots in winter (SST ~{sst:.1f}C)"


def add_sun_markers(fig: go.Figure, sun: dict | None) -> go.Figure:
    """Overlay sunrise (dotted gold) / sunset (dashed orange) verticals.

    ``sun`` is the ``daily`` frame (``{"sunrise": [...], "sunset": [...]}``);
    no-op when absent. Max ~14 lines so the chart stays readable.
    """
    if not isinstance(sun, dict):
        return fig
    for key, color, dash in (("sunrise", "#b8860b", "dot"), ("sunset", "#ff7f0e", "dash")):
        times = sun.get(key) or []
        for t in list(times)[:7]:
            try:
                fig.add_vline(x=t, line_width=1, line_dash=dash, line_color=color)
            except (TypeError, ValueError):
                continue
    return fig


def best_window(scored: list[dict]) -> dict | None:
    """Return the single highest-scoring hour, or None when empty."""
    if not scored:
        return None
    return max(scored, key=lambda r: r.get("score", 0))


def daily_best(scored: list[dict]) -> list[dict]:
    """Best hour per calendar date (date = first 10 chars of ``time``)."""
    best_by_date: dict[str, dict] = {}
    for row in scored or []:
        date = str(row.get("time", ""))[:10]
        if not date:
            continue
        if date not in best_by_date or row.get("score", 0) > best_by_date[date].get(
            "score", 0
        ):
            best_by_date[date] = row
    out = []
    for date in sorted(best_by_date):
        row = best_by_date[date]
        out.append(
            {
                "date": date,
                "time": row.get("time"),
                "score": row.get("score"),
                "wave_height_m": row.get("wave_height_m"),
                "wave_period_s": row.get("wave_period_s"),
                # score_week already converts km/h -> kt.
                "wind_speed_kt": row.get("wind_speed_kt"),
                "wind_direction_deg": row.get("wind_direction_deg"),
            }
        )
    return out


def _empty_fig() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="No forecast data", showarrow=False, font={"size": 16})
    return fig


def _score_color(score: float) -> str:
    """Discrete traffic-light colour for a 0–10 score."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "#bbbbbb"
    if s >= 8:
        return "#1a9850"  # excellent — dark green
    if s >= 6:
        return "#91cf60"  # good — light green
    if s >= 4:
        return "#fee08b"  # fair — yellow
    if s >= 2:
        return "#fc8d59"  # poor — orange
    return "#d73027"  # very poor — red


_ARROWS_8 = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
_COMPASS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

_COMPASS_DEG_16 = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

# Arrow colours: direction quality only (size encodes strength).
_WIND_GOOD = "#1a9850"  # green — offshore / good direction
_WIND_CROSS = "#eab308"  # yellow — cross-shore
_WIND_BAD = "#d73027"  # red — onshore


def _parse_dir_to_deg(direction: Any) -> float | None:
    """Parse 'N', 'NE/SW', 'N to SW' style bearings to degrees (cyclic mean)."""
    if direction is None:
        return None
    if isinstance(direction, (int, float)):
        try:
            return float(direction) % 360.0
        except (TypeError, ValueError):
            return None
    text = str(direction).replace(",", "/").replace(" to ", "/").replace(" ", "").upper()
    parts = [p for p in text.split("/") if p in _COMPASS_DEG_16]
    if not parts:
        return None
    sin_sum = sum(math.sin(math.radians(_COMPASS_DEG_16[p])) for p in parts)
    cos_sum = sum(math.cos(math.radians(_COMPASS_DEG_16[p])) for p in parts)
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0


def _angular_diff(a: float, b: float) -> float:
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _wind_quality_color(wind_from_deg: float, offshore_from_deg: float | None) -> str:
    """Green (offshore) ≤45°, yellow (cross) ≤135°, else red (onshore)."""
    if offshore_from_deg is None:
        return "#0b2c5c"
    try:
        diff = _angular_diff(float(wind_from_deg), float(offshore_from_deg))
    except (TypeError, ValueError):
        return "#0b2c5c"
    if diff <= 45.0:
        return _WIND_GOOD
    if diff <= 135.0:
        return _WIND_CROSS
    return _WIND_BAD


def _wind_arrow_size(speed_kt: Any) -> float:
    """Arrow size encodes strength: ~22 pt when light → ~33 pt when strong (1–1.5x)."""
    try:
        s = max(0.0, float(speed_kt))
    except (TypeError, ValueError):
        return 22.0
    return 22.0 + 11.0 * min(s, 30.0) / 30.0


def _deg_to_compass(deg: float) -> str:
    """8-point compass label for a meteorological degree."""
    try:
        d = float(deg) % 360.0
    except (TypeError, ValueError):
        return "?"
    return _COMPASS_8[int((d + 22.5) // 45) % 8]


def _deg_to_arrow_from(deg_from: float) -> str:
    """Arrow showing where the wind blows TO.

    ``deg_from`` is the meteorological direction (where wind comes FROM);
    the arrow points the opposite way, i.e. the direction of travel.
    """
    try:
        to_deg = (float(deg_from) + 180.0) % 360.0
    except (TypeError, ValueError):
        return "•"
    return _ARROWS_8[int((to_deg + 22.5) // 45) % 8]


def _strip_layout(fig: go.Figure, height: int = 230, hide_x: bool = False) -> go.Figure:
    """Compact shared styling so the three forecast strips read as one.

    Legends share the wind chart's top-right spot (horizontal, anchored
    right) so Score / Swell / Wind titles + legends line up.
    """
    fig.update_layout(
        height=height,
        margin={"l": 48, "r": 48, "t": 60, "b": 30 if not hide_x else 8},
        showlegend=True,
        legend={
            "orientation": "h",
            "x": 1.0,
            "y": 1.15,
            "xanchor": "right",
            "yanchor": "bottom",
        },
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    # Left-align any title so it never shifts the legend row.
    if getattr(getattr(fig.layout, "title", None), "text", None):
        fig.update_layout(title={"x": 0.0, "xanchor": "left"})
    fig.update_xaxes(showticklabels=not hide_x, tickangle=-30, showgrid=True)
    fig.update_yaxes(showgrid=True, gridcolor="#e5e5e5")
    return fig


def build_score_fig(scored: list[dict]) -> go.Figure:
    """Bars coloured by quality (red → green); ★ marks the best hour."""
    if not scored:
        return _empty_fig()
    times = [r.get("time") for r in scored]
    scores = [float(r.get("score") or 0) for r in scored]
    colors = [_score_color(s) for s in scores]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=times,
            y=scores,
            marker={"color": colors, "line": {"width": 0}},
            hovertemplate="%{x}<br>score: %{y:.1f}/10<extra></extra>",
            name="score",
        )
    )
    # Dummy entries so the top legend explains the bar colours.
    for band_name, band_color in [
        ("8+ excellent", "#1a9850"),
        ("6–8 good", "#91cf60"),
        ("4–6 fair", "#fee08b"),
        ("2–4 poor", "#fc8d59"),
        ("0–2 very poor", "#d73027"),
    ]:
        fig.add_trace(
            go.Bar(
                x=[None],
                y=[None],
                marker={"color": band_color},
                name=band_name,
                hoverinfo="skip",
            )
        )
    best = best_window(scored)
    if best is not None:
        fig.add_trace(
            go.Scatter(
                x=[best.get("time")],
                y=[best.get("score")],
                mode="markers",
                marker={"size": 13, "color": "#FFD700", "symbol": "star",
                        "line": {"width": 1, "color": "#0b2c5c"}},
                hovertemplate="★ best: %{y:.1f}/10 @ %{x}<extra></extra>",
                name="best ★",
            )
        )
    fig.update_layout(title="Score", yaxis={"range": [0, 10], "title": "0–10"})
    return _strip_layout(fig, height=230, hide_x=True)


def build_components_fig(scored: list[dict]) -> go.Figure:
    """Retired — kept so old callers don't crash. Use build_score_fig instead."""
    return _empty_fig()


def build_waves_fig(scored: list[dict]) -> go.Figure:
    """Swell height as a filled area (left axis) + period as a line (right)."""
    if not scored:
        return _empty_fig()
    times = [r.get("time") for r in scored]
    heights = [r.get("wave_height_m") for r in scored]
    periods = [r.get("wave_period_s") for r in scored]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times,
            y=heights,
            mode="lines",
            fill="tozeroy",
            fillcolor="rgba(31,119,180,0.25)",
            line={"color": "#1f77b4", "width": 2},
            hovertemplate="%{x}<br>height: %{y:.1f} m<extra></extra>",
            name="height (m)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=periods,
            mode="lines",
            line={"color": "#ff7f0e", "width": 2},
            hovertemplate="%{x}<br>period: %{y:.0f} s<extra></extra>",
            name="period (s)",
            yaxis="y2",
        )
    )
    fig.update_layout(
        title="Swell",
        yaxis={"title": "m"},
        yaxis2={"title": "s", "overlaying": "y", "side": "right"},
    )
    return _strip_layout(fig, height=230, hide_x=True)


def build_wind_fig(scored: list[dict], spot: dict | None = None) -> go.Figure:
    """Wind as colored arrows only: colour = direction quality, size = strength.

    Green = offshore/good (≤45° from the spot's ideal), yellow = cross-shore,
    red = onshore (>135°). Arrow size scales 22→33 pt (1–1.5x) with wind
    speed in kt; heavy font weight keeps them thick. Single row, no y-axis —
    strength reads from size only, exact kt on hover. Arrows point where the
    wind blows TO. ``spot`` is the scoring spot (``ideal_wind.direction``);
    without it all arrows fall back to dark blue.
    """
    if not scored:
        return _empty_fig()
    times = [r.get("time") for r in scored]
    speeds = [r.get("wind_speed_kt") for r in scored]
    dirs = [r.get("wind_direction_deg") for r in scored]
    offshore_deg: float | None = None
    if isinstance(spot, dict):
        offshore_deg = _parse_dir_to_deg((spot.get("ideal_wind") or {}).get("direction"))
    fig = go.Figure()
    # Subsample arrows so the strip stays readable (~1 per 6 h on a 7-day view).
    step = max(1, len(times) // 28)
    idx = list(range(0, len(times), step))
    colors = [_wind_quality_color(dirs[i], offshore_deg) for i in idx]
    sizes = [_wind_arrow_size(speeds[i]) for i in idx]
    fig.add_trace(
        go.Scatter(
            x=[times[i] for i in idx],
            y=[1.0] * len(idx),
            mode="text",
            text=[_deg_to_arrow_from(dirs[i]) for i in idx],
            textfont={
                "size": sizes,
                "color": colors,
                "family": "Arial Black, Arial, sans-serif",
            },
            hovertemplate="%{x}<br>%{customdata}<extra></extra>",
            customdata=[
                f"{float(speeds[i]):.0f} kt from {_deg_to_compass(dirs[i])} "
                f"({float(dirs[i]):.0f}°) — arrow points where it blows to"
                for i in idx
            ],
            name="wind",
            showlegend=False,
        )
    )
    # Dummy entries so the top legend explains arrow colours (the arrow
    # trace itself stays out of the legend so it never blocks arrows).
    for legend_name, legend_color in [
        ("offshore", _WIND_GOOD),
        ("cross-shore", _WIND_CROSS),
        ("onshore", _WIND_BAD),
    ]:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 10, "color": legend_color, "symbol": "square"},
                name=legend_name,
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        title="Wind",
        yaxis={"visible": False, "showticklabels": False, "range": [0.5, 1.5]},
        showlegend=True,
    )
    fig = _strip_layout(fig, height=170, hide_x=False)
    fig.update_yaxes(visible=False, showticklabels=False, showgrid=False, zeroline=False)
    return fig
