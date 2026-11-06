"""Direct unit tests for CommandService HTTP helpers and ingest edge cases."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from cqrs.command_service.app.db import SessionLocal
from cqrs.command_service.app.services import CommandService


class _FakeAsyncClient:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str):
        return await self._handler(url)


def _run(coro):
    return asyncio.run(coro)


async def _service() -> CommandService:
    session = SessionLocal()
    return CommandService(session)


def test_fetch_logs_tf_json_maps_connect_error_to_502():
    async def handler(_url: str):
        raise httpx.ConnectError("connection refused")

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                with pytest.raises(HTTPException) as exc:
                    await service._fetch_logs_tf_json(1234567)
                assert exc.value.status_code == 502
                assert "logs.tf" in exc.value.detail.lower()

    _run(run())


def test_fetch_logs_tf_json_maps_http_404():
    class Response:
        status_code = 404

        def json(self):
            return {}

    async def handler(_url: str):
        return Response()

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                with pytest.raises(HTTPException) as exc:
                    await service._fetch_logs_tf_json(999)
                assert exc.value.status_code == 404

    _run(run())


def test_fetch_logs_tf_json_maps_non_200_status():
    class Response:
        status_code = 503

        def json(self):
            return {}

    async def handler(_url: str):
        return Response()

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                with pytest.raises(HTTPException) as exc:
                    await service._fetch_logs_tf_json(888)
                assert exc.value.status_code == 502

    _run(run())


def test_fetch_logs_tf_json_rejects_invalid_json_body():
    class Response:
        status_code = 200

        def json(self):
            raise ValueError("invalid json")

    async def handler(_url: str):
        return Response()

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                with pytest.raises(HTTPException) as exc:
                    await service._fetch_logs_tf_json(777)
                assert "invalid JSON" in exc.value.detail

    _run(run())


def test_fetch_logs_tf_json_rejects_non_object_payload():
    class Response:
        status_code = 200

        def json(self):
            return ["not", "a", "dict"]

    async def handler(_url: str):
        return Response()

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                with pytest.raises(HTTPException) as exc:
                    await service._fetch_logs_tf_json(666)
                assert "unexpected payload" in exc.value.detail.lower()

    _run(run())


def test_fetch_logs_tf_json_rejects_success_false():
    class Response:
        status_code = 200

        def json(self):
            return {"success": False}

    async def handler(_url: str):
        return Response()

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                with pytest.raises(HTTPException) as exc:
                    await service._fetch_logs_tf_json(555)
                assert exc.value.status_code == 404

    _run(run())


def test_fetch_logs_tf_json_returns_payload_on_success():
    sample = {"success": True, "info": {"map": "cp_test"}, "teams": {}, "players": {}}

    class Response:
        status_code = 200

        def json(self):
            return sample

    async def handler(_url: str):
        return Response()

    async def run() -> None:
        async with SessionLocal() as session:
            service = CommandService(session)
            with patch(
                "cqrs.command_service.app.services.httpx.AsyncClient",
                return_value=_FakeAsyncClient(handler),
            ):
                data = await service._fetch_logs_tf_json(444)
                assert data == sample

    _run(run())


def test_ingest_cached_missing_cache_file_returns_503(client, monkeypatch):
    def _missing_file(_log_id: int, *, cache_path=None):
        raise FileNotFoundError("seed cache missing")

    monkeypatch.setattr(
        "cqrs.command_service.app.services.get_cached_log_data", _missing_file
    )

    response = client["command"].post(
        "/api/v1/commands/logs/ingest-cached",
        json={"log_id": 12345, "tournament_id": 2, "section": "missing-file"},
    )
    assert response.status_code == 503
