from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importing your internal modules to lock in the architecture [cite: 233]
from app.api.routes import router as api_router
from app.api.websockets import router as websocket_router
from app.core.firebase_db import initialize_firebase

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application lifecycle.
    Initializes the Firebase Admin SDK on startup so Firestore is available to all routes[cite: 275].
    """
    print("INITIALIZING GRID: Starting Firebase Admin SDK...")
    try:
        initialize_firebase()
        print("GRID ONLINE: Firebase initialization complete.")
    except Exception as e:
        print(f"CRITICAL SYSTEM FAILURE: Could not initialize Firebase: {e}")
        # Application will still start, but database routes will return 500 errors.
    
    yield
    
    print("SHUTTING DOWN GRID: Terminating Cyber Odyssey backend...")

# Initialize the core FastAPI application [cite: 235]
app = FastAPI(
    title="Cyber Odyssey 2.0 API",
    description="Backend services for Event Management. Handles auth, data routing, and real-time WebSocket broadcasting.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS (Cross-Origin Resource Sharing)
# This allows your local dev environment (127.0.0.1) and Vercel to talk to Render[cite: 236].
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Change to ["https://your-domain.vercel.app"] for production security
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# Mount the API and WebSocket routers [cite: 236]
# Ensure your frontend calls match these prefixes (e.g., /api/v1/participants)
app.include_router(api_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/ws")

# Root health-check endpoint for Render's automated monitoring [cite: 236]
@app.get("/", tags=["Health Check"])
async def health_check():
    return {
        "status": "online",
        "system": "Cyber Odyssey 2.0 Backend",
        "message": "All systems operational."
    }