"""Climate charts (new for v2).

Renders the 5-year ERA5 swell climatology profile produced by Worker B
(``wavereader/climate.py``): the polar direction rose and the monthly
"when to go" view. All render from plain dicts so the stub profile
works identically.

Visual language: same as the rest of the instrument panel — one ink on
paper, two tones only. Ordinary values sit in a muted blue; the top
pick(s) carry full ink. Season bands reuse the weekend-shading tone, so
the page still reads as one instrument. Everything beyond the headline
number (% of days) lives in hover, never as a second overlaid axis or a
second color scale.

Interpretability contract (what a first-time reader must get without
hovering):
- the year chart counts **% of each month's days** in the break's ideal
  size window — the axis title names the window (e.g. "4–12 ft");
- the rose names the dominant swell in words and marks the dataset's
  *stated* ideal directions with ◇, so agreement/mismatch is visible;
- southern-hemisphere season bands sit behind the months (Australia is
  the whole catalogue), tying the chart to the ``bestSeason`` vocabulary.
"""

from __future__ import annotations

_DIRECTIONS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

_MONTH_ABBR = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]

# Southern hemisphere (mirrors SEASON_MONTHS in wavereader.climate).
_SEASONS = [("summer", [12, 1, 2]), ("autumn", [3, 4, 5]),
            ("winter", [6, 7, 8]), ("spring", [9, 10, 11])]

_SHADED_SEASONS = {"summer", "winter"}  # alternating bands; autumn/spring stay paper


def _top_n_indices(vals: list[float], n: int) -> set[int]:
    ranked = sorted(range(len(vals)), key=lambda i: -vals[i])
    return set(ranked[:n])


def _season_bands() -> list[tuple[float, float, str, float]]:
    """Season bands as ``(x0, x1, label, label_x)`` on the month axis 0..11.

    Summer wraps the year end (Dec–Feb), so it splits into two rects; the
    label sits over the middle month of each season.
    """
    runs: list[tuple[list[int], str]] = []
    for label, months in _SEASONS:
        idx = sorted(m - 1 for m in months)  # month 1..12 -> index 0..11
        run = [idx[0]]
        for i in idx[1:]:
            if i == run[-1] + 1:
                run.append(i)
            else:
                runs.append((run, label))
                run = [i]
        runs.append((run, label))
    return [(r[0] - 0.5, r[-1] + 1.5, label, sum(r) / len(r))
            for r, label in runs]


def _dominant(rose: dict[str, float], n: int = 2) -> tuple[list[tuple[str, float]], float]:
    """Top-n rose bins as (label, pct) pairs + their cumulative share."""
    ranked = sorted(((d, float(rose.get(d) or 0)) for d in _DIRECTIONS_16),
                    key=lambda kv: -kv[1])
    return ranked[:n], round(sum(p for _, p in ranked[:n]), 1)


def build_rose_fig(profile: dict | None, name: str = "",
                   ideal_dirs: list[str] | None = None):
    """Polar bar rose of swell-direction frequency (%) from a climate profile.

    ``profile`` shape: ``{"rose": {dir: pct}, ...}``. Full ink for the top-3
    bins, muted for the rest. A subtitle states the dominant swell in words
    ("SW carries 63% of days"); the break's stated ideal directions (from
    ``idealSwell.direction``) are marked ◇ so stated-vs-observed agreement
    reads at a glance. Empty profile → placeholder.
    """
    import plotly.graph_objects as go
    from ui.charts._style import GRID, INK, MUTED, style_fig

    rose = (profile or {}).get("rose") or {}
    vals = [float(rose.get(d, 0) or 0) for d in _DIRECTIONS_16]
    if not any(v > 0 for v in vals):
        fig = go.Figure()
        fig.add_annotation(
            text="no ERA5 profile for this spot yet<br><sub>its 5-yr swell climate lands here when built</sub>",
            showarrow=False, font={"size": 13})
        fig.update_layout(height=300, margin={"l": 30, "r": 30, "t": 50, "b": 20})
        return fig
    top = _top_n_indices(vals, 3)
    fig = go.Figure(
        go.Barpolar(
            r=vals,
            theta=_DIRECTIONS_16,
            marker={
                "color": [INK if i in top else MUTED for i in range(16)],
                "line": {"width": 0.5, "color": INK},
            },
            hovertemplate="%{theta}: %{r:.1f}% of days<extra></extra>",
            name="swell direction",
        )
    )
    # The one-sentence answer: which way the swell comes from, and how much
    # of the record the top directions explain.
    dom, top_share = _dominant(rose, 2)
    subtitle = (f"dominant swell {dom[0][0]} — {dom[0][1]:.0f}% of days · "
                f"top-2 carry {top_share:.0f}%")
    stated = [str(d).strip().upper() for d in (ideal_dirs or [])]
    stated = [d for d in stated if d in _DIRECTIONS_16]
    vmax = max(vals)
    if stated:
        subtitle += " · ◇ stated ideal"
        fig.add_trace(
            go.Scatterpolar(
                r=[vmax * 1.08] * len(stated),
                theta=stated,
                mode="markers",
                marker={"symbol": "diamond-open", "size": 9,
                        "line": {"width": 1.5, "color": INK}},
                hovertemplate="stated ideal: %{theta}<extra>dataset idealSwell</extra>",
                name="stated ideal",
                showlegend=False,
            )
        )
    ticks = sorted({t for t in (10, 25, 50, 75) if t < vmax} | {round(vmax)})
    fig.update_layout(
        title={
            "text": (f"swell climate — {name}" if name else "swell climate")
                    + f"<br><sub>{subtitle}</sub>",
            "font": {"size": 13},
        },
        height=340,
        margin={"l": 30, "r": 30, "t": 70, "b": 20},
        polar={
            "angularaxis": {
                "direction": "clockwise",
                "rotation": 90,
                # label only the 8 cardinal/intercardinal spokes
                "tickmode": "array",
                "tickvals": _DIRECTIONS_16[::2],
                "ticktext": _DIRECTIONS_16[::2],
                "gridcolor": GRID,
                "linecolor": GRID,
            },
            "radialaxis": {
                "tickmode": "array",
                "tickvals": ticks,
                "ticktext": [f"{t}%" for t in ticks],  # ticksuffix dies in array mode
                "gridcolor": GRID,
                "linecolor": GRID,
            },
            "bgcolor": "rgba(0,0,0,0)",
        },
    )
    return style_fig(fig)


def build_year_fig(monthly: list[dict] | None, name: str = "",
                   window_label: str = ""):
    """The "when to go" view: share of each month's days in the ideal window.

    ``monthly`` is ``[{month, height_m, period_s, days, n_days?, pct?}]``
    (12 entries) from :func:`ui._compat.get_climate_monthly`. The bar
    height is the **% of that month's days** whose swell fell in the
    break's ideal size window (falls back to raw 5-yr day counts when the
    entries carry no ``n_days``). Full ink marks the top-3 months; season
    bands (southern hemisphere) sit behind; median height/period ride in
    hover. None/empty → graceful placeholder.
    """
    import plotly.graph_objects as go
    from ui.charts._style import GRID, INK, MUTED, SHADE, style_fig

    if not monthly:
        fig = go.Figure()
        fig.add_annotation(
            text="no climate profile for this spot yet — the ERA5 5-yr view lands when built",
            showarrow=False, font={"size": 14})
        fig.update_layout(height=240, margin={"l": 30, "r": 30, "t": 40, "b": 20})
        return fig

    labels = [_MONTH_ABBR[int(m["month"]) - 1] for m in monthly]
    days = [float(m.get("days") or 0) for m in monthly]
    n_days = [m.get("n_days") for m in monthly]
    heights = [m.get("height_m") for m in monthly]
    periods = [m.get("period_s") for m in monthly]
    use_pct = all(m.get("pct") is not None for m in monthly) or all(n_days)
    if all(m.get("pct") is not None for m in monthly):
        y = [float(m["pct"]) for m in monthly]
    elif use_pct:
        y = [100.0 * d / n if n else 0.0 for d, n in zip(days, n_days)]
    else:
        y = days
    top = _top_n_indices(y, 3)
    # numeric x + tick labels: single-letter months repeat (J/M/A), which
    # Plotly would otherwise merge into one shared category per letter
    xpos = list(range(12))
    unit = "% of days in window" if use_pct else "ideal days / 5 yr"
    hover = [
        "{} · {:.0f}{} · {}/{} days over 5 yr{}{}".format(
            _MONTH_NAMES[int(monthly[i]["month"]) - 1],
            y[i], "%" if use_pct else " days",
            int(days[i]), int(n_days[i]) if n_days[i] else "?",
            f" · median {heights[i]:.1f} m" if heights[i] is not None else "",
            f" @ {periods[i]:.0f}s" if periods[i] is not None else "",
        )
        for i in range(12)
    ]
    fig = go.Figure(
        go.Bar(
            x=xpos, y=y,
            marker={"color": [INK if i in top else MUTED for i in range(12)]},
            customdata=hover,
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=False,
        )
    )
    for x0, x1, label, lx in _season_bands():
        if label in _SHADED_SEASONS:
            fig.add_vrect(x0=x0, x1=x1, fillcolor=SHADE, opacity=0.55,
                          line_width=0, layer="below")
        fig.add_annotation(x=lx, y=1.06, xref="x", yref="paper",
                           text=label.upper(), showarrow=False,
                           font={"size": 10,
                                 "color": INK if label in _SHADED_SEASONS else MUTED})
    ymax = 105.0 if use_pct else max(y) * 1.15 + 1
    fig.update_layout(
        height=260,
        margin={"l": 30, "r": 30, "t": 26, "b": 20},
        yaxis={"title": (f"swell {window_label} · {unit}" if window_label and use_pct
                         else unit),
               "gridcolor": GRID, "range": [0, ymax],
               "tickvals": ([0, 25, 50, 75, 100] if use_pct else None)},
        xaxis={"gridcolor": GRID, "tickmode": "array",
               "tickvals": xpos, "ticktext": labels, "range": [-0.5, 11.5]},
        bargap=0.35,
    )
    return style_fig(fig)
