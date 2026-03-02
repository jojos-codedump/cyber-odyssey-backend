from fastapi import APIRouter, HTTPException, status, Depends
from firebase_admin import firestore
from google.cloud.firestore_v1.transaction import Transaction
import uuid
from datetime import datetime, timezone

# These imports reference modules we will build next.
# They are locked in to ensure perfect synchronization.
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
    """
    Called by the frontend immediately after a user signs up via Firebase Auth.
    Ensures a corresponding document exists in the 'users' collection with their role.
    """
    user_ref = db.collection('users').document(user_data.uid)
    doc = user_ref.get()
    
    if not doc.exists:
        user_ref.set({
            "email": user_data.email,
            "role": user_data.role, # 'Admin', 'Volunteer', 'Judge', 'Participant'
            "assigned_event": user_data.assigned_event, # Null unless Volunteer
            "created_at": datetime.now(timezone.utc)
        })
        return {"message": "User synchronized successfully.", "status": "created"}
    return {"message": "User already exists.", "status": "exists"}

# ---------------------------------------------------------
# 2. EVENT & TEAM MANAGEMENT
# ---------------------------------------------------------
@router.get("/events", status_code=status.HTTP_200_OK)
async def get_all_events(db: firestore.Client = Depends(get_db)):
    """Fetches all events and their capacities to populate the frontend."""
    events_ref = db.collection('events')
    docs = events_ref.stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(team_data: TeamCreateSchema, db: firestore.Client = Depends(get_db)):
    """
    Creates a new team for multi-participant events. 
    Returns the generated Team ID for other members to use.
    """
    team_id = str(uuid.uuid4())
    team_ref = db.collection('teams').document(team_id)
    
    # Default status is Waitlisted. The participant registration transaction 
    # will upgrade this to 'Confirmed' if capacity allows.
    new_team = {
        "team_id": team_id,
        "team_name": team_data.team_name,
        "event_id": team_data.event_id,
        "status": "Waitlisted",
        "created_at": datetime.now(timezone.utc)
    }
    team_ref.set(new_team)
    return new_team

# ---------------------------------------------------------
# 3. PARTICIPANT REGISTRATION & WAITLIST LOGIC
# ---------------------------------------------------------
@firestore.transactional
def register_participant_transaction(transaction: Transaction, db: firestore.Client, data: ParticipantRegisterSchema, participant_id: str):
    """
    Firestore transaction to safely check event capacity and handle waitlisting.
    """
    event_ref = db.collection('events').document(data.event_id)
    event_snapshot = event_ref.get(transaction=transaction)
    
    if not event_snapshot.exists:
        raise HTTPException(status_code=404, detail="Event not found.")
        
    event_data = event_snapshot.to_dict()
    total_capacity = event_data.get('total_capacity', 0)
    
    # Count current confirmed participants for this event
    # Note: In a massive scale app, we'd use a distributed counter. 
    # For a college fest, a direct query inside the transaction is acceptable.
    participants_ref = db.collection('participants').where('event_id', '==', data.event_id).where('status', '==', 'Confirmed')
    current_count = len(list(participants_ref.stream(transaction=transaction)))
    
    participant_status = "Confirmed" if current_count < total_capacity else "Waitlisted"
    
    # If part of a team, update the team status based on the first member's entry
    if data.team_id:
        team_ref = db.collection('teams').document(data.team_id)
        team_snap = team_ref.get(transaction=transaction)
        if team_snap.exists:
            # If the team was waitlisted but capacity exists, confirm the team
            if team_snap.to_dict().get('status') == 'Waitlisted' and participant_status == 'Confirmed':
                transaction.update(team_ref, {"status": "Confirmed"})
            # If the team is already confirmed, the new member is automatically confirmed
            elif team_snap.to_dict().get('status') == 'Confirmed':
                participant_status = "Confirmed"

    # Write Participant Document
    participant_ref = db.collection('participants').document(participant_id)
    participant_doc = {
        "participant_id": participant_id,
        "team_id": data.team_id,
        "event_id": data.event_id,
        "full_name": data.full_name,
        "enrollment_number": data.enrollment_number,
        "is_external": data.is_external,
        "university_name": data.university_name,
        "department": data.department,
        "academic_year": data.academic_year,
        "contact_number": data.contact_number,
        "gmail": data.gmail,
        "status": participant_status,
        "registered_at": datetime.now(timezone.utc)
    }
    transaction.set(participant_ref, participant_doc)
    
    return participant_doc

@router.post("/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
async def register_participant(data: ParticipantRegisterSchema, db: firestore.Client = Depends(get_db)):
    """Registers a participant and automatically calculates Confirmation/Waitlist status."""
    participant_id = str(uuid.uuid4())
    transaction = db.transaction()
    
    try:
        result = register_participant_transaction(transaction, db, data, participant_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------
# 4. QR CODE ATTENDANCE LOGGING (FAIL-SAFED)
# ---------------------------------------------------------
@firestore.transactional
def log_scan_transaction(transaction: Transaction, db: firestore.Client, scan_data: QRScanSchema):
    """
    Enforces the STRICT CONSTRAINT: A participant can only be scanned ONCE per event.
    """
    # Create a composite ID to simulate SQL composite unique constraint
    log_id = f"{scan_data.event_id}_{scan_data.participant_id}"
    log_ref = db.collection('scan_logs').document(log_id)
    
    log_snapshot = log_ref.get(transaction=transaction)
    
    if log_snapshot.exists:
        # Prevents accidental double-scans if the frontend debounce fails
        raise ValueError("Participant has already been scanned for this event.")
        
    log_doc = {
        "log_id": log_id,
        "participant_id": scan_data.participant_id,
        "event_id": scan_data.event_id,
        "scanned_by": scan_data.scanned_by_uid,
        "scan_timestamp": datetime.now(timezone.utc)
    }
    
    transaction.set(log_ref, log_doc)
    return log_doc

@router.post("/attendance/scan", status_code=status.HTTP_200_OK)
async def scan_qr_code(scan_data: QRScanSchema, db: firestore.Client = Depends(get_db)):
    """Logs an entry scan from a Volunteer/Admin dashboard."""
    transaction = db.transaction()
    try:
        result = log_scan_transaction(transaction, db, scan_data)
        
        # Here, we would trigger the WebSocket broadcast to the Admin master dashboard
        # from app.api.websockets import broadcast_scan
        # await broadcast_scan(result)
        
        return {"message": "Scan successful.", "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error during scan.")

# ---------------------------------------------------------
# 5. TOURNAMENT BRACKET GENERATION
# ---------------------------------------------------------
@router.post("/events/{event_id}/generate-bracket", status_code=status.HTTP_200_OK)
async def generate_event_bracket(event_id: str, db: firestore.Client = Depends(get_db)):
    """
    Fetches all confirmed teams/participants for Cyber Visionary or Digital Dilemma 
    and passes them to the binary tree algorithm to inject 'byes' and create the JSON bracket.
    """
    # Fetch confirmed entities for this event
    participants_ref = db.collection('participants').where('event_id', '==', event_id).where('status', '==', 'Confirmed')
    docs = participants_ref.stream()
    
    entities = [{"id": doc.id, "name": doc.to_dict().get("full_name")} for doc in docs]
    
    if not entities:
        raise HTTPException(status_code=400, detail="No confirmed participants to generate a bracket.")
        
    # generate_perfect_bracket is a mathematical function we will build in services
    bracket_json = generate_perfect_bracket(entities)
    
    # Save the generated bracket state to the event document
    db.collection('events').document(event_id).update({
        "current_bracket": bracket_json
    })
    
    return {"message": "Bracket generated successfully.", "bracket": bracket_json}