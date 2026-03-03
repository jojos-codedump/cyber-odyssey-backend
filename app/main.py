import smtplib
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import firestore

# Core imports from your source code
from app.api.routes import router as api_router
from app.api.websockets import router as websocket_router
from app.core.firebase_db import initialize_firebase
from app.core.config import get_settings

settings = get_settings()

async def run_system_diagnostics():
    """
    Internal testing kit to verify cloud service health.
    """
    results = {"firebase": "FAILED", "smtp": "FAILED"}
    
    # 1. Test Firebase Connectivity
    try:
        db = firestore.client()
        # Attempt to read a single document from a known collection
        db.collection('system_check').document('health').get()
        results["firebase"] = "OPERATIONAL"
    except Exception as e:
        print(f"DIAGNOSTIC CRITICAL: Firebase Connection Refused - {e}")

    # 2. Test SMTP/Email Health
    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=5) as server:
            server.starttls()
            server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
            results["smtp"] = "OPERATIONAL"
    except Exception as e:
        print(f"DIAGNOSTIC CRITICAL: SMTP Authentication Failed - {e}")
        
    return results

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager with integrated testing kit.
    """
    print("INITIALIZING GRID: Starting Firebase Admin SDK...")
    initialize_firebase() # [cite: 233-234, 275]
    
    # Run diagnostics on boot
    health = await run_system_diagnostics()
    print(f"PRE-FLIGHT CHECK COMPLETE: Firebase: {health['firebase']} | SMTP: {health['smtp']}")
    
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
    Secure endpoint to return a JSON health report.
    Useful for verifying SMTP/Firebase status after a fresh deployment.
    """
    report = await run_system_diagnostics()
    if "FAILED" in report.values():
        raise HTTPException(status_code=503, detail=report)
    return {
        "status": "Healthy",
        "timestamp": firestore.SERVER_TIMESTAMP,
        "services": report
    }

@app.get("/", tags=["Health Check"])
async def root_check():
    return {"status": "online", "message": "Cyber Odyssey 2.0 Backend Operational."}