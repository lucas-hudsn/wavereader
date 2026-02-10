from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routes.states import router as states_router
from routes.breaks import router as breaks_router

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"

app = FastAPI()

app.include_router(states_router)
app.include_router(breaks_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve React frontend static files
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        # Serve index.html for all non-API routes (SPA routing)
        return FileResponse(str(FRONTEND_DIR / "index.html"))
