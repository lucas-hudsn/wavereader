"""Seafloor world-model: bathymetry grid + deterministic shape analysis.

Data source: OpenTopoData ``gebco2020`` (GEBCO 2020 grid, ~450 m cells,
negative = below sea level), with ``etopo1`` as fallback. Free, no key,
100 locations per call — so a 9x9 grid (81 pts) fits in ONE request.

Pattern mirrors ``app/forecasts.py``: disk cache under ``.cache/seafloor``,
stale-fallback on network failure. Static data → long TTL (30 days).

The LLM never owns numbers: this module computes every stat + Plotly fig
deterministically; callers (UI tab, agent tool) only narrate the results.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import httpx

OPENTOPO_URL = "https://api.opentopodata.org/v1/{dataset}"
PRIMARY_DATASET = "gebco2020"
FALLBACK_DATASET = "etopo1"

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "seafloor"
CACHE_TTL_SECONDS = 30 * 24 * 3600
CACHE_VERSION = 1

GRID_N_DEFAULT = 9  # 9x9 = 81 pts, one API call
RADIUS_KM_DEFAULT = 1.2  # ~300 m spacing at 9x9
MAX_LOCATIONS_PER_CALL = 100


def _deg_offsets(lat: float, radius_km: float, n: int) -> tuple[list[float], list[float]]:
    """Lat/lng offsets for an n x n grid spanning ±radius_km."""
    half = radius_km
    dlat = half / 111.0
    # Guard cos() near poles; breaks are all Australian latitudes anyway.
    dlon = half / max(20.0, 111.0 * math.cos(math.radians(lat)))
    if n <= 1:
        return [0.0], [0.0]
    lats = [((i / (n - 1)) * 2 - 1) * dlat for i in range(n)]
    lngs = [((j / (n - 1)) * 2 - 1) * dlon for j in range(n)]
    return lats, lngs


def _cache_key(lat: float, lng: float, radius_km: float, n: int, dataset: str) -> str:
    return f"v{CACHE_VERSION}_{dataset}_{round(lat, 4):.4f}_{round(lng, 4):.4f}_{radius_km:.2f}km_{n}x{n}"


def _cache_path(lat: float, lng: float, radius_km: float, n: int, dataset: str) -> Path:
    safe = _cache_key(lat, lng, radius_km, n, dataset).replace("/", "_")
    return CACHE_DIR / f"{safe}.json"


def _load_cache(lat, lng, radius_km, n, dataset) -> tuple[dict, float] | None:
    p = _cache_path(lat, lng, radius_km, n, dataset)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict) and "fetched_at" in raw and "data" in raw:
        return raw["data"], float(raw["fetched_at"])
    return raw, 0.0


def _save_cache(lat, lng, radius_km, n, dataset, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {"fetched_at": time.time(), "data": data}
    tmp = _cache_path(lat, lng, radius_km, n, dataset).with_suffix(".tmp")
    tmp.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _cache_path(lat, lng, radius_km, n, dataset))


def _fetch_dataset(lats: list[float], lngs: list[float], dataset: str) -> list[float | None]:
    """Fetch one n x n grid; returns row-major elevations (m, None on miss)."""
    locs = [f"{la:.5f},{lo:.5f}" for la in lats for lo in lngs]
    out: list[float | None] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for i in range(0, len(locs), MAX_LOCATIONS_PER_CALL):
            chunk = locs[i : i + MAX_LOCATIONS_PER_CALL]
            resp = client.get(
                OPENTOPO_URL.format(dataset=dataset),
                params={"locations": "|".join(chunk)},
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") != "OK":
                raise ValueError(f"OpenTopoData {dataset}: {body.get('status')}")
            for r in body.get("results", []):
                out.append(r.get("elevation"))
            time.sleep(1.05)  # OpenTopoData free tier: 1 call/sec
    return out


def get_grid(
    lat: float, lng: float, radius_km: float = RADIUS_KM_DEFAULT, n: int = GRID_N_DEFAULT
) -> dict:
    """Fetch + cache the bathymetry grid around a point.

    Returns ``{"lats", "lngs", "elev", "n", "radius_km", "dataset",
    "center"}`` with ``elev`` row-major (lat-major) in metres.
    Serves fresh cache without network; stale cache on API failure.
    """
    n = max(3, min(10, int(n)))  # 10x10=100 fits one call; 11x11 would split
    radius_km = max(0.3, min(5.0, float(radius_km)))
    dlat, dlon = _deg_offsets(lat, radius_km, n)
    grid_lats = [round(lat + d, 5) for d in dlat]
    grid_lngs = [round(lng + d, 5) for d in dlon]

    for dataset in (PRIMARY_DATASET, FALLBACK_DATASET):
        cached = _load_cache(lat, lng, radius_km, n, dataset)
        if cached is not None and time.time() - cached[1] < CACHE_TTL_SECONDS:
            return cached[0]
        try:
            elev = _fetch_dataset(grid_lats, grid_lngs, dataset)
            data = {
                "lats": grid_lats,
                "lngs": grid_lngs,
                "elev": elev,
                "n": n,
                "radius_km": radius_km,
                "dataset": dataset,
                "center": {"lat": lat, "lng": lng},
            }
            _save_cache(lat, lng, radius_km, n, dataset, data)
            return data
        except (httpx.HTTPError, ValueError, KeyError):
            if cached is not None:
                return cached[0]
            continue  # try fallback dataset
    raise RuntimeError("Seafloor fetch failed (GEBCO + ETOPO1 unreachable, no cache)")


def _finite(vals: list) -> list[float]:
    return [float(v) for v in vals if v is not None]


def analyze_grid(grid: dict) -> dict:
    """Deterministic shape stats + markdown over a fetched grid."""
    elev = grid.get("elev") or []
    vals = _finite(elev)
    if not vals:
        return {"error": "Empty seafloor grid"}
    n = int(grid.get("n", GRID_N_DEFAULT))
    depths = [-v for v in vals if v < 0]  # positive-down metres
    land = [v for v in vals if v >= 0]

    def _pct(xs: list[float], q: float) -> float:
        s = sorted(xs)
        return s[max(0, min(len(s) - 1, int(q * len(s))))]

    # Center cell depth
    ci = (n // 2) * n + (n // 2)
    center_elev = elev[ci] if 0 <= ci < len(elev) else None

    # Slope: max neighbour gradient across the grid (m per km)
    lat_step_km = (2 * float(grid.get("radius_km", 1.2))) / max(1, n - 1)
    max_slope = 0.0
    slopes: list[float] = []
    for i in range(n):
        for j in range(n):
            v = elev[i * n + j] if i * n + j < len(elev) else None
            if v is None:
                continue
            for di, dj in ((1, 0), (0, 1)):
                ni, nj = i + di, j + dj
                if ni >= n or nj >= n:
                    continue
                w = elev[ni * n + nj] if ni * n + nj < len(elev) else None
                if w is None:
                    continue
                step_km = lat_step_km  # approx square grid at this scale
                s = abs(float(w) - float(v)) / max(1e-6, step_km)
                slopes.append(s)
                max_slope = max(max_slope, s)
    med_slope = _pct(slopes, 0.5) if slopes else 0.0

    # Shelf vs steep classification on median + max slope
    if med_slope >= 40:
        shelf = "steep reef edge / drop-off"
    elif med_slope >= 15:
        shelf = "moderately sloping reef/shelf"
    elif depths and _pct(depths, 0.5) <= 5:
        shelf = "shallow, gently shelving platform"
    else:
        shelf = "gradual sandy shelf"

    # Offshore range = relief across the box
    relief = max(vals) - min(vals)

    # Channel hint: deep outlier cells (>2x median depth) clustered off-center
    channel_hint = False
    if depths:
        med_d = _pct(depths, 0.5)
        deep_cells = sum(1 for d in depths if d > max(8.0, 2.0 * med_d))
        channel_hint = deep_cells >= max(3, len(depths) // 8)

    stats = {
        "dataset": grid.get("dataset"),
        "box_km": round(2 * float(grid.get("radius_km", 1.2)), 2),
        "points": len(vals),
        "center_elev_m": round(float(center_elev), 1) if center_elev is not None else None,
        "min_elev_m": round(min(vals), 1),
        "max_elev_m": round(max(vals), 1),
        "mean_elev_m": round(sum(vals) / len(vals), 1),
        "max_depth_m": round(max(depths), 1) if depths else 0.0,
        "median_depth_m": round(_pct(depths, 0.5), 1) if depths else 0.0,
        "land_fraction": round(len(land) / len(vals), 2),
        "relief_m": round(relief, 1),
        "median_slope_m_per_km": round(med_slope, 1),
        "max_slope_m_per_km": round(max_slope, 1),
        "shelf_class": shelf,
        "channel_hint": channel_hint,
    }

    md = (
        f"**Seafloor ({stats['dataset']}, {stats['box_km']} km box, {stats['points']} pts)** — "
        f"centre {stats['center_elev_m']} m · "
        f"deepest {stats['max_depth_m']} m · median depth {stats['median_depth_m']} m · "
        f"relief {stats['relief_m']} m · land {stats['land_fraction'] * 100:.0f}%.\n\n"
        f"- **Shape:** {shelf} (median slope {stats['median_slope_m_per_km']} m/km, "
        f"max {stats['max_slope_m_per_km']} m/km).\n"
        f"- **Channels:** {'possible deeper gutter(s) — compare the blue pockets on the map' if channel_hint else 'no strong channel signal at this resolution'}.\n"
        f"- **Surf read:** {('steep drops focus swell fast — expect punchier, more tide-sensitive peaks' if 'steep' in shelf else ('mid-slope reef — swell jacks up over the edge, check the transect' if 'moderately' in shelf else 'gentle shelf spreads energy — softer, more forgiving, needs more swell'))}."
    )
    return {"stats": stats, "markdown": md}


# ---- Plotly builders ----

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


def _grid_z(grid: dict) -> list[list[float | None]]:
    n = int(grid.get("n", GRID_N_DEFAULT))
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
    n = int(grid.get("n", GRID_N_DEFAULT))
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


def get_seafloor(
    lat: float, lng: float, radius_km: float = RADIUS_KM_DEFAULT, n: int = GRID_N_DEFAULT
) -> dict:
    """One-call fetch + analysis: ``{"grid", "analysis", "stats"}``."""
    grid = get_grid(lat, lng, radius_km=radius_km, n=n)
    analysis = analyze_grid(grid)
    return {"grid": grid, "analysis": analysis.get("markdown", ""),
            "stats": analysis.get("stats", {})}
