"""Quest-related Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class QuestSchema(BaseModel):
    """Quest definition schema."""
    quest_id: str
    title: str
    description: str
    objective: str
    xp_reward: int = Field(..., ge=10, le=1000)
    difficulty_level: str = Field(default="normal", pattern="^(easy|normal|hard)$")
    required_level: int = Field(default=1, ge=1, le=50)
    completion_criteria: str
    
    class Config:
        from_attributes = True


class QuestProgressSchema(BaseModel):
    """Quest progress tracking."""
    user_id: int
    quest_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    is_completed: bool = Field(default=False)
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    attempts: int = Field(default=0, ge=0)
    
    class Config:
        from_attributes = True
