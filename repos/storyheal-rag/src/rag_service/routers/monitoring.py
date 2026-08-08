"""
Monitoring and metrics endpoints.
"""

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from ..config import get_settings

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus format for monitoring and alerting.
    """
    settings = get_settings()
    
    if not settings.metrics_enabled:
        return {"message": "Metrics collection is disabled"}
    
    # Generate Prometheus metrics
    metrics_data = generate_latest(REGISTRY)
    
    from fastapi import Response
    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )
