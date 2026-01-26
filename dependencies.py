"""
FastAPI dependencies for authentication and authorization
"""

import logging
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)


async def get_current_user(authorization: str = Header(None)) -> str:
    """
    Get current user from authorization header.

    This is a placeholder implementation. In production, this should:
    - Validate JWT token
    - Extract user_id from token
    - Check user permissions

    Args:
        authorization: Authorization header (e.g., "Bearer <token>")

    Returns:
        user_id: User identifier

    Raises:
        HTTPException: If authentication fails
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )

    # TODO: Implement proper JWT validation
    # For now, extract user_id from header (development only)

    # Expected format: "Bearer <token>" or just "<user_id>"
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        # TODO: Decode JWT and extract user_id
        # For now, use token as user_id
        user_id = token
    else:
        user_id = authorization

    logger.info(f"Authenticated user: {user_id}")
    return user_id


async def get_optional_user(authorization: str = Header(None)) -> str | None:
    """
    Get current user if authenticated, otherwise return None

    Args:
        authorization: Authorization header (optional)

    Returns:
        user_id or None
    """
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None
