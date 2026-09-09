"""Break map — the lens of the single-page app.

One Scattermap trace (per-point colour = skill level; skill legend is
rendered as HTML chips by the lens panel). Clean carto-positron tiles.
Selecting a spot re-centers the map on it ("fly-to") with a gold star —
point order always matches the ``records`` list so callers can resolve
selections by index.
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


def skill_legend_html() -> str:
    """Lo-fi chips explaining the per-point skill colours."""
    spans = [
        f'<span class="skill-chip"><i style="background:{SKILL_COLORS.get(s, "#1f77b4")}"></i>{s}</span>'
        for s in SKILL_ORDER
    ]
    return '<div class="skill-legend">' + "".join(spans) + "</div>"


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


def build_map(records: list[dict], default_view: bool = False,
              selected: dict | None = None) -> go.Figure:
    """Scattermap of breaks; point order matches ``records`` order.

    Recenters (and zooms) to fit the given records, so filtering
    reframes the map on the matching spots. ``default_view`` frames the
    whole of Australia instead. When ``selected`` is set the map flies
    to that spot (zoom 11.5) and drops a gold takeoff star on it.
    """
    lats = [_lat(r) for r in records]
    lngs = [_lng(r) for r in records]
    names = [r.get("name", "?") for r in records]
    skills = [str(r.get("skillLevel", "?")) for r in records]
    regions = [r.get("region", "?") for r in records]

    sel_lat, sel_lng = (_lat(selected), _lng(selected)) if selected else (None, None)
    valid = [(la, lo) for la, lo in zip(lats, lngs) if la is not None and lo is not None]
    if sel_lat is not None and sel_lng is not None:
        center_lat, center_lng, zoom = sel_lat, sel_lng, 11.5
    elif valid and not default_view:
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
        fig.add_trace(
            go.Scattermap(
                lat=lats,
                lon=lngs,
                mode="markers",
                marker={
                    "size": 10,
                    "color": [SKILL_COLORS.get(s.lower(), "#1f77b4") for s in skills],
                },
                text=names,
                customdata=list(zip(names, regions, skills)),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]} · %{customdata[2]}"
                    "<extra></extra>"
                ),
                name="breaks",
                showlegend=False,
            )
        )
    if selected is not None and sel_lat is not None and sel_lng is not None:
        fig.add_trace(
            go.Scattermap(
                lat=[sel_lat], lon=[sel_lng], mode="markers",
                marker={"size": 16, "color": "#FFD700", "symbol": "star"},
                hovertemplate=f"<b>{selected.get('name', '?')}</b> — selected<extra></extra>",
                name="selected",
                showlegend=False,
            )
        )
    fig.update_layout(
        map_style="carto-positron",
        hovermode="closest",
        height=560,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        map=dict(center={"lat": center_lat, "lon": center_lng}, zoom=zoom),
        showlegend=False,
    )
    if not records:
        fig.add_annotation(
            text="No spots match these filters",
            showarrow=False,
            font={"size": 16},
        )
    return fig
