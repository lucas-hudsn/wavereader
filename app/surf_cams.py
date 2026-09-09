"""Curated surf-cam link overlay (link-out only, no scraping).

Data lives in ``data/surf-cams.json`` keyed by canonical enriched break id
(``"<name> | <state> | <region>"``). This module is deliberately dependency-free
so ``main.py`` can load it the same lazy way as the other ``app/`` helpers.

Rules (MVP):
- Link to cam *pages* only — never direct image/stream URLs (hotlinking + ToS).
- Missing key = no cam linked yet (sparse coverage is expected).
- Session-only custom breaks resolve via the name fallback like anything else.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CAMS_PATH = DATA_DIR / "surf-cams.json"

NO_CAM_MD = "_No public cam linked yet for this break._"


def load_cams(path: Path = CAMS_PATH) -> dict:
    """Load the cam overlay; missing/unreadable file means no cams ({})."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    data.pop("_notes", None)
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def get_cam(break_: dict | None, cams: dict) -> dict | None:
    """Return the overlay entry for a break record, or None.

    Exact ``id`` match first (``"<name> | <state> | <region>"``); falls back
    to a case-insensitive match on the name part of overlay keys so renames
    and session-only breaks still resolve when the name matches.
    """
    if not break_ or not cams:
        return None
    break_id = break_.get("id")
    if break_id and break_id in cams:
        return cams[break_id]
    name = str(break_.get("name", "")).strip().lower()
    if not name:
        return None
    for key, entry in cams.items():
        key_name = str(key).split("|")[0].strip().lower()
        if key_name == name:
            return entry
    return None


def cam_markdown(break_: dict | None, cams: dict) -> str:
    """Clickable cam link line for a Gradio Markdown box."""
    entry = get_cam(break_, cams)
    if not entry or not entry.get("url"):
        return NO_CAM_MD
    label = entry.get("label", "Live cam")
    bits = [f"🎥 Live cam: [{label}]({entry['url']})"]
    for alt in entry.get("alternates") or []:
        if isinstance(alt, dict) and alt.get("url"):
            bits.append(f"[{alt.get('label', 'alt')}]({alt['url']})")
    return " · ".join(bits)


def cam_table_value(break_: dict | None, cams: dict) -> str:
    """Plain-text cam value for the details Dataframe (not clickable there)."""
    entry = get_cam(break_, cams)
    if not entry or not entry.get("url"):
        return "—"
    return f"{entry.get('label', 'Live cam')} — {entry['url']}"
