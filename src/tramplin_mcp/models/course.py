from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from tramplin_mcp.models.common import (
    _SLUG_DOC,
    SLUG_PATTERN,
    Change,
    McpModel,
    Slug,
    ValidationIssue,
    _ensure_unique,
)
from tramplin_mcp.models.questions import QuizPlan


class LessonPlan(McpModel):
    title: str = Field(min_length=1, max_length=200, description="Lesson title shown to students.")
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120, description=_SLUG_DOC)
    body_md: str = Field(
        default="", description="Lesson content as Markdown; this is the source of truth."
    )
    est_minutes: int | None = Field(
        default=None,
        ge=1,
        le=32767,
        description="Estimated time to complete the lesson, in minutes.",
    )


class PracticeSetPlan(McpModel):
    """The desired state of one practice set (a curated list of algorithm-bank problems)
    within a module. Practice sets have no slug in Tramplin, so `title` is the matching
    key across applies — keep it stable to update the same set instead of creating a new one."""

    title: str = Field(
        min_length=1, max_length=200, description="Practice set title shown to students."
    )
    description: str = Field(
        default="", description="Short description shown above the practice set."
    )
    mode: Literal["practice", "mock_interview"] = Field(
        default="practice",
        description="'practice' for open practice; 'mock_interview' for a timed simulation.",
    )
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=480,
        description="Time limit in minutes; required once a mock_interview set is published.",
    )
    problem_slugs: list[Slug] = Field(
        default_factory=list,
        description=(
            "Slugs of problems from the algorithm bank (see list_problems/apply_algorithm_plan), "
            "in the order they should appear. Problems already in the set but absent here are kept."
        ),
    )


class ModulePlan(McpModel):
    title: str = Field(min_length=1, max_length=200, description="Module title shown to students.")
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120, description=_SLUG_DOC)
    summary: str | None = Field(default=None, description="Short description of the module.")
    lessons: list[LessonPlan] = Field(
        default_factory=list, description="Lessons to create or update."
    )
    quizzes: list[QuizPlan] = Field(
        default_factory=list, description="Quizzes to create or update."
    )
    practice_sets: list[PracticeSetPlan] = Field(
        default_factory=list, description="Practice sets to create or update."
    )
    content_order: list[str] = Field(
        default_factory=list,
        description=(
            "Lesson slugs, quiz slugs, and practice set titles from this module, in the order "
            "they should appear. Must list every one exactly once; leave empty to keep the "
            "order given above."
        ),
    )

    @model_validator(mode="after")
    def unique_lesson_slugs(self) -> Self:
        _ensure_unique([lesson.slug for lesson in self.lessons], "lesson slug")
        _ensure_unique([quiz.slug for quiz in self.quizzes], "quiz slug")
        _ensure_unique([practice.title for practice in self.practice_sets], "practice set title")
        all_slugs = (
            [lesson.slug for lesson in self.lessons]
            + [quiz.slug for quiz in self.quizzes]
            + [practice.title for practice in self.practice_sets]
        )
        if self.content_order and (
            set(self.content_order) != set(all_slugs) or len(self.content_order) != len(all_slugs)
        ):
            raise ValueError(
                "content_order must contain every lesson/quiz slug and practice set title "
                "exactly once"
            )
        return self


class CoursePlan(McpModel):
    """The complete desired state of a course. Applying a plan is idempotent and
    additive-only: existing modules/lessons/quizzes not mentioned in the plan are kept."""

    title: str = Field(min_length=1, max_length=200, description="Course title shown to students.")
    slug: Slug = Field(
        pattern=SLUG_PATTERN,
        max_length=120,
        description=(f"{_SLUG_DOC} An existing course with this slug is updated, not duplicated."),
    )
    summary: str | None = Field(default=None, description="Short description of the course.")
    color: str | None = Field(
        default=None,
        max_length=16,
        description="Accent color for the course card, e.g. a hex code like '#3572a5'.",
    )
    est_hours: int | None = Field(
        default=None, ge=1, le=32767, description="Estimated time to complete the course, in hours."
    )
    modules: list[ModulePlan] = Field(
        default_factory=list, description="Modules to create or update, in display order."
    )

    @model_validator(mode="after")
    def unique_module_slugs(self) -> Self:
        _ensure_unique([module.slug for module in self.modules], "module slug")
        return self


class CoursePlanPreview(McpModel):
    course_slug: str
    changes: list[Change] = Field(
        description="Every create/update/unchanged change the plan would make."
    )
    creates: int = Field(description="Number of new entities the plan would create.")
    updates: int = Field(description="Number of existing entities the plan would modify.")
    unchanged: int = Field(description="Number of existing entities the plan leaves untouched.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking notes about applying this plan."
    )


class ApplyResult(McpModel):
    course_slug: str
    completed: bool = Field(description="Whether the plan was applied successfully.")
    changes: list[Change] = Field(description="Every create/update/unchanged change that was made.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking notes about what was applied."
    )


class CoursePlanValidation(McpModel):
    valid: bool = Field(description="True when there are no 'error'-severity issues.")
    issues: list[ValidationIssue] = Field(default_factory=list)
