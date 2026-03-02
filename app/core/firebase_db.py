import firebase_admin
from firebase_admin import credentials, firestore
import logging
from app.core.config import get_settings

# Set up logging for server observability
logger = logging.getLogger(__name__)

def initialize_firebase():
    """
    Initializes the Firebase Admin SDK using credentials loaded securely 
    from the environment variables via our Pydantic settings manager.
    
    This function is called by the lifespan context manager in main.py 
    when the FastAPI application starts up.
    """
    try:
        # We attempt to get the default app. 
        # If it succeeds, it means Firebase is already running (e.g., during a Uvicorn hot-reload).
        firebase_admin.get_app()
        logger.info("Firebase Admin SDK is already initialized. Skipping re-initialization.")
        
    except ValueError:
        # A ValueError is raised if the default app does not exist. 
        # This is the expected behavior on a fresh server startup.
        logger.info("Starting fresh Firebase Admin SDK initialization...")
        
        # Load the centralized settings singleton
        settings = get_settings()
        
        try:
            # Retrieve the parsed JSON dictionary from our config manager
            cert_dict = settings.get_firebase_credentials_dict()
            
            # Create the Firebase credential object
            cred = credentials.Certificate(cert_dict)
            
            # Initialize the global Firebase application
            firebase_admin.initialize_app(cred)
            
            logger.info("Firebase Admin SDK initialized successfully. Connection to Firestore established.")
            
        except Exception as e:
            # If this fails, the backend cannot function. We log the critical error and raise it.
            logger.critical(f"CRITICAL: Failed to initialize Firebase Admin SDK. Error: {e}")
            raise e

def get_db_client() -> firestore.Client:
    """
    Returns an instance of the Firestore client.
    While our routes.py calls `firestore.client()` directly within its dependency injection,
    having this utility function here allows for easier mocking during unit testing later.
    """
    return firestore.client()