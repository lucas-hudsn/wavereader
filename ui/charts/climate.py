"""Climate rose + audit-finding chips (new for v2).

Renders the 5-year ERA5 swell-direction climatology profile produced by
Worker B (``wavereader/climate.py``) as a polar bar rose, and formats
``audit_break`` findings as lo-fi chips. Both render from plain dicts so
the stub profile works identically to the real one.
"""

from __future__ import annotations

_DIRECTIONS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def build_rose_fig(profile: dict | None, name: str = ""):
    """Polar bar rose of swell-direction frequency (%) from a climate profile.

    ``profile`` shape: ``{"rose": {dir: pct}, "best_months": [...],
    "median_height_m": f, "median_period_s": f}``. Empty profile → placeholder.
    """
    import plotly.graph_objects as go

    rose = (profile or {}).get("rose") or {}
    vals = [float(rose.get(d, 0) or 0) for d in _DIRECTIONS_16]
    if not any(v > 0 for v in vals):
        fig = go.Figure()
        fig.add_annotation(text="No climate data yet", showarrow=False, font={"size": 16})
        fig.update_layout(height=300, margin={"l": 30, "r": 30, "t": 50, "b": 20},
                          paper_bgcolor="white")
        return fig
    fig = go.Figure(
        go.Barpolar(
            r=vals,
            theta=_DIRECTIONS_16,
            marker={"color": "#1f77b4", "line": {"width": 1, "color": "#0b2c5c"}},
            hovertemplate="%{theta}: %{r:.1f}% of days<extra></extra>",
            name="swell direction",
        )
    )
    months = ", ".join((profile or {}).get("best_months") or [])
    subtitle = f" — best months: {months}" if months else ""
    fig.update_layout(
        title=f"Swell climate — {name}{subtitle}" if name else f"Swell climate{subtitle}",
        height=340,
        margin={"l": 30, "r": 30, "t": 60, "b": 20},
        polar={"angularaxis": {"direction": "clockwise"},
               "radialaxis": {"ticksuffix": "%"}},
        paper_bgcolor="white",
    )
    return fig


def format_findings(findings: list[dict] | None) -> str:
    """Format audit findings as lo-fi chips (HTML pills + emoji severity)."""
    if not findings:
        return "_No climate audit yet — pick a break._"
    icon = {"ok": "✅", "info": "ℹ️", "warn": "⚠️", "error": "❌"}
    chips = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        level = str(f.get("level", "info")).lower()
        if level not in ("ok", "info", "warn", "error"):
            level = "info"
        msg = str(f.get("message", "")).replace("<", "&lt;").replace(">", "&gt;")
        chips.append(
            f"<span class=\"audit-chip audit-{level}\">"
            f"{icon.get(level, 'ℹ️')} {msg}</span>"
        )
    if not chips:
        return "_No climate audit yet — pick a break._"
    return "<div class=\"audit-chips\">" + " ".join(chips) + "</div>"
