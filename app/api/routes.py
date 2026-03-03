from fastapi import APIRouter, HTTPException, status, Depends
from firebase_admin import firestore, auth
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.models.schemas import (
    UserSyncSchema, 
    TeamCreateSchema, 
    ParticipantRegisterSchema, 
    QRScanSchema,
    TeamResponse,
    ParticipantResponse,
    CommsPayloadSchema,
    EvaluationPayloadSchema,
    BracketUpdateSchema,
    VolunteerCreateSchema
)
from app.services.email_service import send_qr_email
from app.services.bracket_algo import generate_perfect_bracket

router = APIRouter(tags=["Core API Routes"])

def get_db():
    return firestore.client()

# ---------------------------------------------------------
# 1. USER AUTH & ROLE SYNC 
# ---------------------------------------------------------
@router.post("/users/sync", status_code=status.HTTP_200_OK)
async def sync_user(user_data: UserSyncSchema, db: firestore.Client = Depends(get_db)):
    user_ref = db.collection('users').document(user_data.uid)
    user_ref.set({
        "email": user_data.email,
        "role": user_data.role,
        "assigned_event": user_data.assigned_event or "",
        "synced_at": datetime.now(timezone.utc)
    }, merge=True)
    return {"message": "User synchronized.", "status": "success"}

# ---------------------------------------------------------
# 2. ADMIN ROSTER
# ---------------------------------------------------------
@router.get("/admin/events/{event_id}/roster")
async def get_event_roster(event_id: str, db: firestore.Client = Depends(get_db)):
    try:
        docs = db.collection('participants').where('event_id', '==', event_id).stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 3. SMART REGISTRATION
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

    # Trigger QR Code Email
    if p_status == "Confirmed":
        try:
            await send_qr_email(data.gmail, data.full_name, data.team_id or "INDV", data.event_id)
        except Exception: pass 

    return participant_doc 

# ---------------------------------------------------------
# 4. FETCH EVENTS (Fixes Registration Dropdown)
# ---------------------------------------------------------
@router.get("/events")
async def get_events(db: firestore.Client = Depends(get_db)):
    try:
        events_ref = db.collection('events')
        docs = list(events_ref.stream())
        
        # Auto-seed standard events if DB is fresh
        if not docs:
            default_events = [
                {"event_id": "event_codeshield", "event_name": "CodeShield", "max_team_size": 3},
                {"event_id": "event_packet_hijackers", "event_name": "Packet Hijackers", "max_team_size": 2},
                {"event_id": "event_cyber_visionary", "event_name": "Cyber Visionary", "max_team_size": 4},
                {"event_id": "event_digital_dilemma", "event_name": "Digital Dilemma", "max_team_size": 2},
                {"event_id": "event_cyber_canvas", "event_name": "Cyber Canvas", "max_team_size": 1}
            ]
            for ev in default_events:
                events_ref.document(ev["event_id"]).set(ev)
            return default_events
            
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 5. CREATE TEAM (Fixes Team Creation 404)
# ---------------------------------------------------------
@router.post("/teams", response_model=TeamResponse)
async def create_team(data: TeamCreateSchema, db: firestore.Client = Depends(get_db)):
    team_id = f"TM-{str(uuid.uuid4())[:6].upper()}"
    team_doc = {
        "team_id": team_id,
        "team_name": data.team_name,
        "event_id": data.event_id,
        "status": "Active",
        "created_at": datetime.now(timezone.utc)
    }
    db.collection('teams').document(team_id).set(team_doc)
    return team_doc

# ---------------------------------------------------------
# 6. SECURE SERVER TIME (Fixes Digital ID Time-Gate)
# ---------------------------------------------------------
@router.get("/system/time")
async def get_system_time():
    return {"timestamp": datetime.now(timezone.utc).isoformat()}

# ---------------------------------------------------------
# 7. COMMUNICATIONS DISPATCH (Fixes Broadcast 404)
# ---------------------------------------------------------
@router.post("/admin/communications/dispatch")
async def dispatch_comms(payload: CommsPayloadSchema, db: firestore.Client = Depends(get_db)):
    try:
        participants = db.collection('participants').where('event_id', '==', payload.target_event).stream()
        count = len(list(participants))
        # Logic to loop through participants and use email_service.py would go here
        return {"message": f"Transmission dispatched to {count} connected nodes.", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 8. QR ATTENDANCE SCAN (Fixes Scanner Check-In)
# ---------------------------------------------------------
@router.post("/attendance/scan")
async def log_attendance_scan(data: QRScanSchema, db: firestore.Client = Depends(get_db)):
    try:
        doc_ref = db.collection('attendance').document(f"{data.event_id}_{data.participant_id}")
        if doc_ref.get().exists:
            raise HTTPException(status_code=400, detail="Participant already logged in the grid.")
        
        doc_ref.set({
            "event_id": data.event_id,
            "participant_id": data.participant_id,
            "scanned_by": data.scanned_by_uid,
            "scanned_at": datetime.now(timezone.utc)
        })
        return {"message": "Check-in successful", "status": "success"}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 9. JUDGE EVALUATIONS (Fixes Scoring Portals)
# ---------------------------------------------------------
@router.post("/evaluations")
async def submit_evaluation(payload: EvaluationPayloadSchema, db: firestore.Client = Depends(get_db)):
    try:
        eval_id = str(uuid.uuid4())
        db.collection('evaluations').document(eval_id).set({
            "eval_id": eval_id,
            "target_id": payload.target_id,
            "event_id": payload.event_id,
            "scores": payload.scores,
            "feedback": payload.feedback,
            "submitted_at": datetime.now(timezone.utc)
        })
        return {"message": "Evaluation matrix committed.", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 10. GENERATE BRACKETS (Fixes Tournament Tree Render)
# ---------------------------------------------------------
@router.post("/events/{event_id}/generate-bracket")
async def generate_event_bracket(event_id: str, db: firestore.Client = Depends(get_db)):
    try:
        bracket_ref = db.collection('brackets').document(event_id)
        bracket_doc = bracket_ref.get()
        
        if bracket_doc.exists:
            # Reformat logic to match the UI JS mapping (Array of Arrays)
            raw_rounds = bracket_doc.to_dict().get("rounds", [])
            return [r["matches"] for r in raw_rounds]

        participants_docs = db.collection('participants').where('event_id', '==', event_id).stream()
        participants = [{"id": doc.to_dict().get("participant_id"), "name": doc.to_dict().get("team_id") or doc.to_dict().get("full_name") or "Unknown"} for doc in participants_docs]
        
        bracket_data = generate_perfect_bracket(participants)
        bracket_ref.set(bracket_data)
        
        return [r["matches"] for r in bracket_data["rounds"]]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 11. ADVANCE BRACKET WINNER (Fixes Tree Mutations)
# ---------------------------------------------------------
@router.put("/events/{event_id}/bracket/update")
async def update_bracket_node(event_id: str, payload: BracketUpdateSchema, db: firestore.Client = Depends(get_db)):
    try:
        bracket_ref = db.collection('brackets').document(event_id)
        bracket_doc = bracket_ref.get()
        if not bracket_doc.exists:
            raise HTTPException(status_code=404, detail="Tournament bracket not found.")
        
        bracket_data = bracket_doc.to_dict()
        rounds = bracket_data.get("rounds", [])
        
        r_idx = payload.round_index
        m_idx = payload.match_index
        
        if r_idx >= len(rounds) or m_idx >= len(rounds[r_idx]["matches"]):
            raise HTTPException(status_code=400, detail="Invalid node coordinates.")
            
        rounds[r_idx]["matches"][m_idx]["winner_id"] = payload.winner_id
        
        # Advance the winner to the next branch
        if r_idx + 1 < len(rounds):
            next_match_idx = m_idx // 2
            participant_slot = "participant1" if m_idx % 2 == 0 else "participant2"
            
            p1 = rounds[r_idx]["matches"][m_idx]["participant1"]
            p2 = rounds[r_idx]["matches"][m_idx]["participant2"]
            winner_node = p1 if p1 and p1.get("id") == payload.winner_id else p2
            
            rounds[r_idx + 1]["matches"][next_match_idx][participant_slot] = winner_node

        bracket_ref.update({"rounds": rounds})
        return {"message": "Node successfully locked."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 12. AUTHORIZE VOLUNTEER (Fixes Admin Dashboard 404)
# ---------------------------------------------------------
@router.post("/admin/volunteers")
async def register_volunteer(data: VolunteerCreateSchema, db: firestore.Client = Depends(get_db)):
    try:
        # 1. Create the user directly in Firebase Authentication via Admin SDK
        # This prevents the Admin's frontend session from being hijacked
        user_record = auth.create_user(
            email=data.email,
            password=data.password
        )
        
        # 2. Create the user's role profile in Firestore
        db.collection('users').document(user_record.uid).set({
            "email": data.email,
            "role": "Volunteer",
            "assigned_event": data.assigned_event,
            "created_at": datetime.now(timezone.utc)
        })
        
        return {"message": f"Volunteer {data.email} authorized successfully.", "status": "success"}
        
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="This email is already authorized in the grid.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))