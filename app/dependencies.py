"""PhantomAPI — Authentication dependencies.

Luna mode: ANY non-empty Bearer <redacted> is accepted. There is no fixed secret —
whatever string the client sends is treated as valid. Keep the server bound to
127.0.0.1 so only the local machine can reach it.
"""

from fastapi import Request, HTTPException


async def verify_api_key(request: Request) -> str:
    """Accept any non-empty Bearer <redacted> as valid.

    Returns the provided token on success, raises 401 only when the
    Authorization header is missing or the token is empty.
    """
    authorization = request.headers.get("authorization", "")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")

    # Strip "Bearer " prefix (case-insensitive)
    token = authorization
    if token.lower().startswith("bearer "):
        token = token[7:]
    token = token.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Empty API key.")

    return token
