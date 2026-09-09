# legacy/ — wave~reader v1 (archived)

The original Gradio front end (`main.py` + `app/`), frozen after the v2
rebuild. **Superseded by** the root `app.py` + `ui/` + `wavereader/` — that
is the live app (break book / swell check / surf agent on the Gradio 6
three-panel layout, deterministic core in `wavereader/`, MCP server on).

Kept for history and as the fallback adapter layer: `ui/_compat.py` still
falls back to `legacy.app.*` modules when the v2 core is unavailable, and
`ui/charts/` inherit v1 chart conventions.

- Run it (only if you really want the old UI): `uv run python legacy/main.py`
- The v1 dataset pipeline (`legacy/app/generate_base_data.py`,
  `legacy/app/generate_surf_break.py`) produced
  `data/australia-surf-breaks-enriched.json`, still the live dataset.
