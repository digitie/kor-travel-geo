"""Backend Dagster GraphQL client — SSRF-guarded URL resolution + launchRun trigger.

Shared by the observe router (:mod:`kortravelgeo.api.routers.dagster`) and the API→Dagster
launch adapter (T-290g, dagster-boundary §7). Every backend call targets the **internal**
``dagster_url`` on the ``dagster_allowed_hosts`` SSRF allowlist; the browser-facing public
URL is resolved separately (:attr:`_DagsterUrls.public_url`) and is never fetched here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from kortravelgeo.settings import Settings

_ALLOWED_DAGSTER_SCHEMES = {"http", "https"}


class DagsterUrlConfigurationError(ValueError):
    """Dagster URL settings failed the backend SSRF allowlist."""


class DagsterLaunchError(RuntimeError):
    """A Dagster ``launchRun`` mutation did not return a run id (config-invalid, not
    found, unauthorized, ...)."""


@dataclass(frozen=True)
class _DagsterUrls:
    dagster_url: str
    graphql_url: str
    # Browser-facing URL echoed to the admin UI (iframe/links). Validated as http/https
    # with a host, but NOT restricted to ``dagster_allowed_hosts`` (that allowlist guards
    # backend GraphQL calls only; the public URL is never fetched server-side).
    public_url: str


def _candidate_graphql_url(settings: Settings) -> str:
    if settings.dagster_graphql_url:
        return settings.dagster_graphql_url
    return f"{settings.dagster_url.rstrip('/')}/graphql"


def _normalised_allowed_hosts(settings: Settings) -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in settings.dagster_allowed_hosts
        if host.strip()
    }


def _validated_http_url(
    raw_url: str,
    *,
    setting_name: str,
    allowed_hosts: set[str] | None,
    require_graphql_path: bool = False,
) -> str:
    # ``allowed_hosts=None`` skips the SSRF host allowlist (used for the browser-facing
    # public URL, which is only echoed to the client and never fetched server-side).
    value = raw_url.strip()
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_DAGSTER_SCHEMES:
        raise DagsterUrlConfigurationError(f"{setting_name} scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise DagsterUrlConfigurationError(f"{setting_name} must not include userinfo")
    hostname = parsed.hostname
    if hostname is None:
        raise DagsterUrlConfigurationError(f"{setting_name} host is required")
    if allowed_hosts is not None and hostname.lower().rstrip(".") not in allowed_hosts:
        raise DagsterUrlConfigurationError(
            f"{setting_name} host is not in dagster_allowed_hosts"
        )
    if parsed.query or parsed.fragment:
        raise DagsterUrlConfigurationError(
            f"{setting_name} must not include query or fragment"
        )
    if require_graphql_path and not parsed.path.rstrip("/").endswith("/graphql"):
        raise DagsterUrlConfigurationError(f"{setting_name} path must end with /graphql")
    return urlunsplit((scheme, parsed.netloc, parsed.path, "", ""))


def _dagster_urls(settings: Settings) -> _DagsterUrls:
    allowed_hosts = _normalised_allowed_hosts(settings)
    dagster_url = _validated_http_url(
        settings.dagster_url,
        setting_name="dagster_url",
        allowed_hosts=allowed_hosts,
    )
    graphql_url = _validated_http_url(
        _candidate_graphql_url(settings),
        setting_name="dagster_graphql_url",
        allowed_hosts=allowed_hosts,
        require_graphql_path=True,
    )
    # Browser-facing URL: public domain if set, else fall back to the internal
    # dagster_url. Not allowlist-checked (allowed_hosts=None) — it is only echoed to
    # the admin UI, never used for a backend request.
    public_url = _validated_http_url(
        settings.dagster_public_url or settings.dagster_url,
        setting_name="dagster_public_url",
        allowed_hosts=None,
    )
    return _DagsterUrls(
        dagster_url=dagster_url.rstrip("/"),
        graphql_url=graphql_url,
        public_url=public_url.rstrip("/"),
    )


_LAUNCH_RUN_MUTATION = """
mutation LaunchRun($executionParams: ExecutionParams!) {
  launchRun(executionParams: $executionParams) {
    __typename
    ... on LaunchRunSuccess { run { runId } }
    ... on RunConfigValidationInvalid { errors { message } }
    ... on PythonError { message }
    ... on PipelineNotFoundError { message }
    ... on InvalidSubsetError { message }
    ... on UnauthorizedError { message }
  }
}
"""


async def launch_dagster_run(
    settings: Settings,
    *,
    job_name: str,
    run_config: dict[str, Any],
    tags: dict[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Launch a Dagster job run via the GraphQL ``launchRun`` mutation; return the run id.

    The mutation goes to the SSRF-validated **internal** GraphQL URL. Raises
    :class:`DagsterUrlConfigurationError` when the backend URL fails the allowlist, and
    :class:`DagsterLaunchError` when ``launchRun`` does not yield a run (config invalid,
    job not found, unauthorized, ...). Transport failures surface as ``httpx.HTTPError``.
    ``http_client`` is injectable for tests; production leaves it ``None``.
    """

    urls = _dagster_urls(settings)
    execution_params: dict[str, Any] = {
        "selector": {
            "repositoryName": settings.dagster_repository_name,
            "repositoryLocationName": settings.dagster_repository_location_name,
            "jobName": job_name,
        },
        "runConfigData": run_config,
        "mode": "default",
    }
    if tags:
        execution_params["executionMetadata"] = {
            "tags": [{"key": key, "value": value} for key, value in tags.items()]
        }
    request_json = {
        "query": _LAUNCH_RUN_MUTATION,
        "variables": {"executionParams": execution_params},
    }

    async def _post(client: httpx.AsyncClient) -> str:
        response = await client.post(urls.graphql_url, json=request_json)
        response.raise_for_status()
        return _parse_launch_run(response.json())

    if http_client is not None:
        return await _post(http_client)
    async with httpx.AsyncClient(timeout=settings.dagster_request_timeout_seconds) as client:
        return await _post(client)


def _parse_launch_run(payload: object) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    result = data.get("launchRun") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise DagsterLaunchError("launchRun returned no result")
    typename = result.get("__typename")
    if typename == "LaunchRunSuccess":
        run = result.get("run")
        run_id = run.get("runId") if isinstance(run, dict) else None
        if isinstance(run_id, str) and run_id:
            return run_id
        raise DagsterLaunchError("LaunchRunSuccess did not include a run id")
    raise DagsterLaunchError(f"launchRun failed ({typename}): {_launch_error_message(result)}")


def _launch_error_message(result: dict[str, Any]) -> str:
    message = result.get("message")
    if isinstance(message, str) and message:
        return message
    errors = result.get("errors")
    if isinstance(errors, list):
        messages = [
            error["message"]
            for error in errors
            if isinstance(error, dict) and isinstance(error.get("message"), str)
        ]
        if messages:
            return "; ".join(messages)
    return "unknown launchRun error"
