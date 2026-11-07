"""Admin proxy to the api-consumer service (matcha.tf ingest via MatchaAdapter).

The api-consumer authenticates its webhook/admin routes with a shared API key
that must never reach the browser. Admins call the command service with their
JWT, and the command service forwards the request server-to-server with the key.

Configuration:
    API_CONSUMER_URL      Base URL of the api-consumer (e.g. http://api-consumer:8010).
                          Unset disables the integration (endpoints return 503).
    API_CONSUMER_API_KEY  Key sent as ``Authorization: Bearer``. Falls back to
                          WEBHOOK_API_KEY so one variable can serve both services.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

MATCH_TIMEOUT_SECONDS = 120.0
# A full league poll walks every match and its logs.tf logs at a polite rate.
POLL_TIMEOUT_SECONDS = 600.0
STATUS_TIMEOUT_SECONDS = 5.0


def api_consumer_url() -> str:
    return os.getenv("API_CONSUMER_URL", "").strip().rstrip("/")


def api_consumer_api_key() -> str:
    return (
        os.getenv("API_CONSUMER_API_KEY", "").strip()
        or os.getenv("WEBHOOK_API_KEY", "").strip()
    )


def _require_config() -> tuple[str, str]:
    base_url = api_consumer_url()
    api_key = api_consumer_api_key()
    if not base_url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "api-consumer is not configured "
                "(set API_CONSUMER_URL and API_CONSUMER_API_KEY)"
            ),
        )
    return base_url, api_key


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or f"api-consumer returned {response.status_code}"
    if isinstance(body, dict):
        return str(
            body.get("error")
            or body.get("detail")
            or f"api-consumer returned {response.status_code}"
        )
    return f"api-consumer returned {response.status_code}"


async def _post(path: str, *, json: dict[str, Any] | None, params: dict[str, str] | None,
                timeout: float) -> dict[str, Any]:
    base_url, api_key = _require_config()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}{path}",
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="api-consumer did not respond in time",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("api-consumer unreachable at %s: %s", base_url, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api-consumer is unreachable",
        ) from exc

    if response.status_code in (200, 202):
        try:
            body = response.json()
        except ValueError:
            body = {}
        return body if isinstance(body, dict) else {"result": body}

    detail = _error_detail(response)
    if response.status_code == 409:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if response.status_code in (401, 403, 503):
        # Misconfigured key on either side: an operator problem, not the admin's.
        logger.error("api-consumer rejected proxy request (%s): %s", response.status_code, detail)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"api-consumer refused the request: {detail}",
        )
    if response.status_code == 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


async def ingest_matcha_match(match_id: int, *, correlation_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"matchId": match_id}
    if correlation_id:
        payload["correlationId"] = correlation_id
    return await _post(
        "/webhooks/matcha/match", json=payload, params=None, timeout=MATCH_TIMEOUT_SECONDS
    )


async def poll_matcha(*, reset: bool = False) -> dict[str, Any]:
    return await _post(
        "/admin/poll",
        json=None,
        params={"reset": "true"} if reset else None,
        timeout=POLL_TIMEOUT_SECONDS,
    )


async def api_consumer_status() -> dict[str, Any]:
    """Report whether the integration is configured and the service answers /health."""
    base_url = api_consumer_url()
    configured = bool(base_url and api_consumer_api_key())
    result: dict[str, Any] = {"configured": configured, "reachable": False, "source_site": "matcha.tf"}
    if not base_url:
        return result
    try:
        async with httpx.AsyncClient(timeout=STATUS_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{base_url}/health")
        result["reachable"] = response.status_code == 200
    except httpx.HTTPError:
        result["reachable"] = False
    return result
