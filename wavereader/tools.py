"""Agent tools: forecast/score/knowledge lookups plus matplotlib plot builders.

Plain functions resolve a spot by ``(name, region)`` and delegate to
``forecasts``/``scoring``/``spots``; the smolagents ``Tool`` subclasses below
expose them to the CodeAgent. The LLM never computes numbers itself.
"""

import base64
import io
import matplotlib
matplotlib.use("Agg")  # Use non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from smolagents import Tool
from wavereader import forecasts, scoring, spots

# Configure Seaborn global styling
sns.set_theme(style="whitegrid", palette="muted")


def _encode_fig_to_base64(fig) -> str:
    """Helper to convert a matplotlib figure to base64 string."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=150)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    plt.close(fig)
    return encoded


def draw_directional_arrows(ax, x_coords, y_coords, degrees, color="black"):
    """Annotate plot points with direction arrows pointing towards the direction vector."""
    for x, y, deg in zip(x_coords, y_coords, degrees):
        if pd.isna(deg):
            continue
        # Convert degrees to radians (standard meteorology: 0° N, 90° E)
        rad = np.radians(90 - deg)
        dx = np.cos(rad) * 0.4
        dy = np.sin(rad) * 0.4
        ax.annotate(
            "",
            xy=(x + dx, y + dy),
            xytext=(x - dx, y - dy),
            arrowprops=dict(
                arrowstyle="->",
                color=color,
                lw=1.5,
                mutation_scale=12,
            ),
        )


def plot_daily_surf_overview(spot_name: str, region: str) -> dict:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}

    forecast = forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)
    scores = scoring.score_week(forecast, s.model_dump())

    df = pd.DataFrame(scores)

    # Dynamic date field resolution to prevent KeyError
    date_col = next((col for col in ["date", "day", "datetime", "timestamp"] if col in df.columns), None)
    if date_col:
        df["date_label"] = pd.to_datetime(df[date_col]).dt.strftime("%a %b %d")
    else:
        df["date_label"] = [f"Day {i+1}" for i in range(len(df))]

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(
        f"7-Day Surf Overview: {spot_name.title()} ({region.upper()})",
        fontsize=16,
        fontweight="bold",
    )

    # 1. Overall Daily Score
    sns.barplot(
        data=df,
        x="date_label",
        y="score",
        ax=axes[0],
        palette="Blues_d",
        hue="date_label",
        legend=False,
    )
    axes[0].set_ylabel("Overall Score (0-10)", fontweight="bold")
    axes[0].set_ylim(0, 10)
    for p in axes[0].patches:
        axes[0].annotate(
            f"{p.get_height():.1f}",
            (p.get_x() + p.get_width() / 2.0, p.get_height()),
            ha="center",
            va="center",
            xytext=(0, 5),
            textcoords="offset points",
            fontweight="bold",
        )

    # 2. Daily Swell Size & Direction
    sns.lineplot(
        data=df,
        x="date_label",
        y="swell_height",
        ax=axes[1],
        marker="o",
        color="teal",
        linewidth=2.5,
    )
    if "swell_direction" in df.columns:
        draw_directional_arrows(
            axes[1],
            range(len(df)),
            df["swell_height"],
            df["swell_direction"],
            color="darkslategrey",
        )
    axes[1].set_ylabel("Swell Height (m)", fontweight="bold")

    # 3. Daily Wind Speed & Direction
    sns.lineplot(
        data=df,
        x="date_label",
        y="wind_speed",
        ax=axes[2],
        marker="s",
        color="crimson",
        linewidth=2.5,
    )
    if "wind_direction" in df.columns:
        draw_directional_arrows(
            axes[2],
            range(len(df)),
            df["wind_speed"],
            df["wind_direction"],
            color="darkred",
        )
    axes[2].set_ylabel("Wind Speed (kts)", fontweight="bold")
    axes[2].set_xlabel("Date", fontweight="bold")

    plt.xticks(rotation=15)
    plt.tight_layout()
    return {"image_base64": _encode_fig_to_base64(fig), "format": "png"}


def plot_hourly_surf_drilldown(
    spot_name: str, region: str, date_str: str | None = None
) -> dict:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}

    forecast = forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)

    # Safely retrieve hourly data structure
    hourly_raw = forecast.get("hourly") or forecast.get("forecast", [])
    df = pd.DataFrame(hourly_raw)
    if df.empty:
        return {"error": "No hourly forecast data available"}

    # Dynamic timestamp field resolution to prevent KeyError
    ts_col = next((col for col in ["timestamp", "time", "date", "datetime"] if col in df.columns), None)
    if ts_col is None:
        return {"error": "No valid timestamp field found in hourly data"}

    df["parsed_timestamp"] = pd.to_datetime(df[ts_col])

    # Target specific date or default to the first available date
    if date_str:
        target_date = pd.to_datetime(date_str).date()
        df = df[df["parsed_timestamp"].dt.date == target_date]
    else:
        df = df[df["parsed_timestamp"].dt.date == df["parsed_timestamp"].dt.date.iloc[0]]

    if df.empty:
        return {"error": f"No data found for date {date_str}"}

    df["hour_str"] = df["parsed_timestamp"].dt.strftime("%H:%M")

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    display_date = df["parsed_timestamp"].dt.strftime("%Y-%m-%d").iloc[0]
    fig.suptitle(
        f"Hourly Drilldown for {spot_name.title()} ({display_date})",
        fontsize=16,
        fontweight="bold",
    )

    # 1. Hourly Scores
    sns.lineplot(
        data=df,
        x="hour_str",
        y="score",
        ax=axes[0],
        color="purple",
        marker="o",
        linewidth=2,
    )
    axes[0].fill_between(
        df["hour_str"], df["score"], color="purple", alpha=0.15
    )
    axes[0].set_ylabel("Score (0-10)", fontweight="bold")
    axes[0].set_ylim(0, 10)

    # 2. Hourly Swell Size & Direction
    sns.lineplot(
        data=df,
        x="hour_str",
        y="swell_height",
        ax=axes[1],
        color="dodgerblue",
        marker="o",
    )
    if "swell_direction" in df.columns:
        draw_directional_arrows(
            axes[1],
            range(len(df)),
            df["swell_height"],
            df["swell_direction"],
            color="navy",
        )
    axes[1].set_ylabel("Swell (m)", fontweight="bold")

    # 3. Hourly Wind Speed & Direction
    sns.lineplot(
        data=df,
        x="hour_str",
        y="wind_speed",
        ax=axes[2],
        color="orangered",
        marker="o",
    )
    if "wind_direction" in df.columns:
        draw_directional_arrows(
            axes[2],
            range(len(df)),
            df["wind_speed"],
            df["wind_direction"],
            color="darkred",
        )
    axes[2].set_ylabel("Wind (kts)", fontweight="bold")
    axes[2].set_xlabel("Time", fontweight="bold")

    plt.xticks(rotation=45)
    plt.tight_layout()
    return {"image_base64": _encode_fig_to_base64(fig), "format": "png"}


def get_forecast(spot_name: str, region: str) -> dict:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)


def score_week(spot_name: str, region: str) -> dict | list[dict]:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    forecast = forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)
    return scoring.score_week(forecast, s.model_dump())


def find_spots(query: str = "", skill: str | None = None, limit: int = 10) -> list[dict]:
    results = spots.find_spots(query=query, skill=skill, limit=limit)
    return [b.model_dump() for b in results]


def get_spot_knowledge(spot_name: str, region: str) -> dict:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return s.model_dump()


def rank_spots_this_week(region: str, skill: str | None = None) -> list[dict]:
    spots_list = spots.find_spots(region=region, skill=skill)
    if not spots_list:
        return []
    forecasts_map = {}
    for b in spots_list:
        d = forecasts.get_forecast(b.coordinates.lat, b.coordinates.lng)
        forecasts_map[(b.name, b.region)] = d
    return scoring.rank_spots_this_week(
        forecasts_map,
        [b.model_dump() for b in spots_list],
    )


class GetForecastTool(Tool):
    name = "get_forecast"
    description = "Retrieve the wave forecast for a specific surf spot."
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code where the spot is located (e.g., 'QLD').",
        },
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_forecast(spot_name=spot_name, region=region)


class ScoreWeekTool(Tool):
    name = "score_week"
    description = "Score the conditions of a surf spot for the upcoming week based on its forecast."
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code where the spot is located.",
        },
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict | list[dict]:
        return score_week(spot_name=spot_name, region=region)


class FindSpotsTool(Tool):
    name = "find_spots"
    description = "Search for surf spots based on query, skill level, and limit."
    inputs = {
        "query": {
            "type": "string",
            "description": "Search query or region for surf spots. Use State code (e.g., 'QLD') or specific spot names.",
            "nullable": True,
        },
        "skill": {
            "type": "string",
            "description": "Skill level (e.g., beginner, intermediate, advanced).",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of spots to return.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(
        self, query: str = "", skill: str | None = None, limit: int = 10
    ) -> list[dict]:
        return find_spots(query=query, skill=skill, limit=limit)


class GetSpotKnowledgeTool(Tool):
    name = "get_spot_knowledge"
    description = "Retrieve metadata and detailed knowledge for a specific surf spot."
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code where the spot is located.",
        },
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_spot_knowledge(spot_name=spot_name, region=region)


class RankSpotsThisWeekTool(Tool):
    name = "rank_spots_this_week"
    description = "Rank spots in a region for the upcoming week based on scored surf conditions."
    inputs = {
        "region": {
            "type": "string",
            "description": "Region or state code to rank spots in (e.g., 'QLD').",
        },
        "skill": {
            "type": "string",
            "description": "Skill level filter (e.g., beginner, intermediate, advanced).",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(
        self, region: str, skill: str | None = None
    ) -> list[dict]:
        return rank_spots_this_week(region=region, skill=skill)


class PlotDailySurfOverviewTool(Tool):
    name = "plot_daily_surf_overview"
    description = (
        "Generates a 7-day daily overview graph for a surf spot showing score, "
        "swell height/direction, and wind speed/direction. Returns a base64 encoded PNG."
    )
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code (e.g., 'QLD').",
        },
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return plot_daily_surf_overview(spot_name=spot_name, region=region)


class PlotHourlySurfDrilldownTool(Tool):
    name = "plot_hourly_surf_drilldown"
    description = (
        "Generates an hourly drilldown plot for a specific day at a surf spot showing "
        "hourly score, swell height/direction, and wind speed/direction. Returns a base64 encoded PNG."
    )
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code (e.g., 'QLD').",
        },
        "date_str": {
            "type": "string",
            "description": "Date to drill down into (YYYY-MM-DD). If omitted, defaults to the first available date.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(
        self, spot_name: str, region: str, date_str: str | None = None
    ) -> dict:
        return plot_hourly_surf_drilldown(
            spot_name=spot_name, region=region, date_str=date_str
        )