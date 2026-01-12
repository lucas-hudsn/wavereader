from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import os
from pathlib import Path
from agents.surf_graph import run_surf_forecast_agent

# Setup
app = FastAPI()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/forecast")
async def forecast(request: Request):
    """Run the surf forecast agent for a given beach"""
    data = await request.json()
    beach = data.get("beach", "").strip()
    
    if not beach:
        return JSONResponse({"error": "Beach name required"}, status_code=400)
    
    try:
        result = await run_surf_forecast_agent(beach)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}
