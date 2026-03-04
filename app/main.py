import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import firestore
import sendgrid

from app.api.routes import router as api_router
from app.api.websockets import router as websocket_router
from app.core.firebase_db import initialize_firebase
from app.core.config import get_settings

settings = get_settings()


async def run_system_diagnostics():
    """
    Boot-time health check. Verifies Firebase and SendGrid are reachable.
    Called on startup and exposed via /api/v1/debug/health.
    """
    results = {"firebase": "FAILED", "email": "FAILED"}

    # 1. Firebase connectivity — try a lightweight document read
    try:
        db = firestore.client()
        db.collection("system_check").document("health").get()
        results["firebase"] = "OPERATIONAL"
    except Exception as e:
        print(f"DIAGNOSTIC CRITICAL: Firebase Connection Refused - {e}")

    # 2. SendGrid — validate the API key with a lightweight account info call.
    #    This uses HTTPS (port 443) which is always open on Render.
    #    It does NOT send an email; it just confirms the key is accepted.
    try:
        def _ping_sendgrid():
            sg       = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            response = sg.client.api_keys._(settings.SENDGRID_API_KEY[:20] + "...").get()
            # Any non-500 response means the key was accepted by SendGrid's API
            return response.status_code

        loop        = asyncio.get_event_loop()
        status_code = await loop.run_in_executor(None, _ping_sendgrid)

        # 401 = wrong key, 403 = insufficient scope, 200/404 = key is valid
        if status_code in (200, 403, 404):
            results["email"] = "OPERATIONAL"
        else:
            print(f"DIAGNOSTIC WARNING: SendGrid returned unexpected status {status_code}")
            results["email"] = f"DEGRADED ({status_code})"

    except Exception as e:
        # Non-fatal — a bad key here won't prevent the server from booting.
        # It will surface as a warning in the logs and in /debug/health.
        print(f"DIAGNOSTIC WARNING: SendGrid key validation failed - {e}")

    return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes Firebase and runs pre-flight diagnostics on boot.
    """
    print("INITIALIZING GRID: Starting Firebase Admin SDK...")
    initialize_firebase()

    health = await run_system_diagnostics()
    print(
        f"PRE-FLIGHT CHECK COMPLETE: "
        f"Firebase: {health['firebase']} | "
        f"Email: {health['email']}"
    )

    yield
    print("SHUTTING DOWN GRID: All systems offline.")


app = FastAPI(
    title="Cyber Odyssey 2.0 API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/ws")


@app.get("/api/v1/debug/health", tags=["Diagnostics"])
async def secure_health_check():
    """
    Returns a live JSON health report for Firebase and SendGrid.
    Hit this endpoint after a fresh deployment to confirm both services
    are connected before opening registrations.
    """
    report = await run_system_diagnostics()
    if "FAILED" in report.values():
        raise HTTPException(status_code=503, detail=report)
    return {
        "status": "Healthy",
        "services": report,
    }


@app.get("/", tags=["Health Check"])
async def root_check():
    return {"status": "online", "message": "Cyber Odyssey 2.0 Backend Operational."}