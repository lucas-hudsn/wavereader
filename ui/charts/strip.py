"""The week strip: score + swell + wind as ONE synchronized instrument.

One Plotly figure, three stacked rows sharing the time axis — score bars
(0–10, traffic-light), swell height + period, and the wind instrument: a
smooth speed field tinted by direction quality (offshore/cross/onshore
vs. the spot's ideal bearing, night hours dimmed) with vector arrows
riding the curve (rotation = where the wind blows to, size = speed).

Deterministic: renders straight from typed tool payloads (scored hour
dicts + the scoring spot for wind colouring).
"""

from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go

from ui.charts import score as score_chart
from ui.charts._style import INK, add_weekend_shading, style_fig

_COMPASS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

_COMPASS_DEG_16 = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

# Wind colours: direction quality only (size/height encode strength).
_WIND_GOOD = "#1a9850"  # green — offshore / good direction
_WIND_CROSS = "#eab308"  # yellow — cross-shore
_WIND_BAD = "#d73027"  # red — onshore

# Speed-field styling per quality class (fill hugs zero, line rides the top).
_WIND_RUN_STYLES = {
    "offshore": {"line": _WIND_GOOD, "fill_a": 0.20},
    "cross": {"line": "#ca8a04", "fill_a": 0.15},
    "onshore": {"line": _WIND_BAD, "fill_a": 0.13},
    "unknown": {"line": INK, "fill_a": 0.10},
}
_WIND_QUALITY_WORD = {
    "offshore": "offshore", "cross": "cross-shore",
    "onshore": "onshore", "unknown": "(vs ideal unknown)",
}

_CAPTION = (
    "wind field tinted by direction — green offshore · yellow cross-shore · "
    "red onshore — arrows point where it blows to, size = speed, curve "
    "height = kt · ★ best daylight hour · shaded bands = weekend · night dims"
)


def _rgba(hex_c: str, alpha: float) -> str:
    r, g, b = (int(hex_c[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


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


def _wind_quality(wind_from_deg: Any, offshore_from_deg: float | None) -> str | None:
    """'offshore' ≤45°, 'cross' ≤135°, else 'onshore'; None when unknown."""
    if offshore_from_deg is None:
        return None
    try:
        diff = _angular_diff(float(wind_from_deg), float(offshore_from_deg))
    except (TypeError, ValueError):
        return None
    if diff <= 45.0:
        return "offshore"
    if diff <= 135.0:
        return "cross"
    return "onshore"


def _wind_quality_color(wind_from_deg: Any, offshore_from_deg: float | None) -> str:
    """Green (offshore) ≤45°, yellow (cross) ≤135°, else red (onshore)."""
    quality = _wind_quality(wind_from_deg, offshore_from_deg)
    return {
        "offshore": _WIND_GOOD,
        "cross": _WIND_CROSS,
        "onshore": _WIND_BAD,
    }.get(quality, INK)


def _wind_arrow_size(speed_kt: Any) -> float:
    """Arrow diameter in pt: ~11 pt when light → ~19 pt when strong."""
    try:
        s = max(0.0, float(speed_kt))
    except (TypeError, ValueError):
        return 11.0
    return 11.0 + 8.0 * min(s, 30.0) / 30.0


def _deg_to_arrow_angle(deg_from: Any) -> float:
    """Marker angle (clockwise from up) so the arrow points where wind blows TO."""
    try:
        to_deg = (float(deg_from) + 180.0) % 360.0
    except (TypeError, ValueError):
        return 0.0
    return to_deg


def _deg_to_compass(deg: float) -> str:
    """8-point compass label for a meteorological degree."""
    try:
        d = float(deg) % 360.0
    except (TypeError, ValueError):
        return "?"
    return _COMPASS_8[int((d + 22.5) // 45) % 8]


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


def _wind_runs(scored: list[dict], offshore_deg: float | None) -> list[tuple]:
    """Consecutive-hour runs sharing (quality, daylight); gaps break runs.

    Returns ``[((quality, daylight), {"times": [...], "speeds": [...]})]``
    so the speed field can be drawn as one tinted ribbon per regime.
    """
    runs: list[tuple] = []
    key = None
    cur: dict | None = None
    for row in scored:
        quality = _wind_quality(row.get("wind_direction_deg"), offshore_deg)
        try:
            speed = float(row.get("wind_speed_kt"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            speed = None
        if speed is None:
            if cur:
                runs.append((key, cur))
                key, cur = None, None
            continue
        row_key = (quality or "unknown", bool(row.get("daylight", True)))
        if row_key != key and cur:
            runs.append((key, cur))
            cur = None
        key = row_key
        cur = cur or {"times": [], "speeds": []}
        cur["times"].append(row.get("time"))
        cur["speeds"].append(speed)
    if cur:
        runs.append((key, cur))
    return runs


def _speed_ymax(scored: list[dict]) -> float:
    """Headroom top for the wind row: strongest gust + ~35% arrow space."""
    speeds = []
    for row in scored:
        try:
            v = float(row.get("wind_speed_kt"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if v > 0:
            speeds.append(v)
    return max(speeds, default=1.0) * 1.35


def add_wind_traces(fig, scored: list[dict], spot: dict | None = None,
                    row: int = 3) -> go.Figure:
    """The wind instrument: quality-tinted speed field + vector arrows.

    The speed curve (kt) fills to zero as consecutive runs tinted by
    direction quality — green offshore, yellow cross-shore, red onshore,
    ink when the ideal bearing is unknown — night runs dimmed like the
    score bars. On top ride rotated ``arrow`` markers at ~6 h spacing:
    angle = where the wind blows to, size = speed, colour = quality.
    """
    offshore_deg: float | None = None
    if isinstance(spot, dict):
        offshore_deg = _parse_dir_to_deg((spot.get("ideal_wind") or {}).get("direction"))
    for (quality, daylight), run in _wind_runs(scored, offshore_deg):
        style = _WIND_RUN_STYLES[quality]
        dim = 1.0 if daylight else 0.35
        word = _WIND_QUALITY_WORD[quality]
        fig.add_trace(
            go.Scatter(
                x=run["times"], y=run["speeds"],
                mode="lines" if len(run["speeds"]) > 1 else "lines+markers",
                marker={"size": 4, "color": _rgba(style["line"], dim)}
                if len(run["speeds"]) == 1 else {},
                line={"color": _rgba(style["line"], dim), "width": 2,
                      "shape": "spline", "smoothing": 0.55},
                fill="tozeroy", fillcolor=_rgba(style["line"], style["fill_a"] * dim),
                customdata=[f"{s:.0f} kt — {word}" for s in run["speeds"]],
                hovertemplate="%{x}<br>%{customdata}<extra></extra>",
                name="wind", showlegend=False,
            ),
            row=row, col=1,
        )
    # Vector arrows: subsampled so the strip stays readable (~1 per 6 h).
    idx, times, speeds, dirs = [], [], [], []
    step = max(1, len(scored) // 28)
    for i in range(0, len(scored), step):
        row_ = scored[i]
        try:
            speed = float(row_.get("wind_speed_kt"))  # type: ignore[arg-type]
            dir_deg = float(row_.get("wind_direction_deg"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        idx.append(i)
        times.append(row_.get("time"))
        speeds.append(speed)
        dirs.append(dir_deg)
    if idx:
        colors = [_wind_quality_color(d, offshore_deg) for d in dirs]
        alphas = [1.0 if scored[i].get("daylight", True) else 0.45 for i in idx]
        fig.add_trace(
            go.Scatter(
                x=times, y=speeds, mode="markers",
                marker={
                    "symbol": "arrow", "sizemode": "diameter",
                    "size": [_wind_arrow_size(s) for s in speeds],
                    "angle": [_deg_to_arrow_angle(d) for d in dirs],
                    "color": [_rgba(c, a) for c, a in zip(colors, alphas)],
                    "line": {"width": 1.2, "color": INK},
                },
                customdata=[
                    f"{s:.0f} kt from {_deg_to_compass(d)} ({d:.0f}°) — "
                    "arrow points where it blows to"
                    for s, d in zip(speeds, dirs)
                ],
                hovertemplate="%{x}<br>%{customdata}<extra></extra>",
                name="wind arrows", showlegend=False,
            ),
            row=row, col=1,
        )
    return fig


def build_week_strip(scored: list[dict], spot: dict | None = None,
                     height: int = 620) -> go.Figure:
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
                     zeroline=False, range=[0, _speed_ymax(scored)],
                     row=3, col=1)
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


def build_score_fig(scored: list[dict], height: int = 300) -> go.Figure:
    """Standalone score tab: traffic-light bars + ★ best hour."""
    if not scored:
        return score_chart._empty_fig()
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1)
    add_score_traces(fig, scored, row=1)
    add_weekend_shading(fig, scored, row=1, col=1)
    fig.update_yaxes(range=[0, 10], title="", row=1, col=1)
    return _tab_layout(fig, height)


def build_swell_fig(scored: list[dict], height: int = 300) -> go.Figure:
    """Standalone swell tab: height (filled) + period (right axis)."""
    if not scored:
        return score_chart._empty_fig()
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
    add_swell_traces(fig, scored, row=1)
    add_weekend_shading(fig, scored, row=1, col=1)
    fig.update_yaxes(title="", row=1, col=1)
    fig.update_yaxes(row=1, col=1, secondary_y=True, showgrid=False)
    return _tab_layout(fig, height)


def build_wind_fig(scored: list[dict], spot: dict | None = None,
                   height: int = 260) -> go.Figure:
    """Standalone wind tab: speed field + arrows on a visible kt axis."""
    if not scored:
        return score_chart._empty_fig()
    if isinstance(spot, dict) and "ideal_wind" not in spot:
        spot = _scoring_spot(spot)
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1)
    add_wind_traces(fig, scored, spot, row=1)
    add_weekend_shading(fig, scored, row=1, col=1)
    fig.update_yaxes(title="kt", range=[0, _speed_ymax(scored)], row=1, col=1)
    return _tab_layout(fig, height)


def build_tabbed_figs(scored: list[dict],
                      spot: dict | None = None) -> tuple[go.Figure, go.Figure, go.Figure]:
    """The week as three standalone charts for the tabbed strip container."""
    return (build_score_fig(scored),
            build_swell_fig(scored),
            build_wind_fig(scored, spot))


CAPTION = _CAPTION
