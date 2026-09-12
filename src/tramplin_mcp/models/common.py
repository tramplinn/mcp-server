from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Slug = str
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_SLUG_DOC = "Lowercase, hyphen-separated identifier (e.g. 'intro-to-loops'); also used in URLs."


class McpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ChangeKind = Literal[
    "course",
    "module",
    "lesson",
    "quiz",
    "question",
    "order",
    "practice",
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


class ValidationIssue(McpModel):
    severity: Literal["error", "warning"] = Field(
        description="'error' blocks apply_course_plan; 'warning' does not."
    )
    path: str = Field(description="Human-readable location, e.g. 'python/basics/intro'.")
    message: str = Field(description="Description of the issue.")


def _ensure_unique(values: list[str], label: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {', '.join(duplicates)}")
