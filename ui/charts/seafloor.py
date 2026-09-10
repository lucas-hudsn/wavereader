"""Seafloor charts — the "world model" view (smoothed + animated swell).

From the raw GEBCO n×n bathymetry grid (``{"lats", "lngs", "elev", "n",
...}``) we bicubically upsample to a ~41×41 display surface (scipy
RectBivariateSpline) so the 3D view reads like a real world model rather
than a low-poly sheet. ``build_surface_fig`` optionally adds a translucent
animated swell layer — a sinusoidal water surface gliding over the reef at
the forecast's dominant height/period (▶ play button; the frames ride in
the button's args because Gradio's gr.Plot drops ``fig.frames``).

Stats/markdown keep operating on the RAW grid (see
``wavereader.seafloor.analyze_grid``); smoothing is display-only.
"""

from __future__ import annotations

import math

from ui.charts._style import FONT, INK, style_fig

_SAND = "#e8d5a3"  # sand — pinned to elevation 0 in _earth_scale()

_DEEP_STOPS = [  # sea: 0 m → -_DEEP_REF m
    [0.0, "#08306b"],
    [0.5, "#2171b5"],
    [0.85, "#6baed6"],
]
_LAND_STOPS = [  # land: 0 m → +_LAND_REF m
    [0.15, "#a8ddb5"],
    [1.0, "#006d2c"],
]
_DEEP_REF = 40.0  # reference depth (m) for the sea end of the scale
_LAND_REF = 20.0  # reference elevation (m) for the land end of the scale

_WATER_COLORSCALE = [
    [0.0, "rgba(13,71,161,0.10)"],
    [0.6, "rgba(33,150,243,0.55)"],
    [0.9, "rgba(159,222,255,0.85)"],
    [1.0, "rgba(255,255,255,0.95)"],  # whitewater on the crest
]

_NO_DATA_FIG_TEXT = "No seafloor data"

_DISPLAY_N = 41  # smoothed display resolution (from the raw 10×10)
_FRAMES = 20  # swell animation frames
_M_PER_DEG_LAT = 111_320.0  # metres per degree of latitude (boxes are ~2 km)


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
    fig.update_layout(font={"family": FONT, "color": INK, "size": 14})
    return fig


def _earth_scale(z) -> tuple[list, float, float]:
    """Colorscale + cmin/cmax with sand pinned exactly at elevation 0.

    Plotly normalizes colors by (z - cmin)/(cmax - cmin), so we place the
    sand stop at 0's normalized position rather than a fixed fraction.
    """
    import numpy as np

    zmin = float(np.nanmin(z))
    zmax = float(np.nanmax(z))
    cmin = min(zmin, -_DEEP_REF * 0.25)
    cmax = max(zmax, _LAND_REF * 0.25)
    zero = -cmin / (cmax - cmin) if cmax > cmin else 0.5
    zero = min(max(zero, 0.02), 0.98)
    stops = [[p * zero, c] for p, c in _DEEP_STOPS]
    stops.append([zero, _SAND])
    stops += [[zero + p * (1.0 - zero), c] for p, c in _LAND_STOPS]
    return stops, cmin, cmax


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
    colorscale, cmin, cmax = _earth_scale(z)
    fig = go.Figure(
        go.Heatmap(
            x=use["x"],
            y=use["y"],
            z=z,
            colorscale=colorscale,
            zmin=cmin,
            zmax=cmax,
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


def _wave_kinematics(x: list[float], y: list[float],
                     period_s: float) -> tuple[float, int, float]:
    """Wavenumber (m⁻¹) + frame duration (ms) + lng metric for the swell.

    Deep-water physics drives the display: wavelength L ≈ 1.56·T² metres,
    clamped to 1.5–5 wavelengths across the box so it stays visible; frame
    duration is the real period spread over ``_FRAMES`` frames (clamped
    40–200 ms). Also returns metres-per-degree-longitude at the box's mean
    latitude, so ``_wave_frames`` can build the field in metres — a degree
    of lng is not a degree of lat, and the rotated wave mixes both axes.
    """
    span_deg = max(1e-6, float(x[-1]) - float(x[0]))
    try:
        mean_lat = (float(y[0]) + float(y[-1])) / 2.0
    except (TypeError, ValueError, IndexError):
        mean_lat = -30.0
    m_per_deg_lng = _M_PER_DEG_LAT * math.cos(math.radians(abs(mean_lat)))
    span_m = span_deg * m_per_deg_lng
    wavelength_m = 1.56 * max(1.0, float(period_s)) ** 2
    wavelength_m = min(max(wavelength_m, span_m / 5.0), span_m / 1.5)
    duration_ms = int(min(200.0, max(40.0, 1000.0 * float(period_s) / _FRAMES)))
    return 2.0 * math.pi / wavelength_m, duration_ms, m_per_deg_lng


def _wave_frames(x: list[float], y: list[float], z_bath: list[list[float]],
                 mask_sea: list[list[bool]] | None, height_m: float,
                 period_s: float,
                 direction_deg: float | None = None) -> tuple[object, list[dict], int]:
    """Initial swell Surface + ▶-button frame list + frame duration.

    ``direction_deg`` is the bearing the swell arrives FROM (Open-Meteo
    convention, clockwise from north) — the wave travels the opposite
    bearing, rotated through the box in metres. No direction keeps the old
    westward default.

    Shoaling like a real breaking wave: Green's law amplifies the crest as
    depth decreases (∝ √(h_deep/h)), the trough is flattened and the crest
    sharpened (≈ cnoidal/spilling profile), and where the water is too
    shallow to carry the wave — depth under ~1.5× the crest height — the
    surface becomes whitewater and dies to NaN (broken). Whitewater is
    coloured by the water colorscale's white top stop.

    Frames are plain ``{"data": [{"z": …}], "traces": [1]}`` dicts riding
    inside the ▶ button's ``args[0]`` — plotly.js ``animate`` accepts a raw
    frame-object list there, while Gradio's ``gr.Plot`` client renders with
    ``Plotly.react(gd, data, layout, config)`` and drops ``fig.frames``, so
    registered frames never reach the browser. Only ``z`` changes per frame
    (x/y are constant) and is quantised to 2 dp to keep the payload small.
    """
    import numpy as np
    import plotly.graph_objects as go

    zn = np.array(z_bath, dtype=float)
    depth = np.clip(-zn, 0.0, None)  # positive seaward depth
    sea = np.array(mask_sea, dtype=bool) if mask_sea is not None else np.ones(zn.shape, dtype=bool)
    base_amp = max(0.25, min(1.2, 0.35 * float(height_m or 1.0)))
    k, duration_ms, m_per_deg_lng = _wave_kinematics(x, y, period_s)
    X, Y = np.meshgrid(np.array(x, dtype=float), np.array(y, dtype=float))
    Xm = (X - float(x[0])) * m_per_deg_lng  # metres east
    Ym = (Y - float(y[0])) * _M_PER_DEG_LAT  # metres north
    travel_deg = (float(direction_deg) + 180.0) % 360.0 if direction_deg is not None else 270.0
    b = math.radians(travel_deg)
    dist = math.sin(b) * Xm + math.cos(b) * Ym  # metres along the travel bearing

    h_deep = float(np.nanmax(depth)) or 1.0
    # Green's-law shoaling, saturated in the surf zone so crests cap not explode.
    shoal = np.sqrt(h_deep / np.maximum(depth, h_deep * 0.06))
    shoal = np.clip(shoal, 1.0, 2.6)
    amp = base_amp * shoal
    # Break: no carry where the crest no longer fits under itself.
    broken = sea & (depth < 1.5 * amp)
    carry = sea & ~broken

    cmax = float(np.nanmax(amp)) * 1.05 or 1.0
    frames: list[dict] = []
    for f in range(_FRAMES):
        phase = 2.0 * math.pi * f / _FRAMES
        s = np.sin(k * dist - phase)  # −phase: crests advance along the travel bearing
        # Sharpen crests, flatten troughs — a pitching, spilling profile.
        profile = np.where(s > 0, np.abs(s) ** 0.55, 0.6 * s)
        wave = amp * profile
        masked = np.where(carry, wave, np.nan)
        z = [[round(float(v), 2) for v in row] for row in masked]
        frames.append({"data": [{"z": z}], "traces": [1]})
    initial = go.Surface(
        x=x, y=y, z=frames[0]["data"][0]["z"],
        colorscale=_WATER_COLORSCALE, opacity=0.65,
        showscale=False, hoverinfo="skip", name="swell",
        lighting={"ambient": 0.9}, cmin=-0.4 * cmax, cmax=cmax,
    )
    return initial, frames, duration_ms


def build_surface_fig(grid: dict, name: str = "", wave: dict | None = None):
    """3D seafloor surface (smoothed) + optional animated swell layer.

    ``wave`` is ``{"height_m": float, "period_s": float,
    "direction_deg": float | None}`` from the scored payload — renders a
    translucent water surface with a ▶ swell play button animating it at
    the forecast's dominant height/period, travelling the bearing opposite
    ``direction_deg`` (the swell's FROM bearing).
    """
    import numpy as np
    import plotly.graph_objects as go

    if not grid.get("elev"):
        return _empty_fig()
    disp, raw = _display(grid)
    use = disp or raw
    x, y = use["x"], use["y"]
    z = np.array(use["z"], dtype=float)
    colorscale, cmin, cmax = _earth_scale(z)
    fig = go.Figure()
    fig.add_trace(
        go.Surface(
            x=x, y=y, z=z,
            colorscale=colorscale,
            cmin=cmin,
            cmax=cmax,
            colorbar={"title": "m"},
            hovertemplate="elev %{z:.0f} m<extra></extra>",
            lighting={"ambient": 0.75, "diffuse": 0.6},
            name="seafloor",
        )
    )
    have_wave = False
    if wave and (wave.get("height_m") or wave.get("period_s")):
        try:
            direction_deg = float(wave["direction_deg"])
        except (KeyError, TypeError, ValueError):
            direction_deg = None
        try:
            initial_wave, frame_args, duration_ms = _wave_frames(
                x, y, use["z"], use.get("mask_sea"),
                float(wave.get("height_m") or 1.0),
                float(wave.get("period_s") or 10.0),
                direction_deg)
            fig.add_trace(initial_wave)
            period_label = (f"{float(wave['period_s']):.0f}s"
                            if wave.get("period_s") else "swell")
            if direction_deg is not None:
                period_label += f" @ {direction_deg:.0f}°"
            fig.update_layout(
                updatemenus=[{
                    "type": "buttons",
                    "direction": "left",
                    "x": 0.02, "y": 0.98, "xanchor": "left", "yanchor": "top",
                    "bgcolor": "#eef6fd", "bordercolor": "#0b2c5c",
                    "font": {"family": FONT, "color": "#0b2c5c", "size": 12},
                    "buttons": [{
                        "label": f"▶ swell {period_label}",
                        "method": "animate",
                        # Frame objects must ride in args[0]: gr.Plot drops
                        # fig.frames client-side (see _wave_frames docstring).
                        "args": [frame_args,
                                 {"frame": {"duration": duration_ms, "redraw": True},
                                  "mode": "immediate"}],
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
