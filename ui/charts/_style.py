"""Shared lo-fi chart styling + weekend/night shading for wave~reader figs.

One helper so every chart reads as the same instrument panel: Courier
type, dark-blue ink on white, week shading for weekends and night hours.
Deterministic — pure Plotly layout, no data changes.
"""

from __future__ import annotations

import datetime as _dt

INK = "#0b2c5c"
PAPER = "#ffffff"
PANEL = "#eef6fd"
SHADE = "#d6e9f8"
NIGHT = "#dde7f3"
GRID = "#c9dff2"
FONT = "Courier New, Courier, monospace"


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
                    "bgcolor": PANEL, "bordercolor": INK},
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


def add_weekend_shading(fig, scored: list[dict], axis: str = "x") -> None:
    """Light-blue bands behind Sat+Sun spans on a time axis."""
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
            fig.add_vrect(x0=x0, x1=x1, fillcolor=SHADE, opacity=0.45,
                          line_width=0, layer="below")
        except Exception:  # noqa: BLE001 — shading is cosmetic
            pass


def add_night_shading(fig, scored: list[dict], sunrise_map: dict | None = None) -> None:
    """Optional pale bands over night hours (needs sunrise/sunset per day).

    ``scored`` rows may carry ``sunrise``/``sunset`` ISO strings; hours
    before sunrise or after sunset get a pale band via vrect per gap.
    Cheap heuristic: shade gaps between consecutive day boundaries.
    """
    stamps = []
    for row in scored or []:
        if not isinstance(row, dict):
            continue
        ts = _ts(row.get("time"))
        sr = _ts(row.get("sunrise"))
        ss = _ts(row.get("sunset"))
        if ts is None or sr is None or ss is None:
            return  # no sun info → skip shading entirely
        stamps.append((ts, sr, ss))
    if not stamps:
        return
    stamps.sort()
    for i, (ts, sr, ss) in enumerate(stamps):
        if ts >= sr and ts <= ss:
            continue
        end = stamps[i + 1][0] if i + 1 < len(stamps) else ts + _dt.timedelta(hours=1)
        try:
            fig.add_vrect(x0=ts.replace(tzinfo=None), x1=end.replace(tzinfo=None),
                          fillcolor=NIGHT, opacity=0.35, line_width=0, layer="below")
        except Exception:  # noqa: BLE001 — shading is cosmetic
            pass
