from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal


class MusicGenerationRequest(BaseModel):
    is_instrumental: bool
    vocal_gender: Optional[Literal["male", "female"]] = None
    lyrics: Optional[str] = Field(None, max_length=200)
    style: str = Field(..., min_length=1)
    duration_seconds: int = Field(..., ge=5, le=60)

    @field_validator('vocal_gender')
    @classmethod
    def validate_vocal_gender(cls, v, info):
        is_instrumental = info.data.get('is_instrumental')
        if not is_instrumental and v is None:
            raise ValueError('vocal_gender is required when is_instrumental is False')
        if is_instrumental and v is not None:
            raise ValueError('vocal_gender should not be provided when is_instrumental is True')
        return v

    @field_validator('lyrics')
    @classmethod
    def validate_lyrics(cls, v, info):
        is_instrumental = info.data.get('is_instrumental')
        if not is_instrumental and (v is None or v.strip() == ''):
            raise ValueError('lyrics is required when is_instrumental is False')
        if is_instrumental and v is not None:
            raise ValueError('lyrics should not be provided when is_instrumental is True')
        return v


class CompositionResponse(BaseModel):
    composition_plan: dict


class GenerateMusicResponse(BaseModel):
    task_id: str
    status: str  # "pending", "processing", "completed", "failed"
    message: str


class StatusResponse(BaseModel):
    task_id: str
    status: str  # "pending", "processing", "completed", "failed"
    progress: Optional[float] = None  # 0-100 if available
    message: Optional[str] = None


class CreditsResponse(BaseModel):
    remaining_credits: Optional[float] = None
    total_credits: Optional[float] = None
    subscription_tier: Optional[str] = None


# Voice Conversion Models
class VoiceConversionResponse(BaseModel):
    job_id: str
    status: str  # "pending", "processing", "completed", "failed"
    message: str


class VoiceConversionStatusResponse(BaseModel):
    job_id: str
    status: str  # "pending", "processing", "completed", "failed"
    progress: Optional[float] = None  # 0-100 if available
    message: Optional[str] = None
