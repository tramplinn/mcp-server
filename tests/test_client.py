from __future__ import annotations

from typing import Any

import httpx
import pytest

from tramplin_mcp.client import TramplinApiError, TramplinClient


def make_client(handler: Any, *, token: str = "tok") -> TramplinClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url="http://test", transport=transport)
    return TramplinClient("http://test", token, 5.0, http=http)


async def test_request_returns_parsed_json_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"ok": True})

    result = await make_client(handler).request("GET", "/x")
    assert result == {"ok": True}


async def test_request_returns_none_on_empty_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    assert await make_client(handler).request("GET", "/x") is None


async def test_request_omits_authorization_header_without_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json={})

    await make_client(handler, token="").request("GET", "/x")


async def test_error_response_includes_details_in_message() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "code": "validation_error",
                "message": "Некорректные данные запроса",
                "details": {"fields": [{"loc": "slug", "message": "bad"}]},
            },
        )

    with pytest.raises(TramplinApiError) as exc_info:
        await make_client(handler).request("GET", "/x")
    error = exc_info.value
    assert error.status_code == 422
    assert error.code == "validation_error"
    assert error.details == {"fields": [{"loc": "slug", "message": "bad"}]}
    assert "fields" in str(error)
    assert "slug" in str(error)


async def test_error_response_without_details_omits_separator() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found", "message": "нет"})

    with pytest.raises(TramplinApiError) as exc_info:
        await make_client(handler).request("GET", "/x")
    assert str(exc_info.value) == "Tramplin API error 404 (not_found): нет"


async def test_error_response_with_non_json_body_uses_defaults() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(TramplinApiError) as exc_info:
        await make_client(handler).request("GET", "/x")
    assert exc_info.value.code == "http_error"


async def test_transport_error_wraps_httpx_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(TramplinApiError) as exc_info:
        await make_client(handler).request("GET", "/x")
    assert exc_info.value.code == "transport_error"


async def test_get_course_returns_none_on_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found", "message": "нет"})

    assert await make_client(handler).get_course("missing") is None


async def test_index_rejects_non_object_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    with pytest.raises(TramplinApiError, match="invalid_response"):
        await make_client(handler).index_courses()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("index_courses", "/authoring/courses/index"),
        ("index_tracks", "/authoring/tracks/index"),
        ("index_problems", "/authoring/algorithms/problems/index"),
    ],
)
async def test_indexes_get_expected_paths(method: str, path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("GET", path)
        return httpx.Response(200, json={"items": [], "total": 0})

    assert await getattr(make_client(handler), method)() == {"items": [], "total": 0}


async def test_get_track_returns_none_on_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found", "message": "нет"})

    assert await make_client(handler).get_track("missing") is None


async def test_get_problem_by_slug_returns_none_on_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found", "message": "нет"})

    assert await make_client(handler).get_problem_by_slug("missing") is None


@pytest.mark.parametrize(
    ("method", "action", "path"),
    [
        ("course_plan", "preview", "/authoring/course-plans/preview"),
        ("course_plan", "apply", "/authoring/course-plans/apply"),
        ("practice_set_plan", "apply", "/authoring/course-plans/practice-set/apply"),
        ("track_plan", "preview", "/authoring/track-plans/preview"),
        ("algorithm_plan", "apply", "/authoring/algorithm-plans/apply"),
    ],
)
async def test_plans_post_payload_to_expected_path(method: str, action: str, path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("POST", path)
        assert request.content == b'{"slug":"x"}'
        return httpx.Response(200, json={"valid": True})

    result = await getattr(make_client(handler), method)(action, {"slug": "x"})
    assert result == {"valid": True}


async def test_algorithm_plan_can_request_template_validation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["validate_templates"] == "true"
        return httpx.Response(200, json={"valid": True})

    await make_client(handler).algorithm_plan("apply", {}, validate_templates=True)


async def test_invalid_plan_error_carries_issues() -> None:
    issue = {"severity": "error", "path": "c", "code": "unknown_problem", "message": "нет"}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"code": "invalid_plan", "message": "ошибки", "details": {"issues": [issue]}},
        )

    with pytest.raises(TramplinApiError, match="unknown_problem") as exc_info:
        await make_client(handler).course_plan("apply", {})
    assert exc_info.value.code == "invalid_plan"


async def test_with_token_shares_http_client_but_not_ownership() -> None:
    seen_tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_tokens.append(request.headers.get("authorization"))
        return httpx.Response(200, json={})

    base = make_client(handler, token="base-token")
    scoped = base.with_token("scoped-token")

    await base.request("GET", "/x")
    await scoped.request("GET", "/x")

    assert seen_tokens == ["Bearer base-token", "Bearer scoped-token"]
    assert scoped._http is base._http
