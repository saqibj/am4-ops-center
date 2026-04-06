"""FastAPI app: static files, Jinja2, route registration (per PRD)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent


def _auth_template_context(request: Request) -> dict[str, Any]:
    from dashboard.auth import get_dashboard_auth_token

    return {"auth_token": get_dashboard_auth_token()}


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates"),
    context_processors=[_auth_template_context],
)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    from dashboard.auth import get_dashboard_auth_token

    get_dashboard_auth_token()
    yield


app = FastAPI(title="AM4 Ops Center Dashboard", lifespan=_app_lifespan)
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
