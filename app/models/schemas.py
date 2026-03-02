from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal
from datetime import datetime

# ---------------------------------------------------------
# 1. USER AUTHENTICATION SCHEMAS
# ---------------------------------------------------------

class UserSyncSchema(BaseModel):
    """Schema for syncing Firebase Auth users to the Firestore 'users' collection."""
    uid: str = Field(..., description="The unique Firebase Auth UID")
    email: EmailStr = Field(..., description="User's registered email address")
    role: Literal['Admin', 'Volunteer', 'Judge', 'Participant'] = Field(
        ..., 
        description="Role-Based Access Control designation"
    )
    assigned_event: Optional[str] = Field(
        None, 
        description="The event ID a Volunteer is assigned to (Null for others)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "uid": "abc123xyz456",
                "email": "admin@cyberodyssey.com",
                "role": "Admin",
                "assigned_event": None
            }
        }
    }

# ---------------------------------------------------------
# 2. EVENT & TEAM SCHEMAS
# ---------------------------------------------------------

class TeamCreateSchema(BaseModel):
    """Schema for a Team Lead creating a new team for a multi-participant event."""
    team_name: str = Field(..., min_length=2, max_length=100, description="The name of the team")
    event_id: str = Field(..., description="The ID of the event (e.g., event_codeshield)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "team_name": "AgniSena",
                "event_id": "event_codeshield"
            }
        }
    }

class TeamResponse(TeamCreateSchema):
    """Schema for the backend response after a team is successfully created."""
    team_id: str = Field(..., description="The generated UUID for the team")
    status: Literal['Confirmed', 'Waitlisted'] = Field(..., description="Current capacity status")
    created_at: datetime = Field(..., description="Timestamp of creation")

# ---------------------------------------------------------
# 3. PARTICIPANT REGISTRATION SCHEMAS
# ---------------------------------------------------------

class ParticipantRegisterSchema(BaseModel):
    """
    Schema for individual participant registration. 
    Requires specific data fields tailored for the registration portal.
    """
    event_id: str = Field(..., description="The ID of the event being registered for")
    team_id: Optional[str] = Field(None, description="The Team ID if joining an existing team")
    full_name: str = Field(..., min_length=2, max_length=150, description="Participant's full name")
    enrollment_number: str = Field(..., max_length=100, description="University Enrollment Number")
    is_external: bool = Field(False, description="True if from another college")
    university_name: Optional[str] = Field(
        "University of Engineering & Management, Kolkata", 
        max_length=150, 
        description="Name of the university (Required if is_external is True)"
    )
    department: str = Field(..., max_length=100, description="Academic Department")
    academic_year: str = Field(..., max_length=20, description="Current year of study")
    contact_number: str = Field(..., max_length=20, description="Primary contact number")
    gmail: EmailStr = Field(..., description="Gmail address for automated QR code delivery")

    @field_validator('university_name')
    def validate_external_university(cls, v, info):
        # Enforce that external participants provide their university name
        if info.data.get('is_external') is True and not v:
            raise ValueError('University name is required for external participants.')
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "event_id": "event_visionary",
                "team_id": "uuid-1234-5678",
                "full_name": "Samaraho Mukherjee",
                "enrollment_number": "1202XXXXXX",
                "is_external": False,
                "university_name": "University of Engineering & Management, Kolkata",
                "department": "CSE (IoT, CS, BT)",
                "academic_year": "3rd Year",
                "contact_number": "+91 9876543210",
                "gmail": "participant@gmail.com"
            }
        }
    }

class ParticipantResponse(ParticipantRegisterSchema):
    """Schema for the backend response after a participant is successfully registered."""
    participant_id: str = Field(..., description="The generated UUID for the participant")
    status: Literal['Confirmed', 'Waitlisted'] = Field(..., description="Current capacity status")
    registered_at: datetime = Field(..., description="Timestamp of registration")

# ---------------------------------------------------------
# 4. DIGITAL IDENTIFICATION & ATTENDANCE SCHEMAS
# ---------------------------------------------------------

class QRScanSchema(BaseModel):
    """
    Schema for validating incoming QR code scans from Volunteer/Admin dashboards.
    Ensures all necessary relational IDs are present for the composite unique check.
    """
    participant_id: str = Field(..., description="The UUID of the participant being scanned")
    event_id: str = Field(..., description="The ID of the event they are entering")
    scanned_by_uid: str = Field(..., description="The Firebase Auth UID of the Volunteer/Admin scanning")

    model_config = {
        "json_schema_extra": {
            "example": {
                "participant_id": "uuid-part-1234",
                "event_id": "event_codeshield",
                "scanned_by_uid": "uuid-vol-5678"
            }
        }
    }