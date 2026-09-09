"""Break-list loading, filtering + import-time index (DF/STATES/...)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from legacy.app.config import ALL, DATA_PATH, SKILL_ORDER

def load_breaks(path: Path = DATA_PATH) -> pd.DataFrame:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        # Legacy format: {"name | state | region": {...}} mapping.
        df = pd.read_json(path, orient="index")
    else:
        df = pd.DataFrame(data)
    if "error" in df.columns:
        df = df[df["error"].isna()].drop(columns=["error"])
    return df.reset_index(drop=True)


def filter_breaks(
    df: pd.DataFrame,
    state: str | None = None,
    region: str | None = None,
    skill: str | None = None,
) -> pd.DataFrame:
    """Filter breaks by state / region / skill level ("All"/None = no filter)."""
    out = df
    if state and state != ALL:
        out = out[out["state"].str.lower() == state.lower()]
    if region and region != ALL:
        out = out[out["region"].str.lower() == region.lower()]
    if skill and skill != ALL:
        out = out[out["skillLevel"].str.lower() == skill.lower()]
    return out.reset_index(drop=True)


DF = load_breaks()


STATES = sorted(DF["state"].dropna().unique().tolist())


REGIONS_BY_STATE = {
    state: sorted(DF[DF["state"] == state]["region"].dropna().unique().tolist())
    for state in STATES
}


ALL_REGIONS = sorted(DF["region"].dropna().unique().tolist())


SKILLS = [s for s in SKILL_ORDER if s in set(DF["skillLevel"].str.lower())] or sorted(
    DF["skillLevel"].dropna().unique().tolist()
)
