"""Seafloor charts — the "world model" view (smoothed + animated swell).

From the raw GEBCO n×n bathymetry grid (``{"lats", "lngs", "elev", "n",
...}``) we bicubically upsample to a ~41×41 display surface (scipy
RectBivariateSpline) so the 3D view reads like a real world model rather
than a low-poly sheet. ``build_surface_fig`` optionally adds a translucent
animated swell layer — a sinusoidal water surface gliding over the reef at
the forecast's dominant height/period (Plotly frames + play button).

Stats/markdown keep operating on the RAW grid (see
``wavereader.seafloor.analyze_grid``); smoothing is display-only.
"""

from __future__ import annotations

import math

from ui.charts._style import FONT, INK, style_fig

_EARTH_COLORSCALE = [
    [0.0, "#08306b"],
    [0.25, "#2171b5"],
    [0.45, "#6baed6"],
    [0.55, "#fef0d9"],
    [0.75, "#a8ddb5"],
    [1.0, "#006d2c"],
]

_WATER_COLORSCALE = [
    [0.0, "rgba(13,71,161,0.10)"],
    [0.5, "rgba(33,150,243,0.55)"],
    [1.0, "rgba(224,247,255,0.95)"],
]

_NO_DATA_FIG_TEXT = "No seafloor data"

_DISPLAY_N = 41  # smoothed display resolution (from the raw 10×10)
_FRAMES = 20  # swell animation frames


def _empty_fig():
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_annotation(text=_NO_DATA_FIG_TEXT, showarrow=False, font={"size": 16})
    return fig


def _loading_fig(text: str = "🌍 world model — resolving GEBCO bathymetry…"):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_annotation(text=text, showarrow=False, font={"size": 14})
    fig.update_layout(height=300, margin={"l": 0, "r": 0, "t": 30, "b": 0})
    from ui.charts._style import FONT, INK

    fig.update_layout(font={"family": FONT, "color": INK, "size": 14})
    return fig


def _grid_n(grid: dict) -> int:
    try:
        return int(grid.get("n", 10))
    except (TypeError, ValueError):
        return 10


def _grid_z(grid: dict) -> list[list[float | None]]:
    n = _grid_n(grid)
    elev = grid.get("elev") or []
    return [[elev[i * n + j] if i * n + j < len(elev) else None for j in range(n)] for i in range(n)]


def _smooth_grid(grid: dict, up_n: int = _DISPLAY_N) -> dict | None:
    """Bicubic upsample of the raw grid to ``up_n``×``up_n`` for display.

    Returns ``{"x", "y", "z", "mask_sea"}`` (2D lists, z smoothed,
    ``mask_sea`` True where the smoothed bathymetry is below sea level) or
    None when the grid/interp is unusable — callers fall back to raw.
    """
    import numpy as np

    raw = _grid_z(grid)
    n = len(raw)
    if n < 4 or len(raw[0]) < 4:
        return None
    try:
        from scipy.interpolate import RectBivariateSpline

        arr = np.array(
            [[float(c) if c is not None else np.nan for c in row] for row in raw],
            dtype=float,
        )
        if np.isnan(arr).all():
            return None
        col_mean = np.nanmean(np.where(np.isnan(arr), np.nan, arr), axis=0)
        arr = np.where(np.isnan(arr), col_mean, arr)  # fill rare None cells
        if np.isnan(arr).any():
            arr = np.where(np.isnan(arr), np.nanmean(arr), arr)
        x_raw = np.array(grid["lngs"], dtype=float)
        y_raw = np.array(grid["lats"], dtype=float)
        spl = RectBivariateSpline(y_raw, x_raw, arr, kx=3, ky=3, s=0)
        y_new = np.linspace(y_raw[0], y_raw[-1], up_n)
        x_new = np.linspace(x_raw[0], x_raw[-1], up_n)
        z_new = spl(y_new, x_new)
        return {"x": x_new.tolist(), "y": y_new.tolist(),
                "z": z_new.tolist(), "mask_sea": (z_new < 0.3).tolist()}
    except Exception:  # noqa: BLE001 — display nicety only, fall back to raw
        return None


def _display(grid: dict) -> tuple[dict | None, dict]:
    """Smoothed display grid, or (None, raw) fallback with raw 2D z."""
    n = _grid_n(grid)
    raw2d = {"x": grid.get("lngs") or [], "y": grid.get("lats") or [],
             "z": _grid_z(grid), "mask_sea": None}
    return _smooth_grid(grid), raw2d


def build_depth_fig(grid: dict, name: str = ""):
    """2D depth map (smoothed; blue = deep, green = land) + takeoff star."""
    import numpy as np
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    disp, raw = _display(grid)
    use = disp or raw
    z = np.array(use["z"], dtype=float)
    fig = go.Figure(
        go.Heatmap(
            x=use["x"],
            y=use["y"],
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
    )
    return style_fig(fig)


def _wave_frames(x: list[float], y: list[float], z_bath: list[list[float]],
                 mask_sea: list[list[bool]] | None, height_m: float,
                 period_s: float) -> list:
    """Frames for the animated swell layer (one Surface per phase)."""
    import numpy as np
    import plotly.graph_objects as go

    zn = np.array(z_bath, dtype=float)
    amp = max(0.8, min(3.0, 0.6 + float(height_m or 1.0) * 0.9))
    k = 2.0 * math.pi / max(0.05, (x[1] - x[0]) * 3.0)  # ~3 wavelengths across
    sea = np.array(mask_sea, dtype=bool) if mask_sea is not None else np.ones(zn.shape, dtype=bool)
    X, _Y = np.meshgrid(np.array(x, dtype=float), np.array(y, dtype=float))
    frames = []
    for f in range(_FRAMES):
        phase = 2.0 * math.pi * f / _FRAMES
        wave = amp * np.sin(k * X + phase) + amp * 0.15
        masked = np.where(sea, wave, np.nan)
        frames.append(
            go.Frame(
                data=[go.Surface(
                    x=x, y=y, z=masked.tolist(),
                    colorscale=_WATER_COLORSCALE, opacity=0.55,
                    showscale=False, hoverinfo="skip", name="swell",
                    lighting={"ambient": 0.9}, cmin=-amp * 1.2, cmax=amp * 1.2,
                )],
                traces=[1],
                name=str(f),
            )
        )
    return frames


def build_surface_fig(grid: dict, name: str = "", wave: dict | None = None):
    """3D seafloor surface (smoothed) + optional animated swell layer.

    ``wave`` is ``{"height_m": float, "period_s": float}`` from the scored
    payload — renders a translucent water surface with a ▶ swell play
    button animating it at the forecast's dominant period (2× speed).
    """
    import numpy as np
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    disp, raw = _display(grid)
    use = disp or raw
    x, y = use["x"], use["y"]
    z = np.array(use["z"], dtype=float)
    fig = go.Figure()
    fig.add_trace(
        go.Surface(
            x=x, y=y, z=z,
            colorscale=_EARTH_COLORSCALE,
            colorbar={"title": "m"},
            hovertemplate="elev %{z:.0f} m<extra></extra>",
            lighting={"ambient": 0.75, "diffuse": 0.6},
            name="seafloor",
        )
    )
    have_wave = False
    if wave and (wave.get("height_m") or wave.get("period_s")):
        try:
            base_wave = _wave_frames(x, y, use["z"], use.get("mask_sea"),
                                     float(wave.get("height_m") or 1.0),
                                     float(wave.get("period_s") or 10.0))
            fig.add_trace(base_wave[0].data[0])
            fig.frames = base_wave
            fig.update_layout(
                updatemenus=[{
                    "type": "buttons",
                    "direction": "left",
                    "x": 0.02, "y": 0.98, "xanchor": "left", "yanchor": "top",
                    "bgcolor": "#eef6fd", "bordercolor": "#0b2c5c",
                    "font": {"family": "Courier New", "color": "#0b2c5c", "size": 12},
                    "buttons": [{
                        "label": "▶ swell",
                        "method": "animate",
                        "args": [None, {"frame": {"duration": 90, "redraw": True},
                                        "fromcurrent": True, "mode": "immediate"}],
                    }],
                }]
            )
            have_wave = True
        except Exception:  # noqa: BLE001 — animation is cosmetic
            have_wave = False
    title = f"seafloor model — {name}" if name else "seafloor model"
    if have_wave:
        title += " · animated swell layer"
    fig.update_layout(
        title=title,
        height=430,
        margin={"l": 0, "r": 0, "t": 50, "b": 0},
        scene={
            "xaxis": {"title": {"text": "lng", "font": {"family": FONT, "color": INK, "size": 11}},
                      "tickfont": {"family": FONT, "color": INK, "size": 10}},
            "yaxis": {"title": {"text": "lat", "font": {"family": FONT, "color": INK, "size": 11}},
                      "tickfont": {"family": FONT, "color": INK, "size": 10}},
            "zaxis": {"title": {"text": "m", "font": {"family": FONT, "color": INK, "size": 11}},
                      "tickfont": {"family": FONT, "color": INK, "size": 10}},
            "aspectmode": "auto",
            "camera": {"eye": {"x": -1.55, "y": -1.35, "z": 0.85}},
            "bgcolor": "rgba(238,246,253,0.35)",
        },
        paper_bgcolor="white",
    )
    fig.update_layout(
        font={"family": FONT, "color": INK, "size": 12},
        title={"font": {"family": FONT, "color": INK, "size": 14}},
    )
    return style_fig(fig)


def build_transect_fig(grid: dict, name: str = ""):
    """Shore-normal-ish transects (smoothed): W–E + S–N slices."""
    import numpy as np
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    disp, raw = _display(grid)
    use = disp or raw
    z = np.array(use["z"], dtype=float)
    n_rows = z.shape[0]
    mid = n_rows // 2
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=use["x"], y=z[mid].tolist(), mode="lines",
            line={"color": "#1f77b4", "width": 2},
            name="W–E slice", hovertemplate="lng %{x:.4f}<br>elev %{y:.0f} m<extra></extra>",
            fill="tozeroy", fillcolor="rgba(31,119,180,0.12)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=use["y"], y=z[:, mid].tolist(), mode="lines",
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
        legend={"orientation": "h", "y": 1.12, "x": 1.0, "xanchor": "right"},
    )
    return style_fig(fig)
