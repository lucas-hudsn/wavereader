"""The week strip: score + swell + wind as ONE synchronized instrument.

One Plotly figure, three stacked rows sharing the time axis — score bars
(0–10, traffic-light), swell height + period, wind arrows (colour =
direction quality vs. the spot's ideal offshore bearing, size = speed) —
so the whole forecast reads in a single glance.

Deterministic: renders straight from typed tool payloads (scored hour
dicts + the scoring spot for wind colouring).
"""

from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go

from ui.charts import score as score_chart
from ui.charts._style import INK, add_weekend_shading, style_fig

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

_CAPTION = (
    "green arrows offshore · yellow cross-shore · red onshore — "
    "size = speed · ★ best daylight hour · shaded bands = weekend · "
    "gold dotted = sunrise · orange dashed = sunset · night bars dimmed"
)


def _bar_color(score: float, daylight: bool) -> str:
    """Traffic-light hex; night hours keep their colour at 35% alpha."""
    hex_c = score_chart._score_color(score)
    if daylight:
        return hex_c
    r, g, b = (int(hex_c[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},0.35)"


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
        return INK
    try:
        diff = _angular_diff(float(wind_from_deg), float(offshore_from_deg))
    except (TypeError, ValueError):
        return INK
    if diff <= 45.0:
        return _WIND_GOOD
    if diff <= 135.0:
        return _WIND_CROSS
    return _WIND_BAD


def _wind_arrow_size(speed_kt: Any) -> float:
    """Arrow size encodes strength: ~20 pt when light → ~31 pt when strong."""
    try:
        s = max(0.0, float(speed_kt))
    except (TypeError, ValueError):
        return 20.0
    return 20.0 + 11.0 * min(s, 30.0) / 30.0


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


def _scoring_spot(break_: dict | None) -> dict | None:
    """Minimal scoring spot for wind directional colouring."""
    if not break_:
        return None
    wind = (break_ or {}).get("idealWind", {}) or {}
    direction = wind.get("direction", "N")
    if isinstance(direction, list):
        direction = "/".join(str(d) for d in direction if d)
    return {"ideal_wind": {"direction": str(direction or "N")}}


def add_score_traces(fig, scored: list[dict], row: int = 1) -> go.Figure:
    """Score bars (traffic-light, night dimmed) + ★ best-hour marker."""
    times = [r.get("time") for r in scored]
    scores = [float(r.get("score") or 0) for r in scored]
    colors = [_bar_color(s, bool(r.get("daylight", True)))
              for s, r in zip(scores, scored)]
    fig.add_trace(
        go.Bar(
            x=times, y=scores,
            marker={"color": colors, "line": {"width": 0}},
            hovertemplate="%{x}<br>score: %{y:.1f}/10<extra></extra>",
            name="score",
        ),
        row=row, col=1,
    )
    best = score_chart.best_window(scored)
    if best is not None:
        fig.add_trace(
            go.Scatter(
                x=[best.get("time")], y=[best.get("score")],
                mode="markers",
                marker={"size": 13, "color": "#FFD700", "symbol": "star",
                        "line": {"width": 1, "color": INK}},
                hovertemplate="★ best: %{y:.1f}/10 @ %{x}<extra></extra>",
                name="best ★",
            ),
            row=row, col=1,
        )
    return fig


def add_swell_traces(fig, scored: list[dict], row: int = 2) -> go.Figure:
    """Swell height (filled area, left axis) + period (line, right axis)."""
    times = [r.get("time") for r in scored]
    fig.add_trace(
        go.Scatter(
            x=times, y=[r.get("wave_height_m") for r in scored],
            mode="lines", fill="tozeroy", fillcolor="rgba(31,119,180,0.25)",
            line={"color": "#1f77b4", "width": 2},
            hovertemplate="%{x}<br>height: %{y:.1f} m<extra></extra>",
            name="height (m)",
        ),
        row=row, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=times, y=[r.get("wave_period_s") for r in scored],
            mode="lines", line={"color": "#ff7f0e", "width": 2},
            hovertemplate="%{x}<br>period: %{y:.0f} s<extra></extra>",
            name="period (s)",
        ),
        row=row, col=1, secondary_y=True,
    )
    return fig


def add_wind_traces(fig, scored: list[dict], spot: dict | None = None,
                    row: int = 3) -> go.Figure:
    """Wind arrows onto a subplot row (colour = quality, size = speed)."""
    times = [r.get("time") for r in scored]
    speeds = [r.get("wind_speed_kt") for r in scored]
    dirs = [r.get("wind_direction_deg") for r in scored]
    offshore_deg: float | None = None
    if isinstance(spot, dict):
        offshore_deg = _parse_dir_to_deg((spot.get("ideal_wind") or {}).get("direction"))
    # Subsample arrows so the strip stays readable (~1 per 6 h on a 7-day view).
    step = max(1, len(times) // 28)
    idx = list(range(0, len(times), step))
    fig.add_trace(
        go.Scatter(
            x=[times[i] for i in idx], y=[1.0] * len(idx),
            mode="text",
            text=[_deg_to_arrow_from(dirs[i]) for i in idx],
            textfont={
                "size": [_wind_arrow_size(speeds[i]) for i in idx],
                "color": [_wind_quality_color(dirs[i], offshore_deg) for i in idx],
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
        ),
        row=row, col=1,
    )
    return fig


def build_week_strip(scored: list[dict], spot: dict | None = None,
                     sun: dict | None = None, height: int = 620) -> go.Figure:
    """The full week as one instrument: score / swell / wind rows, shared x."""
    if not scored:
        return score_chart._empty_fig()
    if isinstance(spot, dict) and "ideal_wind" not in spot:
        spot = _scoring_spot(spot)
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.40, 0.34, 0.26], vertical_spacing=0.05,
        specs=[[{"secondary_y": False}], [{"secondary_y": True}],
               [{"secondary_y": False}]],
    )
    add_score_traces(fig, scored)
    add_swell_traces(fig, scored)
    add_wind_traces(fig, scored, spot)
    for row in (1, 2, 3):
        add_weekend_shading(fig, scored, row=row, col=1)
    for row in (1, 2):
        score_chart.add_sun_markers(fig, sun, row=row, col=1)

    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 52, "b": 10},
        hovermode="x unified",
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": 1.03,
                "xanchor": "left", "yanchor": "top"},
    )
    fig.update_yaxes(range=[0, 10], title="", row=1, col=1)
    fig.update_yaxes(title="", row=2, col=1)
    fig.update_yaxes(title="", row=2, col=1, secondary_y=True, showgrid=False)
    fig.update_yaxes(visible=False, showticklabels=False, showgrid=False,
                     zeroline=False, range=[0.5, 1.5], row=3, col=1)
    fig.update_xaxes(tickangle=-30)
    return style_fig(fig)


def _tab_layout(fig: go.Figure, height: int, unified: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        # t leaves room for the h-legend + a clear gap so it never blocks
        # the bars/★ at the top of the plot.
        margin={"l": 10, "r": 10, "t": 52, "b": 10},
        hovermode="x unified" if unified else "closest",
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": 1.04,
                "xanchor": "left", "yanchor": "bottom"},
    )
    fig.update_xaxes(tickangle=-30)
    return style_fig(fig)


def build_score_fig(scored: list[dict], sun: dict | None = None,
                    height: int = 300) -> go.Figure:
    """Standalone score tab: traffic-light bars + ★ best hour."""
    if not scored:
        return score_chart._empty_fig()
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1)
    add_score_traces(fig, scored, row=1)
    add_weekend_shading(fig, scored, row=1, col=1)
    score_chart.add_sun_markers(fig, sun, row=1, col=1)
    fig.update_yaxes(range=[0, 10], title="", row=1, col=1)
    return _tab_layout(fig, height)


def build_swell_fig(scored: list[dict], sun: dict | None = None,
                    height: int = 300) -> go.Figure:
    """Standalone swell tab: height (filled) + period (right axis)."""
    if not scored:
        return score_chart._empty_fig()
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
    add_swell_traces(fig, scored, row=1)
    add_weekend_shading(fig, scored, row=1, col=1)
    score_chart.add_sun_markers(fig, sun, row=1, col=1)
    fig.update_yaxes(title="", row=1, col=1)
    fig.update_yaxes(row=1, col=1, secondary_y=True, showgrid=False)
    return _tab_layout(fig, height)


def build_wind_fig(scored: list[dict], spot: dict | None = None,
                   height: int = 220) -> go.Figure:
    """Standalone wind tab: arrows only (colour = quality, size = speed)."""
    if not scored:
        return score_chart._empty_fig()
    if isinstance(spot, dict) and "ideal_wind" not in spot:
        spot = _scoring_spot(spot)
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1)
    add_wind_traces(fig, scored, spot, row=1)
    add_weekend_shading(fig, scored, row=1, col=1)
    fig.update_yaxes(visible=False, showticklabels=False, showgrid=False,
                     zeroline=False, range=[0.5, 1.5], row=1, col=1)
    return _tab_layout(fig, height)


def build_tabbed_figs(scored: list[dict], spot: dict | None = None,
                      sun: dict | None = None) -> tuple[go.Figure, go.Figure, go.Figure]:
    """The week as three standalone charts for the tabbed strip container."""
    return (build_score_fig(scored, sun),
            build_swell_fig(scored, sun),
            build_wind_fig(scored, spot))


CAPTION = _CAPTION
