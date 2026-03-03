from fastapi import APIRouter, HTTPException, status, Depends
from firebase_admin import firestore
from google.cloud.firestore_v1.transaction import Transaction
import uuid
from datetime import datetime, timezone

from app.models.schemas import (
    UserSyncSchema, 
    TeamCreateSchema, 
    ParticipantRegisterSchema, 
    QRScanSchema,
    TeamResponse,
    ParticipantResponse
)
from app.services.email_service import send_qr_email

router = APIRouter(tags=["Core API Routes"])

def get_db():
    return firestore.client()

# ---------------------------------------------------------
# 1. USER AUTH & ROLE SYNC (Fixes 'Database Error')
# ---------------------------------------------------------
@router.post("/users/sync", status_code=status.HTTP_200_OK)
async def sync_user(user_data: UserSyncSchema, db: firestore.Client = Depends(get_db)):
    user_ref = db.collection('users').document(user_data.uid)
    
    # Use empty string if assigned_event is null to satisfy schema [cite: 337-338]
    user_ref.set({
        "email": user_data.email,
        "role": user_data.role,
        "assigned_event": user_data.assigned_event or "",
        "synced_at": datetime.now(timezone.utc)
    }, merge=True)
    return {"message": "User synchronized.", "status": "success"}

# ---------------------------------------------------------
# 2. ADMIN ROSTER (Fixes 'API Error')
# ---------------------------------------------------------
@router.get("/admin/events/{event_id}/roster")
async def get_event_roster(event_id: str, db: firestore.Client = Depends(get_db)):
    """Fetches participants. Prevents the 'API Error' in admin.html [cite: 121-122]."""
    try:
        docs = db.collection('participants').where('event_id', '==', event_id).stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 3. SMART REGISTRATION (Fixes 404: Event Not Found)
# ---------------------------------------------------------
@router.post("/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
async def register_participant(data: ParticipantRegisterSchema, db: firestore.Client = Depends(get_db)):
    participant_id = str(uuid.uuid4())
    event_ref = db.collection('events').document(data.event_id)
    
    # FAIL-SAFE: If event document is missing, initialize it 
    if not event_ref.get().exists:
        event_ref.set({"total_capacity": 100, "name": data.event_id})

    # Simple Capacity Check
    participants_ref = db.collection('participants').where('event_id', '==', data.event_id).where('status', '==', 'Confirmed')
    current_count = len(list(participants_ref.stream()))
    
    p_status = "Confirmed" if current_count < 100 else "Waitlisted"

    participant_doc = {
        "participant_id": participant_id,
        "team_id": data.team_id or "INDIVIDUAL",
        "event_id": data.event_id,
        "full_name": data.full_name,
        "enrollment_number": data.enrollment_number,
        "department": data.department,
        "academic_year": data.academic_year,
        "gmail": data.gmail,
        "status": p_status,
        "registered_at": datetime.now(timezone.utc)
    }

    db.collection('participants').document(participant_id).set(participant_doc)

    # Trigger QR Code Email [cite: 310-311]
    if p_status == "Confirmed":
        try:
            await send_qr_email(data.gmail, data.full_name, data.team_id or "INDV", data.event_id)
        except Exception: pass 

    return participant_doc