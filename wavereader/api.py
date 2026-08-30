"""FastAPI backend: data endpoints owned by the core modules.

Gradio (app.py) is the demo UI; this API exposes the same core for tests
and any non-Gradio consumer. Endpoints: /spots, /forecast, /score, /ask.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="wavereader", version="0.1.0")


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/spots")
async def list_spots(query: str = "", region: str | None = None, skill: str | None = None):
    """Search/validate breaks via spots.py. TODO: wire up."""
    raise NotImplementedError


@app.get("/forecast")
async def forecast(spot: str, days: int = 7):
    """Hourly marine + wind forecast via forecasts.py. TODO: wire up."""
    raise NotImplementedError


@app.get("/score")
async def score(spot: str, days: int = 7):
    """Deterministic hourly surf scores via scoring.py. TODO: wire up."""
    raise NotImplementedError


@app.post("/ask")
async def ask(question: str):
    """Agent answer via agent.py tool loop. TODO: wire up."""
    raise NotImplementedError
