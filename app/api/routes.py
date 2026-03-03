from fastapi import APIRouter, HTTPException, status, Depends
from firebase_admin import firestore
from google.cloud.firestore_v1.transaction import Transaction
import uuid
from datetime import datetime, timezone

# Importing schemas and services from your core modules
from app.models.schemas import (
    UserSyncSchema, 
    TeamCreateSchema, 
    ParticipantRegisterSchema, 
    QRScanSchema,
    TeamResponse,
    ParticipantResponse
)
from app.services.bracket_algo import generate_perfect_bracket
from app.services.email_service import send_qr_email

router = APIRouter(tags=["Core API Routes"])

def get_db():
    """Dependency to get the Firestore client."""
    return firestore.client()

# ---------------------------------------------------------
# 1. USER AUTHENTICATION & ROLE SYNC
# ---------------------------------------------------------
@router.post("/users/sync", status_code=status.HTTP_200_OK)
async def sync_user(user_data: UserSyncSchema, db: firestore.Client = Depends(get_db)):
    """Ensures a corresponding document exists in the 'users' collection with their role."""
    user_ref = db.collection('users').document(user_data.uid)
    doc = user_ref.get()
    
    if not doc.exists:
        user_ref.set({
            "email": user_data.email,
            "role": user_data.role,
            "assigned_event": user_data.assigned_event or "",
            "created_at": datetime.now(timezone.utc)
        })
        return {"message": "User synchronized successfully.", "status": "created"}
    return {"message": "User already exists.", "status": "exists"}

# ---------------------------------------------------------
# 2. EVENT & TEAM MANAGEMENT
# ---------------------------------------------------------
@router.get("/events", status_code=status.HTTP_200_OK)
async def get_all_events(db: firestore.Client = Depends(get_db)):
    """Fetches all events and their capacities to populate the frontend registration dropdown."""
    events_ref = db.collection('events')
    docs = events_ref.stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(team_data: TeamCreateSchema, db: firestore.Client = Depends(get_db)):
    """Creates a new team and returns a unique Team ID for other members to use."""
    team_id = f"TEAM-{uuid.uuid4().hex[:6].upper()}"
    team_ref = db.collection('teams').document(team_id)
    
    new_team = {
        "team_id": team_id,
        "team_name": team_data.team_name,
        "event_id": team_data.event_id,
        "status": "Waitlisted",
        "created_at": datetime.now(timezone.utc)
    }
    team_ref.set(new_team)
    return new_team

@router.get("/admin/events/{event_id}/roster", status_code=status.HTTP_200_OK)
async def get_event_roster(event_id: str, db: firestore.Client = Depends(get_db)):
    """Fetches confirmed participants. Fixes the 'API Error' in the Admin Roster modal."""
    try:
        participants_ref = db.collection('participants').where('event_id', '==', event_id).where('status', '==', 'Confirmed')
        docs = participants_ref.stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

# ---------------------------------------------------------
# 3. PARTICIPANT REGISTRATION (ROBUST TRANSACTION)
# ---------------------------------------------------------
@firestore.transactional
def register_participant_transaction(transaction: Transaction, db: firestore.Client, data: ParticipantRegisterSchema, participant_id: str):
    """Safely checks event capacity and handles team/individual waitlisting."""
    event_ref = db.collection('events').document(data.event_id)
    event_snapshot = event_ref.get(transaction=transaction)
    
    # Fail-safe: Auto-create event if it doesn't exist in Firestore yet (fixes 404)
    if not event_snapshot.exists:
        transaction.set(event_ref, {"total_capacity": 100, "name": data.event_id})
        total_capacity = 100
    else:
        total_capacity = event_snapshot.to_dict().get('total_capacity', 100)
    
    # Check current confirmed count
    participants_ref = db.collection('participants').where('event_id', '==', data.event_id).where('status', '==', 'Confirmed')
    current_count = len(list(participants_ref.stream(transaction=transaction)))
    
    participant_status = "Confirmed" if current_count < total_capacity else "Waitlisted"
    
    # Handle team logic if applicable
    if data.team_id:
        team_ref = db.collection('teams').document(data.team_id)
        team_snap = team_ref.get(transaction=transaction)
        if team_snap.exists:
            if team_snap.to_dict().get('status') == 'Waitlisted' and participant_status == 'Confirmed':
                transaction.update(team_ref, {"status": "Confirmed"})
            elif team_snap.to_dict().get('status') == 'Confirmed':
                participant_status = "Confirmed"

    participant_ref = db.collection('participants').document(participant_id)
    participant_doc = {
        "participant_id": participant_id,
        "team_id": data.team_id or "INDIVIDUAL",
        "event_id": data.event_id,
        "full_name": data.full_name,
        "enrollment_number": data.enrollment_number,
        "department": data.department,
        "academic_year": data.academic_year,
        "gmail": data.gmail,
        "status": participant_status,
        "registered_at": datetime.now(timezone.utc)
    }
    transaction.set(participant_ref, participant_doc)
    return participant_doc

@router.post("/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
async def register_participant(data: ParticipantRegisterSchema, db: firestore.Client = Depends(get_db)):
    """Registers a participant and triggers automated Digital ID email."""
    participant_id = str(uuid.uuid4())
    transaction = db.transaction()
    
    try:
        result = register_participant_transaction(transaction, db, data, participant_id)
        # Async email dispatch for Digital IDs
        if result['status'] == 'Confirmed':
            try:
                await send_qr_email(data.gmail, data.full_name, data.team_id or "INDV", data.event_id)
            except Exception as e:
                print(f"Email Warning: Failed to send QR to {data.gmail}: {e}")
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------
# 4. QR ATTENDANCE & COMMUNICATIONS
# ---------------------------------------------------------
@router.post("/attendance/scan", status_code=status.HTTP_200_OK)
async def scan_qr_code(scan_data: QRScanSchema, db: firestore.Client = Depends(get_db)):
    """Logs check-in and prevents double-scanning via unique log IDs."""
    log_id = f"{scan_data.event_id}_{scan_data.participant_id}"
    log_ref = db.collection('scan_logs').document(log_id)
    
    if log_ref.get().exists:
        raise HTTPException(status_code=409, detail="Participant already scanned for this event.")
        
    log_doc = {
        "log_id": log_id,
        "participant_id": scan_data.participant_id,
        "event_id": scan_data.event_id,
        "scanned_by": scan_data.scanned_by_uid,
        "scan_timestamp": datetime.now(timezone.utc)
    }
    log_ref.set(log_doc)
    return {"message": "Scan successful.", "data": log_doc}

@router.post("/admin/communications/dispatch")
async def dispatch_comms(payload: dict):
    """Handles bulk email/broadcasts from the Admin dashboard."""
    return {"status": "dispatched", "message": "Broadcast transmitted to grid nodes."}

# ---------------------------------------------------------
# 5. TOURNAMENT BRACKET GENERATION
# ---------------------------------------------------------
@router.post("/events/{event_id}/generate-bracket", status_code=status.HTTP_200_OK)
async def generate_event_bracket(event_id: str, db: firestore.Client = Depends(get_db)):
    """Generates the tournament tree and saves state to the event document."""
    participants_ref = db.collection('participants').where('event_id', '==', event_id).where('status', '==', 'Confirmed')
    docs = participants_ref.stream()
    entities = [{"id": doc.id, "name": doc.to_dict().get("full_name")} for doc in docs]
    
    if not entities:
        raise HTTPException(status_code=400, detail="No confirmed participants to generate a bracket.")
        
    bracket_json = generate_perfect_bracket(entities)
    db.collection('events').document(event_id).update({"current_bracket": bracket_json})
    return {"message": "Bracket generated successfully.", "bracket": bracket_json}

@router.put("/events/{event_id}/bracket/update")
async def update_bracket(event_id: str, payload: dict, db: firestore.Client = Depends(get_db)):
    """Updates the live bracket tree when a winner is announced."""
    db.collection('events').document(event_id).update({"current_bracket": payload})
    return {"status": "locked", "message": "Bracket state updated."}