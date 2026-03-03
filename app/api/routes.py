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
    VolunteerCreateSchema,
    ParticipantUpdateSchema 
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
    return {"message": "User context synchronized.", "uid": user_data.uid}

# ---------------------------------------------------------
# 2. EVENT DISCOVERY & CAPACITIES
# ---------------------------------------------------------
@router.get("/events")
async def get_events(db: firestore.Client = Depends(get_db)):
    events_ref = db.collection('events')
    docs = events_ref.stream()
    events = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        events.append(data)
    return events

# ---------------------------------------------------------
# 3. TEAM CREATION
# ---------------------------------------------------------
@router.post("/teams", response_model=TeamResponse)
async def create_team(team_data: TeamCreateSchema, db: firestore.Client = Depends(get_db)):
    # 1. Validation to prevent undefined event IDs
    if not team_data.event_id or team_data.event_id == "undefined":
        raise HTTPException(status_code=400, detail="Invalid Event ID provided.")

    # 2. Check for duplicate team names within the same event
    teams_ref = db.collection('teams')
    query = teams_ref.where('event_id', '==', team_data.event_id).where('team_name', '==', team_data.team_name).limit(1)
    if len(list(query.stream())) > 0:
        raise HTTPException(status_code=400, detail=f"Team '{team_data.team_name}' already exists in this event.")

    team_id = f"TM-{uuid.uuid4().hex[:6].upper()}"
    
    new_team = {
        "team_id": team_id,
        "team_name": team_data.team_name,
        "event_id": team_data.event_id,
        "created_at": datetime.now(timezone.utc),
        "status": "Active"
    }
    
    db.collection('teams').document(team_id).set(new_team)
    return new_team

# ---------------------------------------------------------
# 4. PARTICIPANT REGISTRATION & DIGITAL ID
# ---------------------------------------------------------
@router.post("/participants", response_model=ParticipantResponse)
async def register_participant(data: ParticipantRegisterSchema, db: firestore.Client = Depends(get_db)):
    try:
        # 1. Check if email is already registered globally (prevent double registration)
        existing_query = db.collection('participants').where('gmail', '==', data.gmail).limit(1).stream()
        if len(list(existing_query)) > 0:
            raise HTTPException(status_code=400, detail="This email is already registered in the system.")

        # 2. Prepare payload
        participant_data = data.dict()
        participant_data['registered_at'] = datetime.now(timezone.utc)
        participant_data['attendance_status'] = "Pending"
        participant_data['scanned_at'] = None

        # 3. Insert into database
        _, doc_ref = db.collection('participants').add(participant_data)
        participant_id = doc_ref.id
        
        # 4. Dispatch Email with QR Code (Runs synchronously for now)
        try:
            send_qr_email(
                participant_email=data.gmail,
                participant_name=data.full_name,
                event_name=data.event_id.replace('event_', '').replace('_', ' ').title(),
                participant_id=participant_id,
                team_id=data.team_id or "INDIVIDUAL"
            )
        except Exception as e:
            print(f"Non-fatal error: Email dispatch failed for {data.gmail}. Reason: {str(e)}")

        return {
            "participant_id": participant_id,
            "team_id": data.team_id,
            "event_id": data.event_id,
            "full_name": data.full_name,
            "status": "Registered",
            "registered_at": participant_data['registered_at']
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 5. ATTENDANCE & QR SCANNING
# ---------------------------------------------------------
@router.post("/attendance/scan")
async def log_attendance_scan(scan_data: QRScanSchema, db: firestore.Client = Depends(get_db)):
    try:
        doc_ref = db.collection('participants').document(scan_data.participant_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Invalid Digital ID. Record not found.")

        p_data = doc.to_dict()

        # Security check: Are they scanning for the right event?
        if p_data.get('event_id') != scan_data.event_id:
            raise HTTPException(status_code=403, detail="Participant is registered for a different event module.")

        if p_data.get('attendance_status') == "Present":
            return {"message": "Participant already checked in.", "status": "duplicate"}

        scan_time = datetime.now(timezone.utc)

        # 1. Update the participant node
        doc_ref.update({
            "attendance_status": "Present",
            "scanned_at": scan_time,
            "scanned_by": scan_data.scanned_by_uid
        })

        # 2. Push to the immutable Global Attendance Log (Updated Collection Name)
        db.collection('attendance').add({
            "participant_id": scan_data.participant_id,
            "participant_name": p_data.get("full_name", "Unknown Node"),
            "event_id": scan_data.event_id,
            "scanned_by_uid": scan_data.scanned_by_uid,
            "timestamp": scan_time
        })

        return {"message": "Check-in successful.", "status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 6. SYSTEM SYNCHRONIZATION
# ---------------------------------------------------------
@router.get("/system/time")
async def get_server_time():
    return {"server_time": datetime.now(timezone.utc).isoformat()}

# ---------------------------------------------------------
# 7. ADMIN / VOLUNTEER ROSTER FETCH
# ---------------------------------------------------------
@router.get("/admin/events/{event_id}/roster")
async def get_event_roster(event_id: str, db: firestore.Client = Depends(get_db)):
    try:
        query = db.collection('participants').where('event_id', '==', event_id)
        docs = query.stream()
        roster = []
        for doc in docs:
            data = doc.to_dict()
            data['participant_id'] = doc.id
            roster.append(data)
        return roster
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 8. COMMUNICATIONS DISPATCH
# ---------------------------------------------------------
@router.post("/admin/comms/dispatch")
async def dispatch_communications(payload: CommsPayloadSchema, db: firestore.Client = Depends(get_db)):
    try:
        db.collection('communications_log').add({
            "target_event": payload.target_event,
            "subject": payload.subject,
            "body": payload.body,
            "dispatched_at": datetime.now(timezone.utc)
        })
        return {"message": f"Comms dispatched to {payload.target_event} successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 9. EVALUATION (JUDGE SCORING)
# ---------------------------------------------------------
@router.post("/evaluations/submit")
async def submit_evaluation(payload: EvaluationPayloadSchema, db: firestore.Client = Depends(get_db)):
    try:
        total_score = sum(payload.scores.values())

        eval_data = {
            "target_id": payload.target_id, 
            "event_id": payload.event_id,
            "scores": payload.scores,
            "total_score": total_score,
            "feedback": payload.feedback,
            "submitted_at": datetime.now(timezone.utc)
        }

        db.collection('evaluations').add(eval_data)
        return {"message": "Evaluation logged successfully.", "total_score": total_score}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 10. BRACKET INITIALIZATION (Tournament Events)
# ---------------------------------------------------------
@router.post("/events/bracket/{event_id}/generate")
async def initialize_bracket(event_id: str, db: firestore.Client = Depends(get_db)):
    try:
        participants_ref = db.collection('participants').where('event_id', '==', event_id).where('attendance_status', '==', 'Present')
        docs = participants_ref.stream()
        
        competitors = [{"id": doc.id, "name": doc.to_dict().get("full_name", "Unknown")} for doc in docs]
        
        if len(competitors) < 2:
             raise HTTPException(status_code=400, detail="Not enough checked-in participants to generate a bracket.")

        bracket_structure = generate_perfect_bracket(competitors)
        
        db.collection('event_settings').document(f"{event_id}_bracket").set({
            "rounds": bracket_structure,
            "generated_at": datetime.now(timezone.utc),
            "status": "Active"
        })
        
        return {"message": "Bracket generated successfully.", "bracket": bracket_structure}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 11. BRACKET ADVANCEMENT
# ---------------------------------------------------------
@router.post("/events/bracket/{event_id}/update")
async def update_bracket(event_id: str, payload: BracketUpdateSchema, db: firestore.Client = Depends(get_db)):
    try:
        bracket_ref = db.collection('event_settings').document(f"{event_id}_bracket")
        doc = bracket_ref.get()
        if not doc.exists:
             raise HTTPException(status_code=404, detail="Bracket not found for this event.")
             
        bracket_data = doc.to_dict()
        rounds = bracket_data.get("rounds", [])
        
        r_idx = payload.round_index
        m_idx = payload.match_index
        if r_idx >= len(rounds) - 1:
            raise HTTPException(status_code=400, detail="Cannot advance from the final round.")
            
        current_match = rounds[r_idx][m_idx]
        
        winner_node = None
        if current_match.get("p1") and current_match["p1"].get("id") == payload.winner_id:
            winner_node = current_match["p1"]
        elif current_match.get("p2") and current_match["p2"].get("id") == payload.winner_id:
            winner_node = current_match["p2"]
            
        if not winner_node:
            raise HTTPException(status_code=400, detail="Winner ID not found in the specified match.")

        next_round_idx = r_idx + 1
        next_match_idx = m_idx // 2
        participant_slot = "p1" if m_idx % 2 == 0 else "p2"
        
        rounds[next_round_idx][next_match_idx][participant_slot] = winner_node

        bracket_ref.update({"rounds": rounds})
        return {"message": "Node successfully locked."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 12. AUTHORIZE VOLUNTEER
# ---------------------------------------------------------
@router.post("/admin/volunteers")
async def register_volunteer(data: VolunteerCreateSchema, db: firestore.Client = Depends(get_db)):
    try:
        user_record = auth.create_user(
            email=data.email,
            password=data.password
        )
        
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

# ---------------------------------------------------------
# 13. UPDATE PARTICIPANT DATA (PATCH)
# ---------------------------------------------------------
@router.patch("/admin/participants/{participant_id}")
async def update_participant(participant_id: str, data: ParticipantUpdateSchema, db: firestore.Client = Depends(get_db)):
    try:
        update_data = data.dict(exclude_none=True)
        
        if not update_data:
            return {"message": "No data provided to update.", "status": "success"}
            
        doc_ref = db.collection('participants').document(participant_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Participant node not found in the grid.")
            
        doc_ref.update(update_data)
        
        return {"message": "Node data synchronized successfully.", "status": "success"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 14. REMOVE PARTICIPANT NODE (DELETE)
# ---------------------------------------------------------
@router.delete("/admin/participants/{participant_id}")
async def delete_participant(participant_id: str, db: firestore.Client = Depends(get_db)):
    try:
        doc_ref = db.collection('participants').document(participant_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Participant node not found in the grid.")
        
        participant_data = doc.to_dict()
        gmail = participant_data.get("gmail")
        
        doc_ref.delete()
        
        if gmail:
            try:
                user_record = auth.get_user_by_email(gmail)
                auth.delete_user(user_record.uid)
                db.collection('users').document(user_record.uid).delete()
            except Exception:
                pass
                
        return {"message": "Node access permanently revoked.", "status": "success"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# NEW PHASE 4: ADMIN STAFF MANAGEMENT
# =========================================================

# ---------------------------------------------------------
# 15. FETCH ACTIVE STAFF (ADMIN DASHBOARD)
# ---------------------------------------------------------
@router.get("/admin/staff")
async def get_active_staff(db: firestore.Client = Depends(get_db)):
    try:
        query = db.collection('users').where('role', 'in', ['Admin', 'Volunteer'])
        docs = query.stream()
        
        staff_list = []
        for doc in docs:
            data = doc.to_dict()
            staff_list.append({
                "uid": doc.id,
                "email": data.get("email", "Unknown"),
                "role": data.get("role", "Unknown"),
                "assigned_event": data.get("assigned_event", "Master Control"),
                "last_active": data.get("synced_at") or data.get("created_at")
            })
            
        return staff_list
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# NEW PHASE 5: REAL-TIME GLOBAL ATTENDANCE LOGS
# =========================================================

# ---------------------------------------------------------
# 16. FETCH GLOBAL ATTENDANCE LOGS
# ---------------------------------------------------------
@router.get("/admin/attendance/logs")
async def get_attendance_logs(db: firestore.Client = Depends(get_db)):
    try:
        # Query the logs collection, order by newest first, limit to 200 (Updated Collection Name)
        query = db.collection('attendance').order_by(
            'timestamp', direction=firestore.Query.DESCENDING
        ).limit(200)
        
        docs = query.stream()
        
        logs = []
        for doc in docs:
            data = doc.to_dict()
            data['log_id'] = doc.id
            logs.append(data)
            
        return logs
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))