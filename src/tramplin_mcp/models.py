from __future__ import annotations

from collections import Counter
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = str
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_SLUG_DOC = "Lowercase, hyphen-separated identifier (e.g. 'intro-to-loops'); also used in URLs."


class McpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class PlainOption(McpModel):
    """A choice offered to the student in a single/multiple-choice question."""

    id: str = Field(description="Stable id for this choice; referenced from `answer`.")
    label: str = Field(min_length=1, description="Text of this choice, shown to the student.")


class MatchingOption(McpModel):
    """One side of a matching question: every option is a 'left' or a 'right' item."""

    id: str = Field(description="Stable id for this option; referenced from `answer.pairs`.")
    label: str = Field(min_length=1, description="Text of this option, shown to the student.")
    kind: Literal["left", "right"] = Field(
        description=(
            "Which column this option is in. Students draw a line from each 'left' to one 'right'."
        )
    )


class GroupingOption(McpModel):
    """One entry of a grouping question: an option is a sortable 'item' or a target 'group'."""

    id: str = Field(description="Stable id for this option; referenced from `answer.groups`.")
    label: str = Field(min_length=1, description="Text of this option, shown to the student.")
    kind: Literal["item", "group"] = Field(
        description="Whether this is a sortable 'item' or the 'group' items get dropped into."
    )


class SingleAnswer(McpModel):
    value: str = Field(description="id (from `options`) of the one correct choice.")


class MultipleAnswer(McpModel):
    values: list[str] = Field(description="ids (from `options`) of every correct choice.")


class TextAnswer(McpModel):
    accepted: list[str] = Field(
        min_length=1,
        description=(
            "Exact-match strings that count as correct; the student's answer must equal one."
        ),
    )


class FileAnswer(McpModel):
    """File-upload questions have no answer key: a teacher grades the submission by hand."""


class MatchingAnswer(McpModel):
    pairs: dict[str, str] = Field(
        min_length=1,
        description="Maps every 'left' option id (from `options`) to its matching 'right' id.",
    )


class GroupingAnswer(McpModel):
    groups: dict[str, str] = Field(
        min_length=1,
        description="Maps every 'item' option id (from `options`) to the 'group' id it belongs in.",
    )


class QuestionPlanBase(McpModel):
    position: int = Field(ge=0, description="0-based order of this question within the quiz.")
    prompt_md: str = Field(min_length=1, description="Question text, rendered as Markdown.")
    explain_md: str | None = Field(
        default=None,
        description="Optional Markdown shown after answering, explaining the correct answer.",
    )
    attachment_ids: list[str] = Field(
        default_factory=list,
        description="ids of library assets to attach to this question, e.g. an image.",
    )


class SingleQuestionPlan(QuestionPlanBase):
    """Exactly one correct choice out of several options."""

    type: Literal["single"]
    options: list[PlainOption] = Field(description="The choices offered to the student.")
    answer: SingleAnswer


class MultipleQuestionPlan(QuestionPlanBase):
    """One or more correct choices out of several options."""

    type: Literal["multiple"]
    options: list[PlainOption] = Field(description="The choices offered to the student.")
    answer: MultipleAnswer


class TextQuestionPlan(QuestionPlanBase):
    """A free-text answer, graded by exact match against a set of accepted strings."""

    type: Literal["text"]
    options: list[Any] = Field(
        default_factory=list, description="Unused for this question type; leave empty."
    )
    answer: TextAnswer


class FileQuestionPlan(QuestionPlanBase):
    """The student uploads a file; there is no automatic grading."""

    type: Literal["file"]
    options: list[Any] = Field(
        default_factory=list, description="Unused for this question type; leave empty."
    )
    answer: FileAnswer = Field(
        default_factory=FileAnswer, description="Always empty: file answers are graded manually."
    )


class MatchingQuestionPlan(QuestionPlanBase):
    """The student draws lines connecting each 'left' option to one 'right' option."""

    type: Literal["matching"]
    options: list[MatchingOption] = Field(
        description="Every 'left' and 'right' option to match, combined in one flat list."
    )
    answer: MatchingAnswer


class GroupingQuestionPlan(QuestionPlanBase):
    """The student sorts each 'item' option into one of several 'group' options."""

    type: Literal["grouping"]
    options: list[GroupingOption] = Field(
        description="Every 'item' and 'group' option, combined in one flat list."
    )
    answer: GroupingAnswer


QuestionPlan = Annotated[
    SingleQuestionPlan
    | MultipleQuestionPlan
    | TextQuestionPlan
    | FileQuestionPlan
    | MatchingQuestionPlan
    | GroupingQuestionPlan,
    Field(discriminator="type"),
]


class QuizPlan(McpModel):
    title: str = Field(min_length=1, max_length=200, description="Quiz title shown to students.")
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=120, description=_SLUG_DOC)
    lesson_slug: Slug | None = Field(
        default=None,
        pattern=SLUG_PATTERN,
        max_length=120,
        description="slug of a lesson in this module to attach the quiz to; omit for standalone.",
    )
    questions: list[QuestionPlan] = Field(
        default_factory=list,
        description="Questions in display order; `position` must still be set on each.",
    )

    @model_validator(mode="after")
    def unique_question_positions(self) -> Self:
        _ensure_unique([str(question.position) for question in self.questions], "question position")
        return self


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
    content_order: list[Slug] = Field(
        default_factory=list,
        description=(
            "Lesson and quiz slugs from this module, in the order they should appear. Must "
            "list every slug exactly once; leave empty to keep the order given above."
        ),
    )

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


ChangeKind = Literal[
    "course",
    "module",
    "lesson",
    "quiz",
    "question",
    "order",
    "problem",
    "test_case",
    "template",
]


class Change(McpModel):
    action: Literal["create", "update", "unchanged"] = Field(
        description="What applying the plan would do to this entity."
    )
    kind: ChangeKind = Field(description="Type of entity this change applies to.")
    path: str = Field(description="Human-readable location, e.g. 'python/basics/intro'.")
    entity_id: str | None = Field(
        default=None, description="id of the existing entity, if it already exists."
    )
    fields: list[str] = Field(
        default_factory=list,
        description="Which fields would change; empty when action is 'create' or 'unchanged'.",
    )


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


class ValidationIssue(McpModel):
    severity: Literal["error", "warning"] = Field(
        description="'error' blocks apply_course_plan; 'warning' does not."
    )
    path: str = Field(description="Human-readable location, e.g. 'python/basics/intro'.")
    message: str = Field(description="Description of the issue.")


class CoursePlanValidation(McpModel):
    valid: bool = Field(description="True when there are no 'error'-severity issues.")
    issues: list[ValidationIssue] = Field(default_factory=list)


class TestCasePlan(McpModel):
    position: int = Field(ge=0, description="0-based order among this problem's test cases.")
    input: str = Field(default="", description="stdin fed to the solution.")
    expected_output: str = Field(description="Expected stdout, compared exactly.")
    is_sample: bool = Field(
        default=False, description="Whether this case is shown to students as an example."
    )
    weight: int = Field(default=1, ge=1, le=100, description="Relative weight when scoring.")


class TemplatePlan(McpModel):
    language: str = Field(
        pattern=r"^(python|javascript|typescript|cpp|java|csharp|go|kotlin)$",
        description="Programming language key this template applies to.",
    )
    starter_code: str = Field(default="", description="Code shown to students before they start.")
    solution_code: str = Field(
        default="",
        description="Reference solution; run through the test cases by validate_template.",
    )


class ProblemPlan(McpModel):
    """The complete desired state of one algorithmic problem, matched by `slug`."""

    slug: Slug = Field(
        pattern=SLUG_PATTERN,
        max_length=120,
        description=(f"{_SLUG_DOC} An existing problem with this slug is updated, not duplicated."),
    )
    provider: Literal["internal", "external"] = Field(
        default="internal",
        description="'internal' problems run on Judge0; 'external' just link out.",
    )
    external_key: str | None = Field(default=None, max_length=200)
    external_url: str | None = Field(
        default=None, description="Required, HTTPS, when provider is 'external'."
    )
    title: str = Field(min_length=1, max_length=200, description="Problem title shown to students.")
    statement_md: str = Field(default="", description="Problem statement as Markdown.")
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str] = Field(default_factory=list, max_length=30)
    time_limit_ms: int = Field(default=1000, ge=50, le=5000)
    memory_limit_kb: int = Field(default=262144, ge=16384, le=524288)
    test_cases: list[TestCasePlan] = Field(
        default_factory=list, description="Test cases to create or update, matched by `position`."
    )
    templates: list[TemplatePlan] = Field(
        default_factory=list,
        description="Per-language starter/solution code, matched by `language`.",
    )

    @model_validator(mode="after")
    def unique_test_case_positions(self) -> Self:
        _ensure_unique([str(case.position) for case in self.test_cases], "test case position")
        _ensure_unique([template.language for template in self.templates], "template language")
        return self


class AlgorithmPlan(McpModel):
    """The complete desired state of a flat bank of problems. Applying a plan is
    idempotent and additive-only: existing problems not mentioned in the plan are kept,
    and test cases/templates on a mentioned problem but absent from its plan are kept too."""

    problems: list[ProblemPlan] = Field(
        default_factory=list, description="Problems to create or update."
    )

    @model_validator(mode="after")
    def unique_problem_slugs(self) -> Self:
        _ensure_unique([problem.slug for problem in self.problems], "problem slug")
        return self


class AlgorithmPlanPreview(McpModel):
    changes: list[Change] = Field(
        description="Every create/update/unchanged change the plan would make."
    )
    creates: int = Field(description="Number of new entities the plan would create.")
    updates: int = Field(description="Number of existing entities the plan would modify.")
    unchanged: int = Field(description="Number of existing entities the plan leaves untouched.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking notes about applying this plan."
    )


class AlgorithmPlanApplyResult(McpModel):
    completed: bool = Field(description="Whether the plan was applied successfully.")
    changes: list[Change] = Field(description="Every create/update/unchanged change that was made.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking notes about what was applied."
    )


class AlgorithmPlanValidation(McpModel):
    valid: bool = Field(description="True when there are no 'error'-severity issues.")
    issues: list[ValidationIssue] = Field(default_factory=list)


def _ensure_unique(values: list[str], label: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {', '.join(duplicates)}")
