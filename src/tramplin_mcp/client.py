from __future__ import annotations

from typing import Any, cast

import httpx

type ApiResponse = dict[str, Any] | list[Any] | None


class TramplinApiError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, details: object = None) -> None:
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(f"Tramplin API error {status_code} ({code}): {message}")


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
        if not isinstance(result, list):
            raise TramplinApiError(0, "invalid_response", "Expected a course list")
        return cast(list[dict[str, Any]], result)

    async def exchange_mcp_identity(
        self, provider: str, provider_id: str, service_secret: str
    ) -> str:
        try:
            response = await self._http.post(
                "/auth/mcp/exchange",
                json={"provider": provider, "provider_id": provider_id},
                headers={"X-MCP-Service-Secret": service_secret},
            )
        except httpx.HTTPError as exc:
            raise TramplinApiError(0, "transport_error", str(exc)) from exc
        if not response.is_success:
            raise TramplinApiError(
                response.status_code, "oauth_exchange_failed", "Tramplin rejected OAuth identity"
            )
        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str):
            raise TramplinApiError(0, "invalid_response", "Expected an access token")
        return access_token

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

    async def create_course(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", "/authoring/courses", json=payload)
        return _object(result, "course")

    async def update_course(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("PATCH", f"/authoring/courses/{course_id}", json=payload)
        return _object(result, "course")

    async def create_module(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", f"/authoring/courses/{course_id}/modules", json=payload)
        return _object(result, "module")

    async def update_module(self, module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("PATCH", f"/authoring/modules/{module_id}", json=payload)
        return _object(result, "module")

    async def create_lesson(self, module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", f"/authoring/modules/{module_id}/lessons", json=payload)
        return _object(result, "lesson")

    async def update_lesson(self, lesson_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("PATCH", f"/authoring/lessons/{lesson_id}", json=payload)
        return _object(result, "lesson")

    async def get_quiz(self, quiz_id: str) -> dict[str, Any]:
        result = await self.request("GET", f"/authoring/quizzes/{quiz_id}")
        return _object(result, "quiz")

    async def create_quiz(self, module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", f"/authoring/modules/{module_id}/quizzes", json=payload)
        return _object(result, "quiz")

    async def update_quiz(self, quiz_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("PATCH", f"/authoring/quizzes/{quiz_id}", json=payload)
        return _object(result, "quiz")

    async def create_question(self, quiz_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("POST", f"/authoring/quizzes/{quiz_id}/questions", json=payload)
        return _object(result, "question")

    async def update_question(self, question_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("PATCH", f"/authoring/questions/{question_id}", json=payload)
        return _object(result, "question")

    async def reorder_modules(self, course_id: str, ids: list[str]) -> None:
        await self.request(
            "PUT", f"/authoring/courses/{course_id}/modules/order", json={"ids": ids}
        )

    async def reorder_module_content(self, module_id: str, ids: list[str]) -> None:
        await self.request("PUT", f"/authoring/modules/{module_id}/order", json={"ids": ids})


def _object(result: ApiResponse, label: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TramplinApiError(0, "invalid_response", f"Expected a {label} object")
    return result
