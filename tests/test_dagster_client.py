"""Unit tests for the Dagster GraphQL client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from d4bl.services.dagster_client import (
    LAUNCH_RUN_MUTATION,
    RELOAD_REPOSITORY_MUTATION,
    RUN_STATUS_QUERY,
    DagsterClient,
    DagsterClientError,
)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestDagsterClientInit:
    def test_default_url(self, monkeypatch):
        monkeypatch.delenv("DAGSTER_GRAPHQL_URL", raising=False)
        client = DagsterClient()
        assert client.graphql_url == "http://localhost:3000/graphql"

    def test_env_url(self, monkeypatch):
        monkeypatch.setenv(
            "DAGSTER_GRAPHQL_URL", "http://dagster:3333/graphql"
        )
        client = DagsterClient()
        assert client.graphql_url == "http://dagster:3333/graphql"

    def test_explicit_url(self):
        client = DagsterClient(graphql_url="http://custom:9999/graphql")
        assert client.graphql_url == "http://custom:9999/graphql"

    def test_explicit_url_overrides_env(self, monkeypatch):
        monkeypatch.setenv(
            "DAGSTER_GRAPHQL_URL", "http://from-env:3333/graphql"
        )
        client = DagsterClient(graphql_url="http://explicit:9999/graphql")
        assert client.graphql_url == "http://explicit:9999/graphql"


# ---------------------------------------------------------------------------
# Helpers to build mock aiohttp responses
# ---------------------------------------------------------------------------


def _mock_response(json_body: dict, status: int = 200):
    """Return an async-context-manager-compatible mock response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body)
    resp.text = AsyncMock(return_value=str(json_body))
    return resp


def _patch_aiohttp(json_body: dict, status: int = 200):
    """Patch aiohttp.ClientSession so POST returns *json_body*."""
    resp = _mock_response(json_body, status)

    # session.post(...) is used as `async with session.post(...) as resp:`
    mock_post = MagicMock()
    mock_post.__aenter__ = AsyncMock(return_value=resp)
    mock_post.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post
    mock_session.closed = False

    return patch(
        "d4bl.services.dagster_client.aiohttp.ClientSession",
        return_value=mock_session,
    ), mock_session


# ---------------------------------------------------------------------------
# _execute_graphql
# ---------------------------------------------------------------------------


class TestExecuteGraphql:
    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        body = {"data": {"hello": "world"}}
        patcher, mock_session = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient(graphql_url="http://test/graphql")
            result = await client._execute_graphql(
                "query { hello }", {"foo": "bar"}
            )

        assert result == {"hello": "world"}
        # Verify the POST call
        call_kwargs = mock_session.post.call_args
        assert call_kwargs.args[0] == "http://test/graphql"
        payload = call_kwargs.kwargs["json"]
        assert payload["query"] == "query { hello }"
        assert payload["variables"] == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_no_variables(self):
        body = {"data": {"hello": "world"}}
        patcher, mock_session = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient(graphql_url="http://test/graphql")
            await client._execute_graphql("query { hello }")

        payload = mock_session.post.call_args.kwargs["json"]
        assert "variables" not in payload

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        patcher, _ = _patch_aiohttp({}, status=500)

        with patcher:
            client = DagsterClient()
            with pytest.raises(DagsterClientError, match="HTTP 500"):
                await client._execute_graphql("query { x }")

    @pytest.mark.asyncio
    async def test_graphql_errors_raise(self):
        body = {"errors": [{"message": "bad query"}]}
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            with pytest.raises(DagsterClientError, match="bad query"):
                await client._execute_graphql("query { x }")


# ---------------------------------------------------------------------------
# trigger_run
# ---------------------------------------------------------------------------


class TestTriggerRun:
    @pytest.mark.asyncio
    async def test_success(self):
        body = {
            "data": {
                "launchPipelineExecution": {
                    "__typename": "LaunchRunSuccess",
                    "run": {"runId": "abc-123", "status": "QUEUED"},
                }
            }
        }
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            result = await client.trigger_run("census_acs")

        assert result == {"run_id": "abc-123", "status": "QUEUED"}

    @pytest.mark.asyncio
    async def test_python_error(self):
        body = {
            "data": {
                "launchPipelineExecution": {
                    "__typename": "PythonError",
                    "message": "boom",
                    "stack": [],
                }
            }
        }
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            with pytest.raises(DagsterClientError, match="boom"):
                await client.trigger_run("census_acs")


# ---------------------------------------------------------------------------
# get_run_status
# ---------------------------------------------------------------------------


class TestGetRunStatus:
    @pytest.mark.asyncio
    async def test_success(self):
        body = {
            "data": {
                "runOrError": {
                    "__typename": "Run",
                    "runId": "abc-123",
                    "status": "SUCCESS",
                    "startTime": 1000.0,
                    "endTime": 2000.0,
                }
            }
        }
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            result = await client.get_run_status("abc-123")

        assert result["run_id"] == "abc-123"
        assert result["status"] == "SUCCESS"
        assert result["start_time"] == 1000.0
        assert result["end_time"] == 2000.0

    @pytest.mark.asyncio
    async def test_not_found(self):
        body = {
            "data": {
                "runOrError": {
                    "__typename": "RunNotFoundError",
                    "message": "Run abc not found",
                }
            }
        }
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            with pytest.raises(DagsterClientError, match="not found"):
                await client.get_run_status("abc")


# ---------------------------------------------------------------------------
# reload_repository
# ---------------------------------------------------------------------------


class TestReloadRepository:
    @pytest.mark.asyncio
    async def test_success(self):
        body = {
            "data": {
                "reloadRepositoryLocation": {
                    "__typename": "WorkspaceLocationEntry",
                    "name": "d4bl_dagster",
                    "loadStatus": "LOADED",
                }
            }
        }
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            result = await client.reload_repository()

        assert result == {
            "status": "ok",
            "location": "d4bl_dagster",
            "load_status": "LOADED",
        }

    @pytest.mark.asyncio
    async def test_not_found(self):
        body = {
            "data": {
                "reloadRepositoryLocation": {
                    "__typename": "RepositoryLocationNotFound",
                    "message": "no such location",
                }
            }
        }
        patcher, _ = _patch_aiohttp(body)

        with patcher:
            client = DagsterClient()
            with pytest.raises(DagsterClientError, match="no such location"):
                await client.reload_repository()


# ---------------------------------------------------------------------------
# GraphQL query strings are well-formed
# ---------------------------------------------------------------------------


class TestQueryStrings:
    def test_launch_mutation_contains_key_fields(self):
        assert "launchPipelineExecution" in LAUNCH_RUN_MUTATION
        assert "executionParams" in LAUNCH_RUN_MUTATION
        assert "LaunchRunSuccess" in LAUNCH_RUN_MUTATION
        assert "runId" in LAUNCH_RUN_MUTATION

    def test_status_query_contains_key_fields(self):
        assert "runOrError" in RUN_STATUS_QUERY
        assert "runId" in RUN_STATUS_QUERY
        assert "status" in RUN_STATUS_QUERY
        assert "RunNotFoundError" in RUN_STATUS_QUERY

    def test_reload_mutation_contains_key_fields(self):
        assert "reloadRepositoryLocation" in RELOAD_REPOSITORY_MUTATION
        assert "WorkspaceLocationEntry" in RELOAD_REPOSITORY_MUTATION
        assert "loadStatus" in RELOAD_REPOSITORY_MUTATION
