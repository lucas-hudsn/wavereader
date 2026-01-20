import os
from google import genai

GEMINI_CLIENT = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
REPORT_MODEL = "gemma-3-27b-it"


def generate_forecast(break_info: dict, weather_data: dict) -> str:
    hourly = weather_data.get("hourly", {})
    times = hourly.get("time", [])
    wave_heights = hourly.get("wave_height", [])
    wind_speeds = hourly.get("wind_speed", [])

    daily_summary = []
    for day in range(7):
        start_idx = day * 24
        end_idx = start_idx + 24
        if start_idx >= len(times):
            break
        day_waves = wave_heights[start_idx:end_idx]
        day_winds = wind_speeds[start_idx:end_idx]
        day_date = times[start_idx][:10] if start_idx < len(times) else f"Day {day + 1}"
        max_wave = max(day_waves) if day_waves else 0
        avg_wind = sum(day_winds) / len(day_winds) if day_winds else 0
        daily_summary.append(
            f"- {day_date}: Max wave {max_wave:.1f}m, Avg wind {avg_wind:.0f}km/h"
        )

    daily_conditions = (
        "\n".join(daily_summary) if daily_summary else "No daily data available"
    )

    prompt = f"""Generate a daily surf report for {break_info.get("name", "this break")}:

SURF BREAK INFORMATION:
- Name: {break_info.get("name", "Unknown")}
- Description: {break_info.get("description", "No description")}
- Break Type: {break_info.get("break_type", "Unknown")}
- Bottom Type: {break_info.get("bottom_type", "Unknown")}
- Wave Direction: {break_info.get("wave_direction", "Unknown")}
- Skill Level: {break_info.get("skill_level", "Unknown")}
- Ideal Wind: {break_info.get("ideal_wind", "Unknown")}
- Ideal Tide: {break_info.get("ideal_tide", "Unknown")}
- Ideal Swell Size: {break_info.get("ideal_swell_size", "Unknown")}

7-DAY FORECAST SUMMARY:
{daily_conditions}

Create a daily surf report with:
1. Week Overview (2-3 sentences)
2. Best Days (specific days and why)
3. Swell Trend
4. Wind Pattern
5. Recommended Sessions
6. Who Should Surf

Be specific and practical."""

    response = GEMINI_CLIENT.models.generate_content(
        model=REPORT_MODEL,
        contents=prompt,
    )
    return response.text if response.text else ""
