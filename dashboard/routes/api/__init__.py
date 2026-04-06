"""Aggregated `/api` router (HTMX fragments + JSON)."""

from __future__ import annotations

from fastapi import APIRouter

from dashboard.routes.api import analytics, fleet, fleet_health, hubs, meta, my_routes, recommendations

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(meta.router)
router.include_router(analytics.router)
router.include_router(recommendations.router)
router.include_router(fleet.router)
router.include_router(fleet_health.router)
router.include_router(my_routes.router)
router.include_router(hubs.router)
