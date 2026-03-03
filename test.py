import os
import asyncio
import json
from dotenv import load_dotenv
from firebase_admin import firestore, credentials, initialize_app
import smtplib
from email.message import EmailMessage

# 1. Load Environment Variables from your local .env file
load_dotenv()

def initialize_local_grid():
    """Initializes Firebase Admin SDK using the .env service account key."""
    try:
        # Parse the JSON string from .env
        service_account_info = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY"))
        cred = credentials.Certificate(service_account_info)
        initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"CRITICAL: Firebase Initialization Failed: {e}")
        return None

async def test_smtp_and_registration():
    print("--- CYBER ODYSSEY 2.0: LOCAL INTEGRITY TEST ---")
    
    db = initialize_local_grid()
    if not db: return

    # 2. Test SMTP Health
    print("\n[1/3] Checking SMTP Handshake...")
    sender_email = os.getenv("SENDER_EMAIL")
    sender_pass = os.getenv("SENDER_PASSWORD") # Ensure this is your 16-char App Password
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.starttls()
            server.login(sender_email, sender_pass)
            print(f" > SMTP Status: OPERATIONAL (Logged in as {sender_email})")
    except Exception as e:
        print(f" ! SMTP Status: FAILED - {e}")

    # 3. Test Firestore Write (Meghnad's Registration)
    print("\n[2/3] Attempting Direct Firestore Write...")
    participant_id = "TEST-LOCAL-SYNC"
    participant_data = {
        "participant_id": participant_id,
        "full_name": "Meghnad Debnath",
        "enrollment_number": "12023002029146",
        "event_id": "event_codeshield",
        "department": "CSE(IoT, CS, BT)",
        "academic_year": "3rd",
        "gmail": "samaraho.career@gmail.com",
        "status": "Confirmed",
        "registered_at": firestore.SERVER_TIMESTAMP
    }

    try:
        # Check if the event document exists to prevent 404-style logic errors
        event_ref = db.collection('events').document('event_codeshield')
        if not event_ref.get().exists:
            print(" > Warning: event_codeshield not found. Auto-creating event document...")
            event_ref.set({"total_capacity": 100, "name": "CodeShield"})

        db.collection('participants').document(participant_id).set(participant_data)
        print(f" > Firestore: SUCCESS (Data committed for {participant_data['full_name']})")
    except Exception as e:
        print(f" ! Firestore: FAILED - {e}")

    print("\n[3/3] Final Verification")
    print("--------------------------------------------------")
    print("If both steps passed, your credentials and SDK logic are correct.")
    print("The previous 'Timeout' was likely due to Render's free tier sleep mode.")
    print("--------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(test_smtp_and_registration())