"""API router initializers."""

from fastapi import APIRouter


def get_api_router() -> APIRouter:
    """Construct and return the API router."""

    from backend.routers.slack import router as slack_router

    api_router = APIRouter()
    api_router.include_router(slack_router, prefix="/slack", tags=["slack"])
    return api_router

