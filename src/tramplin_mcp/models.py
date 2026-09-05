from __future__ import annotations

from collections import Counter
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = str
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class McpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LessonPlan(McpModel):
    title: str = Field(min_length=1, max_length=200)
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120)
    body_md: str = ""
    est_minutes: int | None = Field(default=None, ge=1, le=32767)


class QuestionPlan(McpModel):
    position: int = Field(ge=0)
    prompt_md: str = Field(min_length=1)
    type: Literal["single", "multiple", "text", "matching", "grouping", "file"]
    options: list[Any] = Field(default_factory=list)
    answer: dict[str, Any]
    explain_md: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)


class QuizPlan(McpModel):
    title: str = Field(min_length=1, max_length=200)
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120)
    lesson_slug: Slug | None = Field(default=None, pattern=SLUG_PATTERN, max_length=120)
    questions: list[QuestionPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_question_positions(self) -> Self:
        _ensure_unique([str(question.position) for question in self.questions], "question position")
        return self


class ModulePlan(McpModel):
    title: str = Field(min_length=1, max_length=200)
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120)
    summary: str | None = None
    lessons: list[LessonPlan] = Field(default_factory=list)
    quizzes: list[QuizPlan] = Field(default_factory=list)
    content_order: list[Slug] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_lesson_slugs(self) -> Self:
        _ensure_unique([lesson.slug for lesson in self.lessons], "lesson slug")
        _ensure_unique([quiz.slug for quiz in self.quizzes], "quiz slug")
        all_slugs = [lesson.slug for lesson in self.lessons] + [quiz.slug for quiz in self.quizzes]
        if self.content_order and (
            set(self.content_order) != set(all_slugs) or len(self.content_order) != len(all_slugs)
        ):
            raise ValueError("content_order must contain every lesson and quiz slug exactly once")
        return self


class CoursePlan(McpModel):
    title: str = Field(min_length=1, max_length=200)
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120)
    summary: str | None = None
    color: str | None = Field(default=None, max_length=16)
    est_hours: int | None = Field(default=None, ge=1, le=32767)
    modules: list[ModulePlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_module_slugs(self) -> Self:
        _ensure_unique([module.slug for module in self.modules], "module slug")
        return self


class Change(McpModel):
    action: Literal["create", "update", "unchanged"]
    kind: Literal["course", "module", "lesson", "quiz", "question", "order"]
    path: str
    entity_id: str | None = None
    fields: list[str] = Field(default_factory=list)


class CoursePlanPreview(McpModel):
    course_slug: str
    changes: list[Change]
    creates: int
    updates: int
    unchanged: int
    warnings: list[str] = Field(default_factory=list)


class ApplyResult(McpModel):
    course_slug: str
    completed: bool
    changes: list[Change]
    warnings: list[str] = Field(default_factory=list)


class ValidationIssue(McpModel):
    severity: Literal["error", "warning"]
    path: str
    message: str


class CoursePlanValidation(McpModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


def _ensure_unique(values: list[str], label: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {', '.join(duplicates)}")
