"""Gradio map front end for Australian surf breaks (thin entrypoint)."""

from __future__ import annotations

from app.break_details import break_to_table
from app.breaks_data import (
    ALL_REGIONS,
    DF,
    REGIONS_BY_STATE,
    SKILLS,
    STATES,
    filter_breaks,
    load_breaks,
)
from app.browse_sync import on_break_pick, update_map
from app.config import ALL
from app.custom_break import clear_custom_break, generate_custom_break
from app.forecast_handlers import fetch_forecast, generate_reports
from app.maps import build_map, build_map_with_custom
from app.seafloor_handlers import fetch_seafloor, generate_seafloor_explanation
from app.theme import APP_CSS
from app.ui import build_demo

__all__ = [
    "ALL",
    "ALL_REGIONS",
    "DF",
    "REGIONS_BY_STATE",
    "SKILLS",
    "STATES",
    "APP_CSS",
    "break_to_table",
    "build_demo",
    "build_map",
    "build_map_with_custom",
    "clear_custom_break",
    "fetch_forecast",
    "fetch_seafloor",
    "generate_seafloor_explanation",
    "filter_breaks",
    "generate_custom_break",
    "generate_reports",
    "load_breaks",
    "on_break_pick",
    "update_map",
]

def main():
    import argparse

    parser = argparse.ArgumentParser(description="wave~reader — break book + swell check")
    parser.add_argument(
        "--share",
        action="store_true",
        help="launch a public gradio.live link (great for sharing demos)",
    )
    args = parser.parse_args()
    build_demo().launch(css=APP_CSS, share=args.share)


if __name__ == "__main__":
    main()
