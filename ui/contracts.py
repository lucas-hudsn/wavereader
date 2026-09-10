"""Canonical output contracts shared by panels + wiring.

Every handler that fills several components returns a tuple ordered by
its contract's key tuple; missing entries become ``gr.skip()`` (component
untouched). One module owns the order, so handlers, panel dicts and the
wiring in ``ui/app.py`` can't drift apart the way the old hand-maintained
11-tuples did.
"""

from __future__ import annotations

# Picking a spot (search box / default on load): static story + intel.
SELECT_KEYS = (
    "search_dd", "map_plot", "spot_header", "badges_md", "description_md",
    "rose_plot", "year_plot", "months_md", "selected",
)

# The staged forecast fetch: status, hero, strip, world model, state.
FETCH_KEYS = (
    "status_box", "hero_md", "score_plot", "swell_plot", "wind_plot",
    "surface_plot", "depth_plot", "transect_plot", "seafloor_md", "scored",
)

# An agent turn: chat + live trace + meter + verdict + status + chart + ranks.
AGENT_KEYS = (
    "chatbot", "msg", "trace_html", "token_md", "agent_status",
    "verdict_html", "agent_strip", "spot_dd", "rank_html", "agent_store",
)


def fill(keys: tuple[str, ...], **values):
    """Build an output tuple for ``keys``, skipping what wasn't passed."""
    import gradio as gr

    return tuple(values.get(k, gr.skip()) for k in keys)
