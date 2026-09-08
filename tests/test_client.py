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


async def test_list_courses_rejects_non_list_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    with pytest.raises(TramplinApiError, match="invalid_response"):
        await make_client(handler).list_courses()


async def test_list_courses_unwraps_paginated_envelope() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"slug": "a"}, {"slug": "b"}], "total": 2, "limit": 20, "offset": 0},
        )

    assert await make_client(handler).list_courses() == [{"slug": "a"}, {"slug": "b"}]


async def test_list_tracks_unwraps_paginated_envelope() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"slug": "seti"}], "total": 1, "limit": 20, "offset": 0},
        )

    assert await make_client(handler).list_tracks() == [{"slug": "seti"}]


async def test_get_track_returns_none_on_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found", "message": "нет"})

    assert await make_client(handler).get_track("missing") is None


async def test_create_track_posts_payload_and_returns_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/authoring/tracks"
        return httpx.Response(201, json={"id": "t1", "slug": "seti"})

    result = await make_client(handler).create_track({"title": "Сети", "slug": "seti"})
    assert result == {"id": "t1", "slug": "seti"}


async def test_attach_course_to_track_puts_to_expected_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/authoring/tracks/t1/courses/c1"
        return httpx.Response(204)

    await make_client(handler).attach_course_to_track("t1", "c1")


async def test_reorder_track_courses_puts_ordered_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/authoring/tracks/t1/courses/order"
        assert request.content == b'{"course_ids":["c2","c1"]}'
        return httpx.Response(204)

    await make_client(handler).reorder_track_courses("t1", ["c2", "c1"])


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
