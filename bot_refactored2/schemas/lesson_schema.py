"""Lesson-related Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class QuizQuestionSchema(BaseModel):
    """Quiz question schema."""
    question: str
    options: List[str] = Field(..., min_items=2, max_items=4)
    correct_answer: str
    explanation: Optional[str] = None
    
    class Config:
        from_attributes = True


class LessonSchema(BaseModel):
    """Lesson content schema."""
    lesson_id: str
    course_id: str
    title: str
    content: str
    lesson_number: int = Field(..., ge=1)
    difficulty: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    xp_reward: int = Field(default=100, ge=0)
    estimated_time_minutes: int = Field(default=10, ge=1)
    quiz: Optional[List[QuizQuestionSchema]] = None
    
    class Config:
        from_attributes = True


class LessonProgressSchema(BaseModel):
    """Lesson progress tracking."""
    user_id: int
    lesson_id: str
    course_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    is_completed: bool = Field(default=False)
    quiz_passed: Optional[bool] = None
    attempts: int = Field(default=0, ge=0)
    
    class Config:
        from_attributes = True
