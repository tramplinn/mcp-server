from __future__ import annotations

import json
from typing import Any, cast

import httpx

type ApiResponse = dict[str, Any] | list[Any] | None


class TramplinApiError(RuntimeError):
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

    async def list_courses(self) -> list[dict[str, Any]]:
        result = await self.request("GET", "/authoring/courses")
        return _list(result, "course")

    async def apply_course_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", "/authoring/course-plans/apply", json=payload)
        return _object(result, "course plan result")

    async def get_course(self, slug: str) -> dict[str, Any] | None:
        return await self._get_or_none(f"/authoring/courses/{slug}", "course")

    async def get_lesson(self, lesson_id: str) -> dict[str, Any]:
        result = await self.request("GET", f"/authoring/lessons/{lesson_id}")
        return _object(result, "lesson")

    async def preview_markdown(self, body_md: str) -> dict[str, Any]:
        result = await self.request(
            "POST", "/authoring/markdown/preview", json={"body_md": body_md}
        )
        return _object(result, "Markdown preview")

    async def get_quiz(self, quiz_id: str) -> dict[str, Any]:
        result = await self.request("GET", f"/authoring/quizzes/{quiz_id}")
        return _object(result, "quiz")

    async def get_practice_set(self, set_id: str) -> dict[str, Any]:
        result = await self.request("GET", f"/authoring/practice-sets/{set_id}")
        return _object(result, "practice set")

    async def list_tracks(self) -> list[dict[str, Any]]:
        result = await self.request("GET", "/authoring/tracks")
        return _list(result, "track")

    async def get_track(self, slug: str) -> dict[str, Any] | None:
        return await self._get_or_none(f"/authoring/tracks/{slug}", "track")

    async def create_track(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", "/authoring/tracks", json=payload)
        return _object(result, "track")

    async def attach_course_to_track(self, track_id: str, course_id: str) -> None:
        await self.request("PUT", f"/authoring/tracks/{track_id}/courses/{course_id}")

    async def reorder_track_courses(self, track_id: str, course_ids: list[str]) -> None:
        await self.request(
            "PUT",
            f"/authoring/tracks/{track_id}/courses/order",
            json={"course_ids": course_ids},
        )

    async def list_problems(self) -> list[dict[str, Any]]:
        result = await self.request("GET", "/authoring/algorithms/problems")
        return _list(result, "problem")

    async def get_problem_by_slug(self, slug: str) -> dict[str, Any] | None:
        return await self._get_or_none(f"/authoring/algorithms/problems/slug/{slug}", "problem")

    async def apply_algorithm_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", "/authoring/algorithm-plans/apply", json=payload)
        return _object(result, "algorithm plan result")

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


def _list(result: ApiResponse, label: str) -> list[dict[str, Any]]:
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        result = result["items"]
    if not isinstance(result, list):
        raise TramplinApiError(0, "invalid_response", f"Expected a {label} list")
    return cast(list[dict[str, Any]], result)
