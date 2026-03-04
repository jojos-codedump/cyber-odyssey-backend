# app/core/auth_deps.py
# ─────────────────────────────────────────────────────────────────────────────
# Reusable FastAPI dependencies for Firebase token verification.
#
# Usage in routes.py:
#   from app.core.auth_deps import require_auth, require_role
#
#   # Any authenticated user (participant, volunteer, admin)
#   @router.post("/attendance/scan")
#   async def scan(data: QRScanSchema, caller=Depends(require_auth)):
#
#   # Admin or Volunteer only
#   @router.get("/admin/events/{event_id}/roster")
#   async def roster(event_id: str, caller=Depends(require_role(["Admin","Volunteer"]))):
#
#   # Admin only
#   @router.post("/admin/volunteers")
#   async def create_volunteer(data: ..., caller=Depends(require_role(["Admin"]))):
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth, firestore
from typing import List

_bearer = HTTPBearer(auto_error=True)


def _verify_token(credentials: HTTPAuthorizationCredentials) -> dict:
    """
    Verifies the Firebase ID token in the Authorization: Bearer <token> header.
    Returns the decoded token dict (contains uid, email, etc.) on success.
    Raises HTTP 401 on missing/invalid token, HTTP 403 on revoked token.
    """
    try:
        decoded = auth.verify_id_token(credentials.credentials, check_revoked=True)
        return decoded
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token has been revoked. Please log in again.",
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token.",
        )


def _get_caller_role(uid: str) -> str:
    """
    Reads the caller's role from the Firestore `users` collection.
    This is the authoritative source — not whatever the client claims.
    """
    db = firestore.client()
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller has no user profile in the system.",
        )
    return doc.to_dict().get("role", "")


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Dependency: requires any valid Firebase session.
    Returns decoded token dict so the route can read caller.uid etc.
    """
    return _verify_token(credentials)


def require_role(allowed_roles: List[str]):
    """
    Dependency factory: requires a valid Firebase session AND a specific role.

        caller = Depends(require_role(["Admin"]))
        caller = Depends(require_role(["Admin", "Volunteer"]))

    Returns the decoded token dict enriched with `caller["role"]`.
    """
    async def _check(
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    ) -> dict:
        decoded = _verify_token(credentials)
        role    = _get_caller_role(decoded["uid"])

        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {allowed_roles}. Your role: {role}.",
            )

        decoded["role"] = role
        return decoded

    return _check