"""v1 API 라우터 집합."""
from fastapi import APIRouter

from app.api.v1 import (
    actions,
    alerts,
    auth,
    billing,
    company,
    metrics,
    opportunities,
    pursuits,
    recommendations,
    reminders,
    settings as settings_routes,
    stats,
    watches,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(company.router, prefix="/company", tags=["company"])
api_router.include_router(recommendations.router, tags=["recommendations"])
api_router.include_router(opportunities.router, prefix="/opportunities", tags=["opportunities"])
api_router.include_router(actions.router, prefix="/opportunities", tags=["actions"])
api_router.include_router(stats.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(settings_routes.router, prefix="/settings", tags=["settings"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(pursuits.router, prefix="/pursuits", tags=["pursuits"])
api_router.include_router(watches.router, prefix="/watches", tags=["watches"])
api_router.include_router(reminders.router, prefix="/reminders", tags=["reminders"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
