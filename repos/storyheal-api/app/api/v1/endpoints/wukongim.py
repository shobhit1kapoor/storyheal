"""WuKongIM public endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from app.core.logging import get_logger
from app.schemas.wukongim import WuKongIMRouteResponse
from app.services.wukongim_client import wukongim_client

logger = get_logger("endpoints.wukongim")
router = APIRouter()


@router.get(
    "/route",
    response_model=WuKongIMRouteResponse,
    summary="Get WuKongIM WebSocket Connection Address",
    description="Get the WebSocket long connection address for a user from WuKongIM service. "
                "This endpoint does not require authentication and can be used by both staff and visitors."
)
async def get_wukongim_route(
    uid: str,
    request: Request,
) -> WuKongIMRouteResponse:
    """
    Get WuKongIM WebSocket connection address for a user.
    
    This is a public endpoint that proxies the request to WuKongIM service
    to retrieve the WebSocket connection address (tcp_addr and ws_addr) for
    the specified user ID.
    
    Args:
        uid: User ID (can be staff UID or visitor UID)
        
    Returns:
        WuKongIM route response with connection addresses
        
    Raises:
        400: If uid parameter is missing or invalid
        502: If WuKongIM service is unreachable or returns an error
        503: If WuKongIM integration is disabled
    """
    if not uid or not uid.strip():
        logger.warning("Route request with empty uid parameter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uid parameter is required and cannot be empty"
        )
    
    logger.info(f"Getting WuKongIM route for uid: {uid}")
    
    try:
        result = await wukongim_client.get_route(uid=uid)

        # WuKongIM reports its container-local address. Browsers running on a
        # different origin (for example the Vercel admin/widget deployments)
        # must instead connect through the public reverse proxy. Derive that
        # address from trusted proxy headers without persisting a temporary
        # tunnel hostname in application data.
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        # Cloudflare Tunnel reaches Nginx over HTTP, so Nginx's proxy header can
        # describe the internal hop. CF-Visitor preserves the browser scheme.
        if "https" in request.headers.get("cf-visitor", "").lower():
            forwarded_proto = "https"
        forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", "")).split(",")[0].strip()
        if forwarded_host:
            if forwarded_proto == "https":
                result.wss_addr = f"wss://{forwarded_host}/wss"
            else:
                result.ws_addr = f"ws://{forwarded_host}/wss"
        
        logger.info(f"Successfully retrieved route for uid: {uid}")
        
        return result
        
    except HTTPException:
        # Re-raise HTTPExceptions from the client
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting route for uid {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve route from WuKongIM service"
        )
