"""Liveness check — used by Railway and by the database dashboard's "main website" check."""

from fastapi import APIRouter

router = APIRouter(tags=["system"], include_in_schema=False)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
