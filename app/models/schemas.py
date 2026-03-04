from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
from datetime import datetime


# ---------------------------------------------------------
# 1. USER AUTH & ROLE SYNC
# ---------------------------------------------------------
class UserSyncSchema(BaseModel):
    uid: str
    email: EmailStr
    role: str
    assigned_event: Optional[str] = ""


# ---------------------------------------------------------
# 2. TEAM MANAGEMENT
# ---------------------------------------------------------
class TeamCreateSchema(BaseModel):
    event_id: str
    team_name: str


class TeamResponse(BaseModel):
    team_id: str
    team_name: str
    event_id: str
    status: str
    created_at: datetime


# ---------------------------------------------------------
# 3. PARTICIPANT REGISTRATION
# ---------------------------------------------------------
class ParticipantRegisterSchema(BaseModel):
    event_id: str
    full_name: str
    enrollment_number: str
    is_external: bool = False
    university_name: Optional[str] = ""
    department: str
    academic_year: str
    contact_number: str
    gmail: EmailStr
    team_id: Optional[str] = None

    # Optional — only sent by the volunteer "Register Node" flow.
    # The public registration form (register.html) does NOT send this field;
    # Firebase Auth is created client-side in registration.js instead.
    # Making this required was the root cause of the 422 "Field required" error
    # on every public registration attempt.
    password: Optional[str] = None


class ParticipantResponse(BaseModel):
    participant_id: str
    team_id: Optional[str]
    event_id: str
    full_name: str
    status: str
    registered_at: datetime


# ---------------------------------------------------------
# 4. PARTICIPANT UPDATE (PATCH — Volunteer / Admin CRM)
# ---------------------------------------------------------
class ParticipantUpdateSchema(BaseModel):
    """
    All fields Optional so the frontend can PATCH only changed fields
    without resubmitting the full profile.
    """
    event_id: Optional[str] = None
    full_name: Optional[str] = None
    enrollment_number: Optional[str] = None
    is_external: Optional[bool] = None
    university_name: Optional[str] = None
    department: Optional[str] = None
    academic_year: Optional[str] = None
    contact_number: Optional[str] = None
    gmail: Optional[EmailStr] = None
    team_id: Optional[str] = None


# ---------------------------------------------------------
# 5. QR SCANNING & ATTENDANCE
# ---------------------------------------------------------
class QRScanSchema(BaseModel):
    event_id: str
    participant_id: str
    scanned_by_uid: str


# ---------------------------------------------------------
# 6. COMMUNICATIONS DISPATCH
# ---------------------------------------------------------
class CommsPayloadSchema(BaseModel):
    target_event: str
    subject: str
    body: str


# ---------------------------------------------------------
# 7. JUDGE EVALUATIONS
# ---------------------------------------------------------
class EvaluationPayloadSchema(BaseModel):
    target_id: str
    event_id: str
    scores: Dict[str, int]
    feedback: Optional[str] = ""


# ---------------------------------------------------------
# 8. TOURNAMENT BRACKET UPDATES
# ---------------------------------------------------------
class BracketUpdateSchema(BaseModel):
    round_index: int
    match_index: int
    winner_id: str


# ---------------------------------------------------------
# 9. VOLUNTEER AUTHORIZATION
# ---------------------------------------------------------
class VolunteerCreateSchema(BaseModel):
    email: EmailStr
    password: str
    assigned_event: str