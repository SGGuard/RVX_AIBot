"""User-related Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class UserSchema(BaseModel):
    """User profile schema."""
    user_id: int = Field(..., description="Telegram user ID")
    username: str = Field(default="", description="Telegram username")
    first_name: str = Field(default="", description="User first name")
    is_banned: bool = Field(default=False, description="Ban status")
    ban_reason: Optional[str] = Field(default=None, description="Ban reason")
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        from_attributes = True


class UserStatsSchema(BaseModel):
    """User statistics schema."""
    user_id: int
    xp: int = Field(default=0, ge=0)
    level: int = Field(default=1, ge=1, le=50)
    courses_completed: int = Field(default=0, ge=0)
    tests_passed: int = Field(default=0, ge=0)
    badges_count: int = Field(default=0, ge=0)
    daily_requests_used: int = Field(default=0, ge=0)
    last_request_at: Optional[datetime] = None
    
    @field_validator('xp', 'level', 'courses_completed', 'tests_passed', 'badges_count')
    @classmethod
    def validate_non_negative(cls, v):
        if v < 0:
            raise ValueError('Value must be non-negative')
        return v
    
    class Config:
        from_attributes = True


class UserProgressSchema(BaseModel):
    """User progress in courses."""
    user_id: int
    course_id: str
    current_lesson: int = Field(default=0, ge=0)
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    completed: bool = Field(default=False)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
