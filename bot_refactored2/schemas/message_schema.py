"""Message and API response schemas."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class MessageSchema(BaseModel):
    """User message schema."""
    user_id: int
    text: str = Field(..., min_length=1, max_length=4096)
    message_type: str = Field(default="text", pattern="^(text|news|question)$")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        from_attributes = True


class AnalysisResponseSchema(BaseModel):
    """API analysis response schema (from backend)."""
    summary_text: str
    impact_points: List[str] = Field(default_factory=list)
    simplified_text: Optional[str] = None
    educational_context: Optional[str] = None
    xp_earned: int = Field(default=0, ge=0)
    
    class Config:
        from_attributes = True
