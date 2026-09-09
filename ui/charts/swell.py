"""Swell chart (ported from ``app/surf_forecast.py``).

Swell height as a filled area (left axis) + period as a line (right).
Renders straight from typed tool payloads.
"""

from __future__ import annotations

import plotly.graph_objects as go

from ui.charts._style import add_weekend_shading
from ui.charts.score import _empty_fig, _strip_layout


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
    add_weekend_shading(fig, scored)
    return _strip_layout(fig, height=230, hide_x=True)
