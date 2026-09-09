"""Offline tests for ui.charts.seafloor (animated swell wiring).

Synthetic grids only — no network. The animation test guards the Gradio
integration: gr.Plot renders with ``Plotly.react(gd, data, layout,
config)`` and drops ``fig.frames``, so the swell frames must ride inside
the ▶ button's ``args[0]`` (raw frame-object list plotly.js animates).
"""

import json
import math

from ui.charts.seafloor import _FRAMES, build_surface_fig


def _reef_grid(n=10, center=(-38.37, 144.28)):
    """GEBCO-shaped grid: deep offshore, a reef peak breaching near (7, 3)."""
    lats = [round(center[0] + (i - n / 2) * 0.008, 5) for i in range(n)]
    lngs = [round(center[1] + (j - n / 2) * 0.008, 5) for j in range(n)]
    elev = [round(-25.0 + 4.0 * math.hypot(i - 7, j - 3), 1)
            for i in range(n) for j in range(n)]
    return {"lats": lats, "lngs": lngs, "elev": elev, "n": n,
            "center": {"lat": center[0], "lng": center[1]}}


def test_surface_animates_frames_via_button_args():
    """▶ frames ride in updatemenus args — never in (client-dropped) fig.frames."""
    doc = json.loads(build_surface_fig(
        _reef_grid(), "Bells Beach",
        wave={"height_m": 1.8, "period_s": 11.0}).to_json())

    assert "frames" not in doc  # dead payload — gr.Plot drops it client-side
    button = doc["layout"]["updatemenus"][0]["buttons"][0]
    assert button["method"] == "animate" and "swell" in button["label"]
    frames_arg, opts = button["args"]
    assert len(frames_arg) == _FRAMES
    assert opts["frame"]["redraw"] is True and opts["frame"]["duration"] > 0
    for frame in frames_arg:
        # z-only updates for trace 1 (the swell Surface); NaN ships as null
        assert frame["traces"] == [1]
        (z,) = frame["data"]
        assert set(z) == {"z"} and len(z["z"]) == 41
        assert any(v is None for row in z["z"] for v in row)  # broken-zone holes
    # the phases must actually differ or the "animation" would be a still
    z0 = frames_arg[0]["data"][0]["z"]
    z_mid = frames_arg[_FRAMES // 2]["data"][0]["z"]
    assert any(abs((a or 0) - (b or 0)) > 0.01
               for row_a, row_b in zip(z0, z_mid)
               for a, b in zip(row_a, row_b))
    # initial swell surface present as trace 1, matching frame 0
    assert doc["data"][1]["name"] == "swell"
    assert doc["data"][1]["z"] == z0


def test_surface_without_wave_has_no_button():
    doc = json.loads(build_surface_fig(_reef_grid(), "Bells").to_json())
    assert "updatemenus" not in doc["layout"]
    assert len(doc["data"]) == 1 and doc["data"][0]["name"] == "seafloor"


def _flat_grid(n=10, center=(-38.37, 144.28)):
    """Uniform deep water — no shoaling, no broken zone: z *is* the phase field."""
    lats = [round(center[0] + (i - n / 2) * 0.008, 5) for i in range(n)]
    lngs = [round(center[1] + (j - n / 2) * 0.008, 5) for j in range(n)]
    elev = [-25.0] * (n * n)
    return {"lats": lats, "lngs": lngs, "elev": elev, "n": n,
            "center": {"lat": center[0], "lng": center[1]}}


def _first_frame_z(direction_deg):
    doc = json.loads(build_surface_fig(
        _flat_grid(), "Bells",
        wave={"height_m": 1.8, "period_s": 11.0, "direction_deg": direction_deg}
    ).to_json())
    return doc["data"][1]["z"]


def test_surface_direction_rotates_the_swell():
    """direction_deg steers travel: from-E crests run N–S, from-N crests run E–W."""
    z_from_east = _first_frame_z(90.0)   # travels west → varies along lng only
    z_from_north = _first_frame_z(0.0)   # travels south → varies along lat only

    # from-east: rows are identical (field depends on lng only) but vary along the row
    assert all(a == b for row_a, row_b in zip(z_from_east, z_from_east[1:])
               for a, b in zip(row_a, row_b))
    assert any(a != b for a, b in zip(z_from_east[0], z_from_east[0][1:]))
    # from-north: every row is flat (constant along lng) and rows differ
    assert all(v == row[0] for row in z_from_north for v in row)
    assert any(row_a[0] != row_b[0]
               for row_a, row_b in zip(z_from_north, z_from_north[1:]))
    # no direction given: legacy default (travels west, varies along lng)
    z_default = _first_frame_z(None)
    assert all(a == b for row_a, row_b in zip(z_default, z_default[1:])
               for a, b in zip(row_a, row_b))
    # and the two steerings genuinely differ from each other
    assert any((a or 0) != (b or 0)
               for row_a, row_b in zip(z_from_east, z_from_north)
               for a, b in zip(row_a, row_b))


def test_surface_button_label_shows_swell_direction():
    doc = json.loads(build_surface_fig(
        _reef_grid(), "Bells Beach",
        wave={"height_m": 1.8, "period_s": 11.0, "direction_deg": 213}).to_json())
    label = doc["layout"]["updatemenus"][0]["buttons"][0]["label"]
    assert "swell" in label and "213°" in label
    # missing direction still animates, with no "@ …°" suffix
    doc = json.loads(build_surface_fig(
        _reef_grid(), "Bells Beach",
        wave={"height_m": 1.8, "period_s": 11.0, "direction_deg": None}).to_json())
    label = doc["layout"]["updatemenus"][0]["buttons"][0]["label"]
    assert "swell" in label and "°" not in label
