"""MCP-инструменты через in-memory клиент FastMCP; backend подменён httpx.MockTransport.

Сервер — тонкий прокси: проверяем, какой токен уходит в backend, какие пути и тела
запросов получаются из аргументов инструментов и как ответ упаковывается для агента.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tramplin_mcp import server
from tramplin_mcp.client import TramplinClient

type Route = tuple[str, str]


@dataclass
class FakeBackend:
    """Ответы по (METHOD, path с query); всё, чего нет в routes, — 404."""

    routes: dict[Route, Any] = field(default_factory=dict)
    errors: dict[Route, tuple[int, dict[str, Any]]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.raw_path.decode())
        if key in self.errors:
            status, payload = self.errors[key]
            return httpx.Response(status, json=payload)
        if key not in self.routes:
            return httpx.Response(404, json={"code": "not_found", "message": "Не найдено"})
        body = self.routes[key]
        return httpx.Response(204) if body is None else httpx.Response(200, json=body)

    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
async def mcp_client(
    backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    def make_client(_: str, token: str, timeout: float) -> TramplinClient:
        transport = httpx.MockTransport(backend.handle)
        http = httpx.AsyncClient(base_url="http://test", transport=transport)
        return TramplinClient("http://test", token, timeout, http=http)

    monkeypatch.setattr(server, "TramplinClient", make_client)
    monkeypatch.setattr(server.settings, "api_token", "local-token")
    async with Client(server.mcp) as client:
        yield client


async def call(client: Client[Any], tool: str, **arguments: Any) -> Any:
    return (await client.call_tool(tool, arguments)).structured_content


# --- Токен ----------------------------------------------------------------------

INDEX = {"items": [{"id": "1", "slug": "algo", "title": "Алгоритмы", "status": "draft"}]}


async def test_stdio_mode_uses_configured_token(
    mcp_client: Client[Any], backend: FakeBackend
) -> None:
    backend.routes[("GET", "/authoring/courses/index")] = {**INDEX, "total": 1}

    await call(mcp_client, "list_courses")

    assert backend.last().headers["authorization"] == "Bearer local-token"


async def test_oauth_token_takes_precedence(
    mcp_client: Client[Any], backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend.routes[("GET", "/authoring/courses/index")] = {**INDEX, "total": 1}
    monkeypatch.setattr(server, "get_access_token", lambda: SimpleNamespace(token="user-token"))

    await call(mcp_client, "list_courses")

    assert backend.last().headers["authorization"] == "Bearer user-token"


async def test_stdio_mode_without_token_fails(
    mcp_client: Client[Any], backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server.settings, "api_token", "")

    with pytest.raises(ToolError, match="TRAMPLIN_API_TOKEN"):
        await mcp_client.call_tool("list_courses", {})
    assert backend.requests == []


# --- Чтение ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "path", "extra"),
    [
        ("list_courses", "/authoring/courses/index", {}),
        ("list_tracks", "/authoring/tracks/index", {}),
        ("list_problems", "/authoring/algorithms/problems/index", {"difficulty": "easy"}),
    ],
)
async def test_index_tools(
    mcp_client: Client[Any], backend: FakeBackend, tool: str, path: str, extra: dict[str, Any]
) -> None:
    item = {"id": "1", "slug": "x", "title": "X", "status": "published", **extra}
    backend.routes[("GET", path)] = {"items": [item], "total": 1, "ignored": True}

    result = await call(mcp_client, tool)

    assert result == {"items": [{"difficulty": None, **item}], "total": 1}


async def test_inspect_course_strips_rendered_html(
    mcp_client: Client[Any], backend: FakeBackend
) -> None:
    backend.routes[("GET", "/authoring/courses/algo")] = {
        "slug": "algo",
        "modules": [{"lessons": [{"body_md": "# A", "body_html": "<h1>A</h1>"}]}],
    }

    result = await call(mcp_client, "inspect_course", slug="algo")

    assert result == {
        "found": True,
        "course": {"slug": "algo", "modules": [{"lessons": [{"body_md": "# A"}]}]},
    }


@pytest.mark.parametrize("tool", ["inspect_course", "inspect_track", "inspect_problem"])
async def test_inspect_missing_entity(mcp_client: Client[Any], tool: str) -> None:
    assert await call(mcp_client, tool, slug="nope") == {"found": False, "slug": "nope"}


async def test_inspect_track(mcp_client: Client[Any], backend: FakeBackend) -> None:
    backend.routes[("GET", "/authoring/tracks/backend")] = {"slug": "backend", "courses": []}

    assert await call(mcp_client, "inspect_track", slug="backend") == {
        "found": True,
        "track": {"slug": "backend", "courses": []},
    }


async def test_inspect_problem(mcp_client: Client[Any], backend: FakeBackend) -> None:
    backend.routes[("GET", "/authoring/algorithms/problems/slug/two-sum")] = {"slug": "two-sum"}

    assert await call(mcp_client, "inspect_problem", slug="two-sum") == {
        "found": True,
        "problem": {"slug": "two-sum"},
    }


async def test_inspect_lesson_strips_rendered_html(
    mcp_client: Client[Any], backend: FakeBackend
) -> None:
    backend.routes[("GET", "/authoring/lessons/l1")] = {
        "id": "l1",
        "body_md": "text",
        "body_html": "<p>text</p>",
    }

    assert await call(mcp_client, "inspect_lesson", lesson_id="l1") == {
        "id": "l1",
        "body_md": "text",
    }


async def test_inspect_lesson_surfaces_api_error(mcp_client: Client[Any]) -> None:
    with pytest.raises(ToolError, match="404"):
        await mcp_client.call_tool("inspect_lesson", {"lesson_id": "missing"})


async def test_preview_markdown_posts_body(mcp_client: Client[Any], backend: FakeBackend) -> None:
    backend.routes[("POST", "/authoring/markdown/preview")] = {"html": "<p>x</p>", "cards": []}

    result = await call(mcp_client, "preview_markdown", body_md="x")

    assert result == {"html": "<p>x</p>", "cards": []}
    assert json.loads(backend.last().content) == {"body_md": "x"}


# --- Планы ----------------------------------------------------------------------

REPORT = {"valid": True, "created": 1, "updated": 0, "unchanged": 0}
COURSE_PLAN = {"title": "Алгоритмы", "slug": "algo"}
PRACTICE_SET = {"title": "Разминка"}
TRACK_PLAN = {"title": "Backend", "slug": "backend", "course_slugs": ["algo"]}
ALGORITHM_PLAN: dict[str, Any] = {"problems": []}
PRACTICE_ARGS = {"course_slug": "algo", "module_slug": "hashes", "practice_set": PRACTICE_SET}


@pytest.mark.parametrize("action", ["preview", "apply"])
@pytest.mark.parametrize(
    ("tool", "arguments", "path", "report"),
    [
        (
            "course_plan",
            {"plan": COURSE_PLAN},
            "/authoring/course-plans",
            {"course_slug": "algo"},
        ),
        (
            "practice_set_plan",
            PRACTICE_ARGS,
            "/authoring/course-plans/practice-set",
            {"course_slug": "algo", "module_slug": "hashes"},
        ),
        (
            "track_plan",
            {"plan": TRACK_PLAN},
            "/authoring/track-plans",
            {"track_slug": "backend"},
        ),
        ("algorithm_plan", {"plan": ALGORITHM_PLAN}, "/authoring/algorithm-plans", {}),
    ],
)
async def test_plan_tools_forward_to_backend(
    mcp_client: Client[Any],
    backend: FakeBackend,
    action: str,
    tool: str,
    arguments: dict[str, Any],
    path: str,
    report: dict[str, Any],
) -> None:
    backend.routes[("POST", f"{path}/{action}")] = {**REPORT, **report, "extra": "ignored"}

    result = await call(mcp_client, f"{action}_{tool}", **arguments)

    assert result is not None
    assert {key: result[key] for key in {**REPORT, **report}} == {**REPORT, **report}
    assert "extra" not in result
    sent = json.loads(backend.last().content)
    if tool == "practice_set_plan":
        assert sent["course_slug"] == "algo"
        assert sent["module_slug"] == "hashes"
        assert sent["practice_set"]["title"] == "Разминка"
    else:
        assert {key: sent[key] for key in arguments["plan"]} == arguments["plan"]


async def test_apply_algorithm_plan_can_validate_templates(
    mcp_client: Client[Any], backend: FakeBackend
) -> None:
    backend.routes[("POST", "/authoring/algorithm-plans/apply?validate_templates=true")] = {
        **REPORT,
        "template_validations": [],
    }

    result = await call(
        mcp_client, "apply_algorithm_plan", plan=ALGORITHM_PLAN, validate_templates=True
    )

    assert result is not None
    assert result["valid"] is True


async def test_invalid_plan_never_reaches_backend(
    mcp_client: Client[Any], backend: FakeBackend
) -> None:
    with pytest.raises(ToolError):
        await mcp_client.call_tool("preview_course_plan", {"plan": {"title": "x", "slug": "Bad"}})
    assert backend.requests == []


async def test_backend_rejection_surfaces_as_tool_error(
    mcp_client: Client[Any], backend: FakeBackend
) -> None:
    backend.errors[("POST", "/authoring/course-plans/apply")] = (
        422,
        {"code": "invalid_plan", "message": "План содержит ошибки"},
    )

    with pytest.raises(ToolError, match="invalid_plan"):
        await mcp_client.call_tool("apply_course_plan", {"plan": COURSE_PLAN})


async def test_server_exposes_every_tool(mcp_client: Client[Any]) -> None:
    tools = {tool.name: tool for tool in await mcp_client.list_tools()}

    assert set(tools) == {
        "list_courses",
        "inspect_course",
        "inspect_lesson",
        "preview_markdown",
        "preview_course_plan",
        "apply_course_plan",
        "preview_practice_set_plan",
        "apply_practice_set_plan",
        "list_tracks",
        "inspect_track",
        "preview_track_plan",
        "apply_track_plan",
        "list_problems",
        "inspect_problem",
        "preview_algorithm_plan",
        "apply_algorithm_plan",
    }
    for name, tool in tools.items():
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is not name.startswith("apply_"), name


# --- HTTP и запуск --------------------------------------------------------------


async def test_health_route() -> None:
    transport = httpx.ASGITransport(app=server.mcp.http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    return calls


def test_main_runs_stdio(monkeypatch: pytest.MonkeyPatch, runs: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(server.settings, "transport", "stdio")

    server.main()

    assert runs == [{"transport": "stdio"}]


def test_main_runs_http_with_auth(
    monkeypatch: pytest.MonkeyPatch, runs: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(server.settings, "transport", "http")
    monkeypatch.setattr(server, "auth", object())

    server.main()

    assert runs == [
        {
            "transport": "http",
            "host": server.settings.host,
            "port": server.settings.port,
            "stateless_http": True,
        }
    ]


def test_main_http_requires_oauth(
    monkeypatch: pytest.MonkeyPatch, runs: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(server.settings, "transport", "http")
    monkeypatch.setattr(server, "auth", None)

    with pytest.raises(ValueError, match="OAuth"):
        server.main()
    assert runs == []


def test_main_rejects_unknown_transport(
    monkeypatch: pytest.MonkeyPatch, runs: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(server.settings, "transport", "sse")

    with pytest.raises(ValueError, match="stdio or http"):
        server.main()
    assert runs == []
