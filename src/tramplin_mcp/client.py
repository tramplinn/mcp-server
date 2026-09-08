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
        if isinstance(result, dict) and isinstance(result.get("items"), list):
            result = result["items"]
        if not isinstance(result, list):
            raise TramplinApiError(0, "invalid_response", "Expected a course list")
        return cast(list[dict[str, Any]], result)

    async def apply_course_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", "/authoring/course-plans/apply", json=payload)
        return _object(result, "course plan result")

    async def get_course(self, slug: str) -> dict[str, Any] | None:
        try:
            result = await self.request("GET", f"/authoring/courses/{slug}")
        except TramplinApiError as exc:
            if exc.status_code == 404:
                return None
            raise
        if not isinstance(result, dict):
            raise TramplinApiError(0, "invalid_response", "Expected a course object")
        return result

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


def _object(result: ApiResponse, label: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TramplinApiError(0, "invalid_response", f"Expected a {label} object")
    return result
