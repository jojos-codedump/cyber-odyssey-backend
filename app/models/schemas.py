from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
from datetime import datetime

# 1. User Sync Schema (Fixes Database Error during login/sync)
class UserSyncSchema(BaseModel):
    uid: str
    email: EmailStr
    role: str
    # Fixed: Default to empty string to prevent validation failure if null is sent
    assigned_event: Optional[str] = ""

# 2. Team Creation Schema
class TeamCreateSchema(BaseModel):
    event_id: str
    team_name: str

class TeamResponse(BaseModel):
    team_id: str
    team_name: str
    event_id: str
    status: str
    created_at: datetime

# 3. Registration Schema (Fixes 404 & Validation Errors)
class ParticipantRegisterSchema(BaseModel):
    event_id: str
    full_name: str
    enrollment_number: str
    # Fixed: Ensure bool type matches the 'is_external' checkbox
    is_external: bool = False
    university_name: Optional[str] = ""
    department: str
    academic_year: str
    contact_number: str
    gmail: EmailStr
    team_id: Optional[str] = None

class ParticipantResponse(BaseModel):
    participant_id: str
    team_id: Optional[str]
    event_id: str
    full_name: str
    status: str
    registered_at: datetime

# 4. QR & Attendance
class QRScanSchema(BaseModel):
    event_id: str
    participant_id: str
    scanned_by_uid: str 

# 5. Communications Dispatch
class CommsPayloadSchema(BaseModel):
    target_event: str
    subject: str
    body: str

# 6. Judge Evaluations
class EvaluationPayloadSchema(BaseModel):
    target_id: str
    scores: Dict[str, int]
    feedback: Optional[str] = ""
    event_id: str

# 7. Tournament Bracket Updates
class BracketUpdateSchema(BaseModel):
    round_index: int
    match_index: int
    winner_id: str

# 8. Volunteer Authorization Schema
class VolunteerCreateSchema(BaseModel):
    email: EmailStr
    password: str
    assigned_event: str