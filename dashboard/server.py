"""FastAPI app: static files, Jinja2, route registration (per PRD)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="AM4 Ops Center Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/hub", include_in_schema=False)
def redirect_hub():
    return RedirectResponse(url="/hub-explorer", status_code=307)


@app.get("/route", include_in_schema=False)
def redirect_route():
    return RedirectResponse(url="/route-analyzer", status_code=307)


@app.get("/fleet", include_in_schema=False)
def redirect_fleet():
    return RedirectResponse(url="/fleet-planner", status_code=307)


@app.get("/contribution", include_in_schema=False)
def redirect_contribution():
    return RedirectResponse(url="/contributions", status_code=307)


from dashboard.routes import api_routes, pages

app.include_router(pages.router)
app.include_router(api_routes.router)
