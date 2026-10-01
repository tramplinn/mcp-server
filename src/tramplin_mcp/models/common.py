from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Slug = str
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_SLUG_DOC = "Lowercase, hyphen-separated identifier (e.g. 'intro-to-loops'); also used in URLs."


class McpModel(BaseModel):
    """Plan input: unknown fields are rejected so typos surface instead of being ignored."""

    model_config = ConfigDict(extra="forbid")


class McpOutput(BaseModel):
    """Backend response: new backend fields must not break the server."""

    model_config = ConfigDict(extra="ignore")


class Change(McpOutput):
    action: Literal["create", "update", "unchanged"] = Field(
        description="What the plan does (preview) or did (apply) to this entity."
    )
    kind: str = Field(
        description=(
            "Entity type: course, module, lesson, quiz, question, practice, problem, test_case, "
            "template, track or track_course."
        )
    )
    path: str = Field(description="Human-readable location, e.g. 'python/basics/intro'.")
    entity_id: str | None = Field(
        default=None,
        description=(
            "Entity id. After apply it is the real id (e.g. pass a lesson id to inspect_lesson); "
            "for creates in a preview it is only provisional."
        ),
    )
    fields: list[str] = Field(
        default_factory=list,
        description=(
            "Changed fields; empty for create/unchanged. Besides entity fields it may contain "
            "'content_order', 'problem_slugs', 'course_order' or 'tags'."
        ),
    )


class Issue(McpOutput):
    severity: Literal["error", "warning"] = Field(
        description="'error' makes apply reject the whole plan; 'warning' does not block it."
    )
    path: str = Field(description="Where in the plan the issue is, e.g. 'python/basics/intro'.")
    code: str = Field(
        description="Stable machine-readable code, e.g. 'unknown_problem' or 'invalid_markdown'."
    )
    message: str = Field(description="Explanation of the issue (in Russian).")


class PlanReport(McpOutput):
    valid: bool = Field(description="False when any issue has severity 'error'.")
    created: int = Field(description="Entities created (or that would be created).")
    updated: int = Field(description="Existing entities modified (or that would be).")
    unchanged: int = Field(description="Existing entities the plan leaves as they are.")
    changes: list[Change] = Field(
        default_factory=list,
        description="Exact per-entity diff; empty in a preview when the plan has errors.",
    )
    issues: list[Issue] = Field(default_factory=list, description="Validation findings.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Notes to relay to the user, e.g. a published entity becoming a draft.",
    )


class IndexItem(McpOutput):
    id: str
    slug: str
    title: str
    status: str = Field(
        description="'draft' or 'published'. Only an author in the Tramplin UI can publish."
    )
    difficulty: str | None = Field(default=None, description="Problems only: easy/medium/hard.")


class Index(McpOutput):
    items: list[IndexItem] = Field(description="Every entity, including drafts; not paginated.")
    total: int
