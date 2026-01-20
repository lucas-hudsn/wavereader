"""
Script to generate surf break data using Google Gemini API
"""

import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def get_beach_details(beach_name: str) -> dict:
    """
    Call Gemini to get detailed information about a surf break
    """
    prompt = f"""Provide detailed information about {beach_name} as a surf break.

Return a JSON object with the following fields:
- "description": A quick 2-3 sentence description of the break
- "state": The state/region where it's located
- "coordinates": An object with "latitude" and "longitude" as numbers
- "wave_direction": Either "left" or "right" (the direction the wave breaks)
- "bottom_type": Either "reef" or "sand"
- "break_type": Either "point" or "beach"
- "skill_level": Either "beginner", "intermediate", or "advanced"
- "ideal_wind": Description of ideal wind conditions (direction and strength)
- "ideal_tide": Description of ideal tide conditions (low, mid, high, or combination)
- "ideal_swell_size": Ideal swell size range in feet (e.g., "3-6 ft")

Return ONLY valid JSON, no markdown or additional text."""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
    )
    response_text = response.text.strip()

    if "```" in response_text:
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    return json.loads(response_text)


if __name__ == "__main__":
    beach = "Bells Beach"
    print(f"Fetching details for {beach}...")

    details = get_beach_details(beach)
    print(json.dumps(details, indent=2))
