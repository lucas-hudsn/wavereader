"""Seafloor charts (ported from ``app/seafloor.py``).

2D depth map + 3D surface + shore-normal transects, rendered from a
bathymetry grid dict (``{"lats", "lngs", "elev", "n", ...}``). The seafloor
LLM explainer is cut per plan — deterministic markdown only.
"""

from __future__ import annotations

_EARTH_COLORSCALE = [
    [0.0, "#08306b"],
    [0.25, "#2171b5"],
    [0.45, "#6baed6"],
    [0.55, "#fef0d9"],
    [0.75, "#a8ddb5"],
    [1.0, "#006d2c"],
]

_NO_DATA_FIG_TEXT = "No seafloor data"


def _empty_fig():
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_annotation(text=_NO_DATA_FIG_TEXT, showarrow=False, font={"size": 16})
    return fig


def _grid_n(grid: dict) -> int:
    try:
        return int(grid.get("n", 9))
    except (TypeError, ValueError):
        return 9


def _grid_z(grid: dict) -> list[list[float | None]]:
    n = _grid_n(grid)
    elev = grid.get("elev") or []
    return [[elev[i * n + j] if i * n + j < len(elev) else None for j in range(n)] for i in range(n)]


def build_depth_fig(grid: dict, name: str = ""):
    """2D depth map (blue = deep, green = land) with centre marker."""
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    z = _grid_z(grid)
    fig = go.Figure(
        go.Heatmap(
            x=grid["lngs"],
            y=grid["lats"],
            z=z,
            colorscale=_EARTH_COLORSCALE,
            colorbar={"title": "m"},
            hovertemplate="lat %{y:.4f}<br>lng %{x:.4f}<br>elev %{z:.0f} m<extra></extra>",
            name="depth",
        )
    )
    c = grid.get("center") or {}
    if c:
        fig.add_trace(
            go.Scatter(
                x=[c.get("lng")],
                y=[c.get("lat")],
                mode="markers",
                marker={"size": 12, "color": "#FFD700", "symbol": "star",
                        "line": {"width": 1, "color": "#0b2c5c"}},
                hovertemplate=f"{name} takeoff zone<extra></extra>",
                name="break",
            )
        )
    fig.update_layout(
        title=f"Depth around {name}" if name else "Depth",
        height=340,
        margin={"l": 50, "r": 50, "t": 50, "b": 40},
        xaxis={"title": "lng"},
        yaxis={"title": "lat", "scaleanchor": "x", "scaleratio": 1},
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    return fig


def build_surface_fig(grid: dict, name: str = ""):
    """3D seafloor surface (the 'world model' view)."""
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    z = _grid_z(grid)
    fig = go.Figure(
        go.Surface(
            x=grid["lngs"],
            y=grid["lats"],
            z=z,
            colorscale=_EARTH_COLORSCALE,
            colorbar={"title": "m"},
            hovertemplate="elev %{z:.0f} m<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"3D seafloor — {name}" if name else "3D seafloor",
        height=380,
        margin={"l": 0, "r": 0, "t": 50, "b": 0},
        scene={"xaxis": {"title": "lng"}, "yaxis": {"title": "lat"},
               "zaxis": {"title": "m"}, "aspectmode": "auto"},
        paper_bgcolor="white",
    )
    return fig


def build_transect_fig(grid: dict, name: str = ""):
    """Shore-normal-ish transects: W–E + S–N slices through the centre row/col."""
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    n = _grid_n(grid)
    z = _grid_z(grid)
    mid = n // 2
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=grid["lngs"], y=z[mid], mode="lines+markers",
            line={"color": "#1f77b4", "width": 2},
            name="W–E slice", hovertemplate="lng %{x:.4f}<br>elev %{y:.0f} m<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=grid["lats"], y=[row[mid] for row in z], mode="lines+markers",
            line={"color": "#ff7f0e", "width": 2},
            name="S–N slice", hovertemplate="lat %{x:.4f}<br>elev %{y:.0f} m<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#888")
    fig.update_layout(
        title=f"Transects through {name}" if name else "Transects",
        height=260,
        margin={"l": 50, "r": 30, "t": 50, "b": 40},
        xaxis={"title": "degrees"},
        yaxis={"title": "elevation (m, 0 = sea level)"},
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend={"orientation": "h", "y": 1.12, "x": 1.0, "xanchor": "right"},
    )
    return fig
