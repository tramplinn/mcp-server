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
        description="'internal' problems run on Piston; 'external' just link out.",
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
