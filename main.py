from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from routes.states import router as states_router
from routes.breaks import router as breaks_router

BASE_DIR = Path(__file__).parent

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(states_router)
app.include_router(breaks_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/{state}/{break_name}", response_class=HTMLResponse)
async def get_break_page(request: Request, state: str, break_name: str):
    return templates.TemplateResponse(
        "break.html", {"request": request, "state": state, "break_name": break_name}
    )
