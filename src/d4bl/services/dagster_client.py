"""GraphQL client for communicating with the Dagster webserver."""

from __future__ import annotations

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GraphQL query / mutation strings
# ---------------------------------------------------------------------------

LAUNCH_RUN_MUTATION = """
mutation LaunchRun($executionParams: ExecutionParams!) {
  launchPipelineExecution(executionParams: $executionParams) {
    __typename
    ... on LaunchRunSuccess {
      run {
        runId
        status
      }
    }
    ... on PythonError {
      message
      stack
    }
    ... on InvalidStepError {
      invalidStepKey
    }
    ... on InvalidOutputError {
      invalidOutputName
      stepKey
    }
    ... on RunConflict {
      message
    }
    ... on UnauthorizedError {
      message
    }
    ... on PresetNotFoundError {
      message
    }
    ... on ConflictingExecutionParamsError {
      message
    }
    ... on NoModeProvidedError {
      message
    }
  }
}
"""

RUN_STATUS_QUERY = """
query RunStatus($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run {
      runId
      status
      startTime
      endTime
    }
    ... on RunNotFoundError {
      message
    }
    ... on PythonError {
      message
    }
  }
}
"""

RELOAD_REPOSITORY_MUTATION = """
mutation ReloadRepositoryLocation($location: String!) {
  reloadRepositoryLocation(repositoryLocationName: $location) {
    __typename
    ... on WorkspaceLocationEntry {
      name
      loadStatus
    }
    ... on ReloadNotSupported {
      message
    }
    ... on RepositoryLocationNotFound {
      message
    }
    ... on UnauthorizedError {
      message
    }
    ... on PythonError {
      message
    }
  }
}
"""


class DagsterClientError(Exception):
    """Raised when a Dagster GraphQL call fails."""


class DagsterClient:
    """Async client that talks to the Dagster GraphQL API."""

    def __init__(self, graphql_url: str | None = None) -> None:
        self.graphql_url = graphql_url or os.environ.get(
            "DAGSTER_GRAPHQL_URL", "http://localhost:3000/graphql"
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return a reusable session, creating one if needed."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def trigger_run(
        self,
        asset_key: str,
        run_config: dict | None = None,
        repository_location: str = "d4bl_dagster",
        repository_name: str = "__repository__",
        job_name: str = "__ASSET_JOB",
    ) -> dict:
        """Trigger a Dagster run to materialise a specific asset.

        Returns ``{"run_id": "...", "status": "QUEUED"}`` on success.
        """
        variables = {
            "executionParams": {
                "selector": {
                    "repositoryLocationName": repository_location,
                    "repositoryName": repository_name,
                    "pipelineName": job_name,
                },
                "runConfigData": run_config or {},
                "stepKeys": None,
                "executionMetadata": {
                    "tags": [
                        {"key": "dagster/asset_key", "value": asset_key},
                    ],
                },
                "mode": "default",
            },
        }

        data = await self._execute_graphql(LAUNCH_RUN_MUTATION, variables)
        result = data.get("launchPipelineExecution", {})
        typename = result.get("__typename", "")

        if typename == "LaunchRunSuccess":
            run = result["run"]
            return {"run_id": run["runId"], "status": run["status"]}

        error_msg = result.get("message", f"Unexpected response type: {typename}")
        raise DagsterClientError(f"Failed to launch run: {error_msg}")

    async def get_run_status(self, run_id: str) -> dict:
        """Return the current status of a Dagster run.

        Returns ``{"run_id": "...", "status": "SUCCESS|FAILURE|..."}``
        """
        data = await self._execute_graphql(
            RUN_STATUS_QUERY, {"runId": run_id}
        )
        result = data.get("runOrError", {})
        typename = result.get("__typename", "")

        if typename == "Run":
            return {
                "run_id": result["runId"],
                "status": result["status"],
                "start_time": result.get("startTime"),
                "end_time": result.get("endTime"),
            }

        error_msg = result.get("message", f"Unexpected response type: {typename}")
        raise DagsterClientError(f"Failed to get run status: {error_msg}")

    async def reload_repository(
        self, location: str = "d4bl_dagster"
    ) -> dict:
        """Reload a Dagster repository location.

        Returns ``{"status": "ok", "location": "..."}`` on success.
        """
        data = await self._execute_graphql(
            RELOAD_REPOSITORY_MUTATION, {"location": location}
        )
        result = data.get("reloadRepositoryLocation", {})
        typename = result.get("__typename", "")

        if typename == "WorkspaceLocationEntry":
            return {
                "status": "ok",
                "location": result.get("name"),
                "load_status": result.get("loadStatus"),
            }

        error_msg = result.get("message", f"Unexpected response type: {typename}")
        raise DagsterClientError(f"Failed to reload repository: {error_msg}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute_graphql(
        self, query: str, variables: dict | None = None
    ) -> dict:
        """POST a GraphQL request to the Dagster webserver and return the
        ``data`` portion of the JSON response.
        """
        payload: dict = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        logger.debug("Dagster GraphQL request to %s", self.graphql_url)

        session = await self._get_session()
        async with session.post(
            self.graphql_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise DagsterClientError(
                    f"Dagster returned HTTP {resp.status}: {body}"
                )

            body = await resp.json()

        if "errors" in body:
            msgs = [e.get("message", str(e)) for e in body["errors"]]
            raise DagsterClientError(
                f"GraphQL errors: {'; '.join(msgs)}"
            )

        return body.get("data", {})
