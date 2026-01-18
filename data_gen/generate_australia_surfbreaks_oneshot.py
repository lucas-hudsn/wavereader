"""
Script to generate surf break data using Google Gemini API with one-shot prompting.
Uses Bells Beach as the example, then iterates through 50 popular Australian surf breaks.
"""
import os
import json
import psycopg2
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 50 most popular surf breaks in Australia
AUSTRALIAN_SURF_BREAKS = [
    "Snapper Rocks",
    "Kirra",
    "Burleigh Heads",
    "Duranbah",
    "Greenmount",
    "The Superbank",
    "Noosa",
    "North Narrabeen",
    "Manly Beach",
    "Bondi Beach",
    "Maroubra",
    "Cronulla",
    "Angourie",
    "Lennox Head",
    "Byron Bay - The Pass",
    "Crescent Head",
    "Margaret River",
    "The Box (Margaret River)",
    "Yallingup",
    "Trigg Beach",
    "Scarborough Beach",
    "Rottnest Island",
    "Torquay",
    "Jan Juc",
    "Winkipop",
    "Johanna Beach",
    "Portsea",
    "Gunnamatta",
    "Phillip Island",
    "Woolamai",
    "Cactus Beach",
    "Pennington Bay",
    "Vivonne Bay",
    "Parsons Beach",
    "Waitpinga Beach",
    "Middleton",
    "Goolwa Beach",
    "Southport",
    "Straddie (North Stradbroke Island)",
    "Coolangatta",
    "Currumbin",
    "Palm Beach (QLD)",
    "Moffat Beach",
    "Alexandra Headland",
    "Coolum Beach",
    "Sunshine Beach",
    "Rainbow Bay",
    "Fingal Head",
    "Cabarita Beach",
    "Kingscliff",
]

# Bells Beach example for one-shot prompting
BELLS_BEACH_EXAMPLE = {
    "name": "Bells Beach",
    "description": "Bells Beach is a world-renowned right-hand point break in Victoria, Australia, famous for its long, powerful walls and natural amphitheater setting. It is home to the Rip Curl Pro, the world's longest-running professional surfing competition.",
    "state": "Victoria",
    "coordinates": {"latitude": -38.366, "longitude": 144.279},
    "wave_direction": "right",
    "bottom_type": "reef",
    "break_type": "point",
    "skill_level": "advanced",
    "ideal_wind": "Light offshore (NW to N)",
    "ideal_tide": "Mid to high",
    "ideal_swell_size": "4-10 ft",
}


def get_beach_details(beach_name: str) -> dict:
    """
    Call Gemini to get detailed information about a surf break using one-shot prompting.
    """
    prompt = f"""Provide detailed information about a surf break.

Here is an example for Bells Beach:

Input: Bells Beach
Output:
{json.dumps(BELLS_BEACH_EXAMPLE, indent=2)}

Now provide the same information for the following surf break.

Input: {beach_name}
Output:
Return a JSON object with these fields:
- "name": The name of the surf break
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


def init_database():
    """
    Initialize PostgreSQL database and create surf_breaks table.
    """
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "wavereader"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS surf_breaks (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            description TEXT,
            state VARCHAR(100),
            latitude DECIMAL(10, 6),
            longitude DECIMAL(10, 6),
            wave_direction VARCHAR(20),
            bottom_type VARCHAR(20),
            break_type VARCHAR(20),
            skill_level VARCHAR(20),
            ideal_wind VARCHAR(255),
            ideal_tide VARCHAR(255),
            ideal_swell_size VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    return conn, cursor


def save_to_database(cursor, conn, data: dict):
    """
    Save surf break data to PostgreSQL database.
    """
    cursor.execute(
        """
        INSERT INTO surf_breaks (
            name, description, state, latitude, longitude,
            wave_direction, bottom_type, break_type, skill_level,
            ideal_wind, ideal_tide, ideal_swell_size
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            state = EXCLUDED.state,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            wave_direction = EXCLUDED.wave_direction,
            bottom_type = EXCLUDED.bottom_type,
            break_type = EXCLUDED.break_type,
            skill_level = EXCLUDED.skill_level,
            ideal_wind = EXCLUDED.ideal_wind,
            ideal_tide = EXCLUDED.ideal_tide,
            ideal_swell_size = EXCLUDED.ideal_swell_size
        """,
        (
            data.get("name"),
            data.get("description"),
            data.get("state"),
            data.get("coordinates", {}).get("latitude"),
            data.get("coordinates", {}).get("longitude"),
            data.get("wave_direction"),
            data.get("bottom_type"),
            data.get("break_type"),
            data.get("skill_level"),
            data.get("ideal_wind"),
            data.get("ideal_tide"),
            data.get("ideal_swell_size"),
        ),
    )
    conn.commit()


def main():
    print("Initializing database...")
    conn, cursor = init_database()

    # First, save the Bells Beach example
    print("Saving Bells Beach example...")
    save_to_database(cursor, conn, BELLS_BEACH_EXAMPLE)

    # Process all surf breaks
    total = len(AUSTRALIAN_SURF_BREAKS)
    for i, beach in enumerate(AUSTRALIAN_SURF_BREAKS, 1):
        print(f"[{i}/{total}] Fetching details for {beach}...")
        try:
            details = get_beach_details(beach)
            save_to_database(cursor, conn, details)
            print(f"  Saved: {details.get('name', beach)}")
        except Exception as e:
            print(f"  Error processing {beach}: {e}")

    cursor.close()
    conn.close()
    print("\nDone! All surf breaks saved to database.")


if __name__ == "__main__":
    main()
