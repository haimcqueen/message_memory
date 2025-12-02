"""Pydantic models for transcription webhook requests."""
from pydantic import BaseModel
from typing import Literal, Union


class DualRecordingRequest(BaseModel):
    """Request for dual recording transcription (mic + system audio)."""
    userId: str
    recordingType: Literal["dual"]
    micUrl: str      # Agent's microphone recording (left channel)
    systemUrl: str   # System audio - user's voice (right channel)


class IrlRecordingRequest(BaseModel):
    """Request for IRL recording transcription (single file with both speakers)."""
    userId: str
    recordingType: Literal["irl"]
    irlUrl: str      # Single file with both speakers


# Union type for the endpoint
TranscriptionRequest = Union[DualRecordingRequest, IrlRecordingRequest]
