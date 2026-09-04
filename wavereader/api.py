"""FastAPI backend: data endpoints owned by the core modules.

Gradio (app.py) is the demo UI; this API exposes the same core for tests
and any non-Gradio consumer. Endpoints: /spots, /forecast, /score, /ask.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from wavereader import forecasts, scoring, spots, tools
from wavereader.agent import run_agent, SurfAgent

app = FastAPI(title="wavereader", version="0.1.0")


class AskRequest(BaseModel):
    question: str
    provider: str | None = None
    model: str | None = None


class AskResponse(BaseModel):
    answer: str
    trace: str | None = None


@app.get("/")
async def read_root():
    """Health check."""
    return {"name": "wavereader", "version": "0.1.0", "status": "ok"}


@app.get("/spots")
async def list_spots(query: str = "", region: str | None = None, skill: str | None = None, limit: int = 10):
    """Search/validate breaks via spots.py."""
    results = spots.find_spots(query=query, region=region, skill=skill, limit=limit)
    return [b.model_dump() for b in results]


@app.get("/spots/{spot_name}")
async def get_spot(spot_name: str, region: str):
    """Get full knowledge-base record for a spot keyed by (name, region).

    ``region`` is a required query param: ``/spots/Snapper Rocks?region=QLD``.
    """
    spot = spots.get_spot(spot_name, region)
    if spot is None:
        raise HTTPException(status_code=404, detail=f"Spot '{spot_name}' ({region}) not found")
    return spot.model_dump()


@app.get("/forecast")
async def forecast(spot: str, region: str, days: int = 7):
    """Hourly marine + wind forecast via forecasts.py."""
    s = spots.get_spot(spot, region)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Spot '{spot}' ({region}) not found")
    return forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng, days=days)


@app.get("/score")
async def score(spot: str, region: str, days: int = 7, skill: str | None = None):
    """Deterministic hourly surf scores via scoring.py."""
    s = spots.get_spot(spot, region)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Spot '{spot}' ({region}) not found")
    fc = forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng, days=days)
    skill_level = tools._normalize_skill(skill)
    return scoring.score_week(fc, s.model_dump(), skill_level=skill_level)


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Agent answer via agent.py tool loop."""
    try:
        agent = SurfAgent(provider=request.provider, model=request.model)
        answer = agent.run(request.question)
    except ValueError as exc:
        # Missing/unknown provider config (e.g. unset HF_TOKEN/NVIDIA_API_KEY)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent run failed: {exc}") from exc
    trace_json = agent.trace.to_json() if agent.trace else None
    return AskResponse(answer=answer, trace=trace_json)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)