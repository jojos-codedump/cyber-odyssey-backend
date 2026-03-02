from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# We will generate these modules next. 
# Importing them here now ensures the architecture is perfectly locked in.
from app.api.routes import router as api_router
from app.api.websockets import router as websocket_router
from app.core.firebase_db import initialize_firebase


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.
    Code before the 'yield' runs on application startup.
    Code after the 'yield' runs on application shutdown.
    """
    # Initialize the Firebase Admin SDK so it's globally available to our routes
    print("Initializing Firebase Admin SDK...")
    initialize_firebase()
    print("Firebase initialization complete.")
    
    yield
    
    # Any necessary cleanup on shutdown would go here
    print("Shutting down Cyber Odyssey backend...")


# Initialize the core FastAPI application
app = FastAPI(
    title="Cyber Odyssey 2.0 API",
    description="Backend services for the Cyber Odyssey 2.0 Event Management System. Handles auth validation, data routing, and real-time WebSocket broadcasting.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS (Cross-Origin Resource Sharing)
# This allows your Vercel frontend to make HTTP requests to this Render backend.
# Note: For strict production security, change ["*"] to ["https://your-vercel-domain.vercel.app"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# Mount the API and WebSocket routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/ws")

# Root health-check endpoint
@app.get("/", tags=["Health Check"])
async def health_check():
    """
    Simple endpoint to verify the backend is live. 
    Useful for Render's automated health checks.
    """
    return {
        "status": "online",
        "system": "Cyber Odyssey 2.0 Backend",
        "message": "All systems operational."
    }