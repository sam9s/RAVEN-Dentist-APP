"""FastAPI application entrypoint."""

from fastapi import FastAPI

from backend.routers import get_api_router
from backend.utils.config import get_settings


settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(get_api_router())


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return service health status."""

    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    """Return application version metadata."""

    return {"version": settings.app_version}
