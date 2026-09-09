"""Wind chart (ported from ``app/surf_forecast.py``).

Wind as colored arrows only: colour = direction quality, size = strength.
Green = offshore/good, yellow = cross-shore, red = onshore. Arrow size
scales with wind speed in kt. Renders from typed tool payloads.
"""

from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go

from ui.charts._style import add_weekend_shading
from ui.charts.score import _empty_fig, _strip_layout


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
    """Arrow showing where the wind blows TO (input = where it comes FROM)."""
    try:
        to_deg = (float(deg_from) + 180.0) % 360.0
    except (TypeError, ValueError):
        return "•"
    return _ARROWS_8[int((to_deg + 22.5) // 45) % 8]


def build_wind_fig(scored: list[dict], spot: dict | None = None) -> go.Figure:
    """Wind as colored arrows only: colour = direction quality, size = strength.

    ``spot`` is the scoring spot (``ideal_wind.direction``); without it all
    arrows fall back to dark blue.
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
    add_weekend_shading(fig, scored)
    fig = _strip_layout(fig, height=170, hide_x=False)
    fig.update_yaxes(visible=False, showticklabels=False, showgrid=False, zeroline=False)
    return fig
