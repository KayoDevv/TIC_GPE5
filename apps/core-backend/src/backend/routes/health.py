from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for Kubernetes. No auth required."""
    return {"status": "ok"}
