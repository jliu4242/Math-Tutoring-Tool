from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class ProblemCreate(BaseModel):
    source: str = "generated"
    topic: str
    grade_level: str
    difficulty: str = "medium"
    body: str
    solution: str = ""


class Problem(ProblemCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[datetime] = None


class ProblemFilter(BaseModel):
    topic: Optional[str] = None
    grade_level: Optional[str] = None
    difficulty: Optional[str] = None
    source: Optional[str] = None
    search: Optional[str] = None


class LessonPlanCreate(BaseModel):
    topic: str
    grade_level: str
    duration_min: int = 60


class LessonPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    grade_level: str
    duration_min: int
    objectives: str = ""
    warm_up: str = ""
    explanation: str = ""
    examples: str = ""
    practice: str = ""
    assessment: str = ""
    marketing_copy: str = ""
    created_at: Optional[datetime] = None


class GenerateRequest(BaseModel):
    topic: str
    grade_level: str = "grade-9"
    difficulty: str = "medium"
    count: int = 5
    style_reference: Optional[str] = None


class ExtractRequest(BaseModel):
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    extract_solutions: bool = True
    auto_tag: bool = True
    convert_latex: bool = False


class GradeRequest(BaseModel):
    problem_id: str
    student_label: str = "Student A"
    work_input: str


class GradingSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    problem_id: str
    student_label: str
    work_input: str
    diagnosis: dict = {}
    follow_up_ids: list[str] = []
    created_at: Optional[datetime] = None


class MarketingRequest(BaseModel):
    lesson_plan_id: str
