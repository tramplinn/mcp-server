from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from tramplin_mcp.models.common import _SLUG_DOC, SLUG_PATTERN, McpModel, Slug


class PlainOption(McpModel):
    """A choice offered to the student in a single/multiple-choice question."""

    value: str = Field(description="Stable value for this choice; referenced from `answer`.")
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
    value: str = Field(description="value (from `options`) of the one correct choice.")


class MultipleAnswer(McpModel):
    values: list[str] = Field(description="values (from `options`) of every correct choice.")


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
        description=(
            "Questions in display order. Matched to existing questions by `position`, which "
            "must be unique within the quiz."
        ),
    )
