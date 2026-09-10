"""Scoring summaries + hero formatting (ported from ``app/surf_forecast.py``).

Deterministic: pure functions over typed tool payloads (lists of scored
hour dicts). Chart traces live in :mod:`ui.charts.strip`; this module
owns the numbers behind them — daily bests, the p75 consistency summary,
and the hero/best markdown formatters.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import plotly.graph_objects as go

from ui.charts._style import GRID, style_fig


def _empty_fig() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="No forecast data", showarrow=False, font={"size": 16})
    return style_fig(fig, height=220)


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


def _daylight(rows: list[dict] | None) -> list[dict]:
    """Recommendation pool: daylight rows only (flag-absent = daylight)."""
    return [r for r in rows or [] if isinstance(r, dict) and r.get("daylight", True)]


def best_window(scored: list[dict]) -> dict | None:
    """Highest-scoring *daylight* hour (the ★ pick), or None when empty.

    Night hours stay on the chart but never win the recommendation.
    """
    pool = _daylight(scored)
    if not pool:
        return None
    return max(pool, key=lambda r: r.get("score", 0))


def daily_best(scored: list[dict]) -> list[dict]:
    """Best daylight hour per calendar date (date = first 10 chars of ``time``)."""
    best_by_date: dict[str, dict] = {}
    for row in _daylight(scored):
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
    """Per-day consistency summary over *daylight* hours: p75, best, surfable.

    v2 ranks days by consistency (p75 of daylight hours), not by a single
    peak hour, and night rows (``daylight: False``) never count. Returns
    ``[{date, p75, best, best_time, hours, surfable}]`` sorted by date,
    where ``hours`` is the daylight-hour count and ``surfable`` those
    scoring >= 6.
    """
    by_date: dict[str, list[dict]] = {}
    for row in _daylight(scored):
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
    """Daily-summary hero as lo-fi day chips (p75 consistency per day).

    Chips carry a score-coloured left border, the day's p75, and its
    surfable-hour count; the most consistent week's peak day gets the ★.
    """
    if not summary:
        return "_Pick a spot — its week summary lands here._"
    top = max((float(d.get("best") or 0)) for d in summary)
    chips = []
    for day in summary:
        try:
            day_name = _dt.date.fromisoformat(str(day["date"])).strftime("%a")
        except ValueError:
            day_name = str(day["date"])[5:]
        star = " ★" if float(day.get("best") or 0) >= top else ""
        color = _score_color(day.get("p75") or 0)
        surf = f"{day['surfable']}/{day['hours']}h"
        chips.append(
            f'<span class="day-chip" style="border-left-color:{color}">'
            f"<b>{day_name}{star}</b><i>p75 {day['p75']} · {surf}</i></span>"
        )
    cap = f'<div class="hero-cap">{label}</div>' if label else ""
    return cap + '<div class="day-chips">' + "".join(chips) + "</div>"


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


def build_compare_fig(rows: list[dict], name_key: str, value_key: str,
                      title: str, sub_keys: tuple[str, ...] = (),
                      out_of: float | None = 10.0) -> go.Figure:
    """Horizontal comparison bars for one agent-turn payload.

    Leaderboards (rank_region_week) and similarity matches
    (find_similar_spots) render as one traffic-light bar per row, top
    pick starred, extra row facts (region, best_time, breakType) in
    hover. Deterministic: straight from the typed tool rows; rows
    missing the value drop out.
    """
    clean = []
    for r in rows or []:
        try:
            v = float(r.get(value_key))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        clean.append((str(r.get(name_key) or "?"), v, r))
    if not clean:
        return _empty_fig()
    clean.sort(key=lambda t: -t[1])
    names = [n for n, _, _ in clean][::-1]  # top pick renders at the top
    vals = [v for _, v, _ in clean][::-1]
    hovers = []
    for name, v, r in reversed(clean):
        bits = [name, f"{v:.1f}" + (f"/{out_of:.0f}" if out_of else "")]
        for k in sub_keys:
            if r.get(k) not in (None, ""):
                bits.append(f"{str(k).replace('_', ' ')}: {r[k]}")
        hovers.append("<br>".join(bits) + "<extra></extra>")
    names[-1] = f"★ {names[-1]}"
    fig = go.Figure(
        go.Bar(
            x=vals, y=list(range(len(vals))), orientation="h",
            marker={"color": [_score_color(v) for v in vals]},
            customdata=hovers, hovertemplate="%{customdata}",
            showlegend=False,
        )
    )
    fig.update_layout(
        title={"text": title, "font": {"size": 13}},
        height=max(240, 44 * len(vals) + 110),
        margin={"l": 10, "r": 30, "t": 56, "b": 40},
        xaxis={"title": "score", "range": [0, 10], "gridcolor": GRID},
        yaxis={"tickmode": "array", "tickvals": list(range(len(vals))),
               "ticktext": names},
    )
    return style_fig(fig)


def build_rank_fig(rows: list[dict], region: str = "") -> go.Figure:
    """Agent leaderboard: best score per spot from a rank_region_week sweep."""
    region_bit = f" · {region}" if region else ""
    return build_compare_fig(
        rows, "name", "best_score",
        f"region sweep — best score this week{region_bit}",
        sub_keys=("region", "best_time"),
    )


def build_similarity_fig(rows: list[dict], ref: str = "") -> go.Figure:
    """Agent comparison: how like the reference spot each match is."""
    ref_bit = f" — like {ref}" if ref else ""
    return build_compare_fig(rows, "name", "similarity",
                             f"similar spots{ref_bit}", sub_keys=("region", "breakType"),
                             out_of=None)


def build_component_fig(components: dict, spot: str = "", when: str = "",
                        score: Any = None) -> go.Figure:
    """Component split for one explained hour (explain_score payload).

    The four scorer components (swell size / direction, wind, period) as
    traffic-light bars on the 0–10 scale, the hour's total score in the
    title — the WHY of a score, straight from the tool payload.
    """
    pretty = {"swell_size": "swell size", "swell_direction": "swell dir",
              "wind": "wind", "period": "period"}
    labels: list[str] = []
    vals: list[float] = []
    for k, v in components.items():
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
        labels.append(pretty.get(str(k), str(k).replace("_", " ")))
    if not vals:
        return _empty_fig()
    sub = f"score {score}/10" if score is not None else ""
    if when:
        sub = f"{when} · {sub}" if sub else str(when)
    title = "why this score — component split"
    if spot:
        title += f" — {spot}"
    if sub:
        title += f"<br><sub>{sub}</sub>"
    fig = go.Figure(
        go.Bar(
            x=list(range(len(vals))), y=vals,
            marker={"color": [_score_color(v) for v in vals]},
            customdata=[f"{l}: {v:.1f}/10" for l, v in zip(labels, vals)],
            hovertemplate="%{customdata}<extra></extra>", showlegend=False,
        )
    )
    fig.update_layout(
        title={"text": title, "font": {"size": 13}},
        height=280,
        margin={"l": 30, "r": 30, "t": 60, "b": 30},
        yaxis={"title": "component score", "range": [0, 10], "gridcolor": GRID},
        xaxis={"tickmode": "array", "tickvals": list(range(len(vals))),
               "ticktext": labels},
        bargap=0.35,
    )
    return style_fig(fig)
