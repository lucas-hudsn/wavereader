import requests
from typing import Any


def query_openmeteo(latitude: float, longitude: float) -> dict[str, Any]:
    marine_url = "https://marine-api.open-meteo.com/v1/marine"
    marine_params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ["wave_height", "wave_period", "wave_direction"],
        "daily": ["wave_height_max", "wave_period_max"],
        "timezone": "auto",
        "forecast_days": 7,
    }

    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ["wind_speed_10m", "wind_direction_10m"],
        "daily": ["wind_speed_10m_max", "wind_direction_10m_dominant"],
        "timezone": "auto",
        "forecast_days": 7,
    }

    marine_response = requests.get(marine_url, params=marine_params, timeout=10)
    marine_response.raise_for_status()
    marine_data = marine_response.json()

    weather_response = requests.get(weather_url, params=weather_params, timeout=10)
    weather_response.raise_for_status()
    weather_data = weather_response.json()

    marine_daily = marine_data.get("daily", {})
    weather_daily = weather_data.get("daily", {})

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "wave_height_max": marine_daily.get("wave_height_max", [None])[0],
        "wave_period_max": marine_daily.get("wave_period_max", [None])[0],
        "wind_speed_max": weather_daily.get("wind_speed_10m_max", [None])[0],
        "wind_direction": weather_daily.get("wind_direction_10m_dominant", [None])[0],
        "hourly": {
            "time": marine_data.get("hourly", {}).get("time", []),
            "wave_height": marine_data.get("hourly", {}).get("wave_height", []),
            "wave_period": marine_data.get("hourly", {}).get("wave_period", []),
            "wave_direction": marine_data.get("hourly", {}).get("wave_direction", []),
            "wind_speed": weather_data.get("hourly", {}).get("wind_speed_10m", []),
            "wind_direction": weather_data.get("hourly", {}).get(
                "wind_direction_10m", []
            ),
        },
        "timezone": marine_data.get("timezone", "UTC"),
    }
