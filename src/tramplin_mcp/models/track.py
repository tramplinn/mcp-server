from __future__ import annotations

from pydantic import Field

from tramplin_mcp.models.common import _SLUG_DOC, SLUG_PATTERN, McpModel, PlanReport, Slug


class TrackPlan(McpModel):
    """The desired state of a track: a titled, ordered group of existing courses.

    Additive-only and idempotent: courses already in the track but missing from
    `course_slugs` stay attached and are moved after the listed ones. A new track is created
    as a draft; the status of an existing track is never changed.
    """

    title: str = Field(min_length=1, max_length=200, description="Track title shown to students.")
    slug: Slug = Field(
        pattern=SLUG_PATTERN,
        max_length=120,
        description=f"{_SLUG_DOC} An existing track with this slug is updated, not duplicated.",
    )
    description: str | None = Field(default=None, description="Short description of the track.")
    color: str | None = Field(
        default=None, max_length=16, description="Accent color, e.g. a hex code like '#3572a5'."
    )
    course_slugs: list[Slug] = Field(
        default_factory=list,
        description=(
            "Slugs of existing courses (see list_courses), in display order. Each must be unique."
        ),
    )


class TrackPlanReport(PlanReport):
    track_slug: str
    track_id: str | None = Field(default=None, description="Set after apply.")
