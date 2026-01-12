"""
Tools for surf forecasting agents
"""
import requests
import os
from typing import Any
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from the .env file
load_dotenv()

# Initialize LLM
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
)

def get_beach_description(beach_name: str) -> str:
    """
    Use LLM to get a description of a surf break
    """
    prompt = f"""Provide a concise 2-3 sentence description of the {beach_name} surf break. 
Include information about the break type (reef, beach, point), wave characteristics, 
and what conditions it's best for. Be specific and knowledgeable."""
    
    try:
        message = llm.invoke(prompt)
        return message.content
    except Exception as e:
        return f"Failed to get description: {str(e)}"

def get_beach_coordinates(beach_name: str, context: str = "") -> dict[str, float]:
    """
    Use LLM to get coordinates for a beach
    """
    prompt = f"""Get the latitude and longitude coordinates for the {beach_name} surf break.
    
    Context: {context}
    
    Return ONLY a JSON object with "latitude" and "longitude" keys and numeric values.
    Example: {{"latitude": -33.8688, "longitude": 151.2093}}
    
    Do not include any other text."""
    
    try:
        message = llm.invoke(prompt)
        response_text = message.content.strip()
        
        # Extract JSON if wrapped in markdown code blocks
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()
        
        import json
        coords = json.loads(response_text)
        return {
            "latitude": float(coords["latitude"]),
            "longitude": float(coords["longitude"])
        }
    except Exception as e:
        return {"latitude": 0.0, "longitude": 0.0}

def get_weather_forecast(latitude: float, longitude: float) -> dict[str, Any]:
    """
    Fetch swell and wind data from Open-Meteo API
    """
    try:
        # Open-Meteo API endpoint for marine and weather data
        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": [
                "wave_height",
                "wave_period",
                "wave_direction",
                "wind_speed",
                "wind_direction"
            ],
            "daily": [
                "wave_height_max",
                "wave_period_max",
                "wind_speed_10m_max",
                "wind_direction_10m_dominant"
            ],
            "timezone": "auto",
            "forecast_days": 1,
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract today's daily data
        daily_data = data.get("daily", {})
        
        return {
            "latitude": latitude,
            "longitude": longitude,
            "wave_height_max": daily_data.get("wave_height_max", [None])[0],
            "wave_period_max": daily_data.get("wave_period_max", [None])[0],
            "wind_speed_max": daily_data.get("wind_speed_10m_max", [None])[0],
            "wind_direction": daily_data.get("wind_direction_10m_dominant", [None])[0],
            "hourly": data.get("hourly", {}),
            "timezone": data.get("timezone", "UTC"),
        }
    except Exception as e:
        return {
            "error": f"Failed to fetch weather data: {str(e)}",
            "latitude": latitude,
            "longitude": longitude,
        }

def generate_forecast_summary(
    beach_name: str,
    description: str,
    weather_data: dict[str, Any]
) -> str:
    """
    Use LLM to generate a daily forecast summary based on conditions
    """
    if "error" in weather_data:
        return f"Unable to generate forecast: {weather_data['error']}"
    
    wave_height = weather_data.get("wave_height_max", 0)
    wave_period = weather_data.get("wave_period_max", 0)
    wind_speed = weather_data.get("wind_speed_max", 0)
    wind_direction = weather_data.get("wind_direction", 0)
    
    prompt = f"""Based on the following conditions for {beach_name}, provide a daily forecast summary 
for surfers. Be specific and actionable.

Beach Description: {description}

Today's Conditions:
- Wave Height: {wave_height} m
- Wave Period: {wave_period} s
- Wind Speed: {wind_speed} km/h
- Wind Direction: {wind_direction}°

Provide:
1. Overall forecast (1-2 sentences)
2. Best time to surf (with specific time windows if possible)
3. Suitability for different skill levels
4. What to watch for (hazards, changing conditions)
5. Equipment recommendation (shortboard, fish, etc.)

Be concise and practical."""
    
    try:
        message = llm.invoke(prompt)
        return message.content
    except Exception as e:
        return f"Failed to generate forecast: {str(e)}"
