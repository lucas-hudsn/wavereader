"""Shared lo-fi chart styling + weekend shading for wave~reader figs.

One helper so every chart reads as the same instrument panel: IBM Plex
Mono (Courier fallback), dark-blue ink on the page-blue paper, weekend
shading. Deterministic — pure Plotly layout, no data changes.
"""

from __future__ import annotations

import datetime as _dt

INK = "#0b2c5c"
MUTED = "#a9c8e6"  # second tone for climate charts: ordinary values vs INK picks
PAPER = "#eef6fd"
PANEL = "#eef6fd"
SHADE = "#d6e9f8"
GRID = "#c9dff2"
FONT = "'IBM Plex Mono', 'Courier New', Courier, monospace"


def style_fig(fig, height: int | None = None, title: str | None = None):
    """Apply the lo-fi identity to a Plotly figure (fonts, grid, paper)."""
    fig.update_layout(
        font={"family": FONT, "color": INK, "size": 12},
        title={"font": {"family": FONT, "color": INK, "size": 14}}
        if title is not None else {},
        paper_bgcolor=PAPER,
        plot_bgcolor=PAPER,
        coloraxis={"colorbar": {"tickfont": {"family": FONT, "color": INK}}},
        hoverlabel={"font": {"family": FONT, "color": INK},
                    "bgcolor": "#ffffff", "bordercolor": INK},
        legend={"font": {"family": FONT, "color": INK}},
    )
    fig.update_xaxes(
        gridcolor=GRID, zerolinecolor=GRID,
        tickfont={"family": FONT, "color": INK},
        title_font={"family": FONT, "color": INK},
        linecolor=INK,
    )
    fig.update_yaxes(
        gridcolor=GRID, zerolinecolor=GRID,
        tickfont={"family": FONT, "color": INK},
        title_font={"family": FONT, "color": INK},
        linecolor=INK,
    )
    if height:
        fig.update_layout(height=height)
    if title is not None:
        fig.update_layout(title=title)
    return fig


def _ts(value) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def add_weekend_shading(fig, scored: list[dict], **vrect_kw) -> None:
    """Light-blue bands behind Sat+Sun spans on a time axis.

    Extra kwargs (e.g. ``row=``/``col=`` for subplot grids) pass straight
    through to ``fig.add_vrect``.
    """
    days: dict[_dt.date, list[float]] = {}
    for row in scored or []:
        ts = _ts(row.get("time") if isinstance(row, dict) else row)
        if ts is None:
            continue
        days.setdefault(ts.date(), []).append(_dt.datetime.timestamp(ts))
    if not days:
        return
    for date, stamps in days.items():
        if date.weekday() < 5:
            continue
        x0 = _dt.datetime.fromtimestamp(min(stamps)).astimezone()
        x1 = _dt.datetime.fromtimestamp(max(stamps)).astimezone()
        x0 = x0.replace(tzinfo=None)
        x1 = x1.replace(tzinfo=None)
        try:
            fig.add_vrect(x0=x0, x1=x1, fillcolor=SHADE, opacity=0.5,
                          line_width=0, layer="below", **vrect_kw)
        except Exception:  # noqa: BLE001 — shading is cosmetic
            pass
