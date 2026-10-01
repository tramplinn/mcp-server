from __future__ import annotations

import json
from typing import Any, Literal, cast

import httpx
from fastmcp.exceptions import ToolError

type ApiResponse = dict[str, Any] | list[Any] | None
type PlanAction = Literal["preview", "apply"]


class TramplinApiError(ToolError):
    """Shown to the agent verbatim; for invalid_plan the details carry the issues list."""

    def __init__(self, status_code: int, code: str, message: str, details: object = None) -> None:
        self.status_code = status_code
        self.code = code
        self.details = details
        text = f"Tramplin API error {status_code} ({code}): {message}"
        if details:
            text = f"{text} — {json.dumps(details, ensure_ascii=False)}"
        super().__init__(text)


class TramplinClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        headers = {"Accept": "application/json"}
        self._token = token
        self._base_url = base_url
        self._timeout = timeout
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout)

    def with_token(self, token: str) -> TramplinClient:
        return TramplinClient(self._base_url, token, self._timeout, http=self._http)

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> ApiResponse:
        try:
            headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
            response = await self._http.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise TramplinApiError(0, "transport_error", str(exc)) from exc
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return None
            return cast(ApiResponse, response.json())
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        raise TramplinApiError(
            response.status_code,
            str(payload.get("code", "http_error")),
            str(payload.get("message", response.reason_phrase)),
            payload.get("details"),
        )

    async def index_courses(self) -> dict[str, Any]:
        return _object(await self.request("GET", "/authoring/courses/index"), "course index")

    async def get_course(self, slug: str) -> dict[str, Any] | None:
        return await self._get_or_none(f"/authoring/courses/{slug}", "course")

    async def get_lesson(self, lesson_id: str) -> dict[str, Any]:
        return _object(await self.request("GET", f"/authoring/lessons/{lesson_id}"), "lesson")

    async def preview_markdown(self, body_md: str) -> dict[str, Any]:
        result = await self.request(
            "POST", "/authoring/markdown/preview", json={"body_md": body_md}
        )
        return _object(result, "Markdown preview")

    async def course_plan(self, action: PlanAction, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._plan(f"/authoring/course-plans/{action}", payload)

    async def practice_set_plan(
        self, action: PlanAction, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._plan(f"/authoring/course-plans/practice-set/{action}", payload)

    async def index_tracks(self) -> dict[str, Any]:
        return _object(await self.request("GET", "/authoring/tracks/index"), "track index")

    async def get_track(self, slug: str) -> dict[str, Any] | None:
        return await self._get_or_none(f"/authoring/tracks/{slug}", "track")

    async def track_plan(self, action: PlanAction, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._plan(f"/authoring/track-plans/{action}", payload)

    async def index_problems(self) -> dict[str, Any]:
        result = await self.request("GET", "/authoring/algorithms/problems/index")
        return _object(result, "problem index")

    async def get_problem_by_slug(self, slug: str) -> dict[str, Any] | None:
        return await self._get_or_none(f"/authoring/algorithms/problems/slug/{slug}", "problem")

    async def algorithm_plan(
        self,
        action: PlanAction,
        payload: dict[str, Any],
        *,
        validate_templates: bool = False,
    ) -> dict[str, Any]:
        path = f"/authoring/algorithm-plans/{action}"
        if validate_templates:
            path = f"{path}?validate_templates=true"
        return await self._plan(path, payload)

    async def _plan(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return _object(await self.request("POST", path, json=payload), "plan report")

    async def _get_or_none(self, path: str, label: str) -> dict[str, Any] | None:
        try:
            result = await self.request("GET", path)
        except TramplinApiError as exc:
            if exc.status_code == 404:
                return None
            raise
        return _object(result, label)


def _object(result: ApiResponse, label: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TramplinApiError(0, "invalid_response", f"Expected a {label} object")
    return result
