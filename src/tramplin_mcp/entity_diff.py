from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tramplin_mcp.models import Change, ChangeKind


def diff_fields(
    kind: ChangeKind,
    path: str,
    desired: object,
    current: dict[str, Any],
    fields: tuple[str, ...],
    entity_id: str,
) -> Change:
    lookup = desired.get if isinstance(desired, dict) else lambda field: getattr(desired, field)
    changed = [field for field in fields if to_plain(lookup(field)) != current.get(field)]
    return Change(
        action="update" if changed else "unchanged",
        kind=kind,
        path=path,
        entity_id=entity_id,
        fields=changed,
    )


def to_plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    return value
