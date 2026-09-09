"""Score chart + scoring summaries (ported from ``app/surf_forecast.py``).

Deterministic: renders straight from typed tool payloads (lists of scored
hour dicts). Adds :func:`daily_summary` (p75 of scores per day) for the
swell-panel hero.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from ui.charts._style import add_weekend_shading, style_fig


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


def _percentile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return 0.0
    return s[max(0, min(len(s) - 1, int(q * len(s))))]


def daily_summary(scored: list[dict]) -> list[dict]:
    """Per-day consistency summary: p75 score, best hour, surfable count.

    v2 ranks days by consistency (p75 of daylight hours), not by a single
    peak hour. Returns ``[{date, p75, best, best_time, hours, surfable}]``
    sorted by date, where ``surfable`` counts hours scoring >= 6.
    """
    by_date: dict[str, list[dict]] = {}
    for row in scored or []:
        date = str(row.get("time", ""))[:10]
        if date:
            by_date.setdefault(date, []).append(row)
    out = []
    for date in sorted(by_date):
        rows = by_date[date]
        scores = [float(r.get("score") or 0) for r in rows]
        best = max(rows, key=lambda r: float(r.get("score") or 0))
        out.append(
            {
                "date": date,
                "p75": round(_percentile(scores, 0.75), 1),
                "best": best.get("score"),
                "best_time": best.get("time"),
                "hours": len(rows),
                "surfable": sum(1 for s in scores if s >= 6),
            }
        )
    return out


def _strip_layout(fig: go.Figure, height: int = 230, hide_x: bool = False) -> go.Figure:
    """Compact shared styling so the forecast strips read as one."""
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
    fig.update_yaxes(showgrid=True)
    return style_fig(fig, height=height)


def add_sun_markers(fig: go.Figure, sun: dict | None) -> go.Figure:
    """Overlay sunrise (dotted gold) / sunset (dashed orange) verticals.

    ``sun`` is the ``daily`` frame (``{"sunrise": [...], "sunset": [...]}``);
    no-op when absent.
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
    add_weekend_shading(fig, scored)
    return _strip_layout(fig, height=230, hide_x=True)


def format_best(best: dict | None, label: str | None = None,
                skill: str | None = None) -> str:
    """Format a best_window() hour as markdown for hero/status lines."""
    if not best:
        return "_No scored hours in this window._"
    base = (
        f"**{best.get('score')}/10 @ {best.get('time')}** — "
        f"{best.get('wave_height_m')}m @ {best.get('wave_period_s')}s, "
        f"wind {best.get('wind_speed_kt')}kt "
        f"({best.get('wind_direction_deg')}°)"
    )
    suffix_bits = [b for b in (label, skill) if b]
    if suffix_bits:
        base += f" · _{' · '.join(suffix_bits)}_"
    return base


def format_hero(summary: list[dict], label: str | None = None) -> str:
    """Daily-summary hero markdown (p75 consistency per day)."""
    if not summary:
        return "_Pick a break — its week summary lands here._"
    lines = []
    for day in summary:
        mark = "✅" if day["surfable"] >= 3 else ("🟡" if day["surfable"] else "⬜")
        lines.append(
            f"{mark} **{day['date']}** — p75 {day['p75']}/10 · "
            f"best {day['best']} @ {day['best_time']} · "
            f"{day['surfable']}/{day['hours']} surfable hrs"
        )
    head = f"### {label} — week ahead (p75 daily consistency)\n" if label else "### week ahead (p75 daily consistency)\n"
    return head + "\n".join(lines)


def coerce_scored_hours(payload: Any) -> list[dict] | None:
    """Coerce a score_week tool_result payload to scored hour dicts.

    Accepts a list of dicts, a ``{"scored": [...]}`` wrapper, or a
    ``{"windows": [...]}`` slim shape. Returns None when not scorable.
    """
    if isinstance(payload, dict) and isinstance(payload.get("scored"), list):
        payload = payload["scored"]
    if isinstance(payload, dict) and isinstance(payload.get("windows"), list):
        payload = payload["windows"]
    if not isinstance(payload, list) or not payload:
        return None
    if not all(isinstance(r, dict) and "score" in r and "time" in r for r in payload):
        return None
    return payload
