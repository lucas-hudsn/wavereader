# Encyclopedia tab

The `encyclopedia` tab in `app/ui.py:build_demo()` is the break browser.
It reads the generated knowledge base, filters it, plots it, and feeds
the selected break to the `surf forecast` tab via shared `gr.State`.

## Data source

- `data/australia-surf-breaks-enriched.json` → `load_breaks()` (`app/breaks_data.py`)
  into `DF`. Legacy `{"name | state | region": {...}}` dict format is
  accepted; rows with an `error` column are dropped.
- Derived at import time: `STATES`, `REGIONS_BY_STATE`, `ALL_REGIONS`,
  `SKILLS` (filtered to `SKILL_ORDER`: beginner → intermediate →
  advanced → expert → pro-only).
- Enriched `id` is `"<name> | <state> | <region>"`. Canonical
  `state`/`region` come from the input list, never the model.

## Filtering

`filter_breaks(df, state, region, skill)` — `"All"` / `None` means no
filter, comparison is case-insensitive on `state` / `region` /
`skillLevel`.

- `state_dd.change` → `update_region_choices` (narrows region list) →
  `update_map` → `sync_custom_from_filters` (pushes map State/Region
  into the generation form; `All` leaves the field untouched via
  `gr.skip()`).
- `region_dd` / `skill_dd` → `update_map`.

`update_map` returns `(map fig, break choices, records, count, empty
details)`. Unfiltered view frames the whole of Australia
(`AUSTRALIA_CENTER`, zoom 3.5); otherwise the map auto-centers/zooms via
`_zoom_for_span()`.

## Map

- `build_map(records, default_view)` — Plotly `Scattermap`,
  `open-street-map` style, marker colour by `SKILL_COLORS`. Point order
  matches records order so the break list lines up.
- `build_map_with_custom(base_records, custom)` — adds the gold star
  (`#FFD700`) marker for the session break.
- `_lat()` / `_lng()` return `None` on missing coords; those points are
  skipped for centering.

## Details + selection

- `break_dd` (Radio, `.break-list`) → `on_break_pick` →
  `break_to_table(record)`, a 16-row Field/Value dataframe
  (name/state/region/description/skill/break+peak type/coords/ideal
  swell+wind+tide/season/hazards/crowd).
- `_resolve_pick(label, base_records, custom)` maps the label back to its
  record; the custom break carries a `⭐ (your break)` suffix and matches
  by suffix, base records match by `name`.
- `on_break_pick` also sets shared `selected_break` state and updates the
  forecast tab header + skill default (break's own `skillLevel`,
  validated against `SKILL_ORDER`, fallback `intermediate`).

## Session-only custom break

- `generate_custom_break()` (in `app/custom_break.py`) streams `(telemetry, details, map, dropdown,
  state)` tuples via `yield`. Lazy `from app import generate_surf_break`
  (direct package import, no `importlib` shims).
- Empty custom state/region fields fall back to the main map filters;
  explicit values win. Exactly one custom break per session (`gr.State`,
  never written to disk); regeneration replaces it.
- `clear_custom_break(base_records, selected)` deletes it; if the deleted
  break was the forecast selection, the forecast header/skill reset too.
- `clear` / `generate` do not auto-select the forecast state — pick the
  break in the list first, then fetch on tab 2.

## Theme

Lo-fi via `APP_CSS`: light blue bg `#d6e9f8`, dark blue `#0b2c5c`,
Courier. Don't restyle without asking. Callbacks stay wired in
`build_demo()`.
