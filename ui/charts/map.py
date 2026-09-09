"""Break map (ported from ``app/maps.py``).

Scattermap of breaks, marker colour by skill level. Point order matches
``records`` order. Custom-break overlay cut per plan.
"""

from __future__ import annotations

from plotly import graph_objects as go

try:  # keep colours identical to the v1 front end while it exists
    from app.config import AUSTRALIA_CENTER, AUSTRALIA_ZOOM, SKILL_COLORS, SKILL_ORDER
except ImportError:  # self-contained fallback (app/ is deleted at deploy)
    AUSTRALIA_CENTER = {"lat": -25.5, "lon": 134.0}
    AUSTRALIA_ZOOM = 3.5
    SKILL_ORDER = ["beginner", "intermediate", "advanced", "expert", "pro-only"]
    SKILL_COLORS = {
        "beginner": "#2ca02c",
        "intermediate": "#1f77b4",
        "advanced": "#ff7f0e",
        "expert": "#d62728",
        "pro-only": "#9467bd",
    }


def _lat(break_: dict) -> float | None:
    try:
        return float(break_["location"]["coordinates"]["lat"])
    except (KeyError, TypeError, ValueError):
        return None


def _lng(break_: dict) -> float | None:
    try:
        return float(break_["location"]["coordinates"]["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def _zoom_for_span(span: float) -> float:
    """Pick a map zoom level that fits a lat/lng degree span."""
    if span > 25:
        return 3.5
    if span > 12:
        return 4.2
    if span > 6:
        return 5.0
    if span > 3:
        return 6.0
    if span > 1.5:
        return 7.0
    if span > 0.7:
        return 8.0
    if span > 0.3:
        return 9.0
    return 10.0


def build_map(records: list[dict], default_view: bool = False) -> go.Figure:
    """Scattermap of breaks; point order matches ``records`` order.

    Recenters (and zooms) to fit the given records, so filtering
    reframes the map on the matching spots — unless ``default_view``
    is set, which frames the whole of Australia.
    """
    lats = [_lat(r) for r in records]
    lngs = [_lng(r) for r in records]
    names = [r.get("name", "?") for r in records]
    skills = [str(r.get("skillLevel", "?")) for r in records]
    regions = [r.get("region", "?") for r in records]

    valid = [(la, lo) for la, lo in zip(lats, lngs) if la is not None and lo is not None]
    if valid and not default_view:
        center_lat = sum(la for la, _ in valid) / len(valid)
        center_lng = sum(lo for _, lo in valid) / len(valid)
        span = max(
            max(la for la, _ in valid) - min(la for la, _ in valid),
            max(lo for _, lo in valid) - min(lo for _, lo in valid),
        )
        zoom = _zoom_for_span(span)
    else:
        center_lat, center_lng, zoom = (
            AUSTRALIA_CENTER["lat"],
            AUSTRALIA_CENTER["lon"],
            AUSTRALIA_ZOOM,
        )

    fig = go.Figure()
    if records:
        # One trace per skill level so the map gets a skill-level legend
        # on top (a single trace with per-point colours shows no legend).
        by_skill: dict[str, list[int]] = {}
        for i, s in enumerate(skills):
            by_skill.setdefault(s.lower(), []).append(i)
        ordered = [s for s in SKILL_ORDER if s in by_skill]
        ordered += [s for s in by_skill if s not in SKILL_ORDER]
        for skill_key in ordered:
            idx = by_skill[skill_key]
            # Preserve the canonical label casing from the first record.
            label = skills[idx[0]]
            fig.add_trace(
                go.Scattermap(
                    lat=[lats[i] for i in idx],
                    lon=[lngs[i] for i in idx],
                    mode="markers",
                    marker={
                        "size": 10,
                        "color": SKILL_COLORS.get(skill_key, "#1f77b4"),
                    },
                    text=[names[i] for i in idx],
                    customdata=[(names[i], regions[i], skills[i]) for i in idx],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "%{customdata[1]} · %{customdata[2]}"
                        "<extra></extra>"
                    ),
                    name=label,
                )
            )
    fig.update_layout(
        map_style="open-street-map",
        hovermode="closest",
        height=550,
        margin={"l": 0, "r": 0, "t": 30, "b": 0},
        map=dict(center={"lat": center_lat, "lon": center_lng}, zoom=zoom),
        showlegend=True,
        legend={"orientation": "h", "y": 1.02, "x": 0},
    )
    if not records:
        fig.add_annotation(
            text="No spots match these filters",
            showarrow=False,
            font={"size": 16},
        )
    return fig
