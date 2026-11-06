from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.auth import SteamOpenIdClient
from ...shared.auth.urls import resolve_frontend_url, resolve_steam_openid_urls
from ...shared.broker import close_broker
from ...shared.cors import add_cors_middleware
from ...shared.schemas import (
    AssignMatchTournamentCommand,
    AuthCodeExchangeRequest,
    AuthTokenResponse,
    AuthUserView,
    CachedLogIngest,
    CreateEventCommand,
    CreateTournamentCommand,
    IngestLogsTfCommand,
    LinkTournamentToEventCommand,
    RawLogUpload,
    UpdateEventCommand,
    UpdatePlayerDisplayNameCommand,
    UpdateTournamentCommand,
)
from ...shared.settings import enforce_production_settings, fastapi_docs_kwargs
from .auth_service import AuthService
from .db import get_write_session, init_write_db
from .dependencies import AuthenticatedUser, get_current_admin_user, get_current_user
from .outbox_worker import start_outbox_worker, stop_outbox_worker
from .services import CommandService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    enforce_production_settings("command")
    await init_write_db()
    start_outbox_worker()
    yield
    await stop_outbox_worker()
    await close_broker()


app = FastAPI(
    title="CQRS Command Service",
    version="1.0.0",
    lifespan=lifespan,
    **fastapi_docs_kwargs(),
)
add_cors_middleware(app)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled command service error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Auth (Steam OpenID) ─────────────────────────────────────────────────────


@app.get("/api/v1/auth/steam/login")
async def steam_login(request: Request) -> RedirectResponse:
    realm, return_to = resolve_steam_openid_urls(request)
    client = SteamOpenIdClient(realm=realm, return_to=return_to)
    return RedirectResponse(url=client.build_login_url(), status_code=302)


@app.get("/api/v1/auth/steam/callback")
async def steam_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_write_session)],
) -> RedirectResponse:
    params = {key: value for key, value in request.query_params.multi_items()}
    openid = SteamOpenIdClient()
    try:
        steam_id = await openid.validate_callback(params)
    except ValueError as exc:
        query = urlencode({"error": str(exc)})
        return RedirectResponse(
            url=f"{resolve_frontend_url(request)}/auth/callback?{query}",
            status_code=302,
        )

    auth_service = AuthService(session)
    user = await auth_service.upsert_steam_user(steam_id)
    token = auth_service.issue_token(user)
    code = await auth_service.create_login_code(token)
    query = urlencode({"code": code})
    return RedirectResponse(
        url=f"{resolve_frontend_url(request)}/auth/callback?{query}",
        status_code=302,
    )


@app.post("/api/v1/auth/exchange", response_model=AuthTokenResponse)
async def exchange_auth_code(
    payload: AuthCodeExchangeRequest,
    session: Annotated[AsyncSession, Depends(get_write_session)],
) -> AuthTokenResponse:
    auth_service = AuthService(session)
    try:
        token = await auth_service.exchange_login_code(payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthTokenResponse(token=token)


@app.get("/api/v1/auth/me", response_model=AuthUserView)
async def auth_me(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthUserView:
    return AuthUserView(
        steam_id=user.steam_id,
        display_name=user.display_name or user.steam_id,
        avatar_url=user.avatar_url,
        role=user.role.value,
    )


# ── Commands (Admin RBAC) ───────────────────────────────────────────────────


@app.post("/api/v1/commands/logs/upload", status_code=202)
async def upload_log(
    payload: RawLogUpload,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.upload_log(payload, actor_id=admin.steam_id)


@app.post("/api/v1/commands/logs/ingest-cached", status_code=202)
async def ingest_cached_log(
    payload: CachedLogIngest,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.ingest_cached_log(payload, actor_id=admin.steam_id)


@app.post("/api/v1/commands/logs/ingest-logstf", status_code=202)
async def ingest_logstf(
    payload: IngestLogsTfCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.ingest_logs_tf(payload, actor_id=admin.steam_id)


@app.post("/api/v1/commands/players/display-name", status_code=202)
async def update_player_display_name(
    payload: UpdatePlayerDisplayNameCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.update_player_display_name(payload, actor_id=admin.steam_id)


@app.post("/api/v1/commands/tournaments", status_code=202)
async def create_tournament(
    payload: CreateTournamentCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.create_tournament(payload, actor_id=admin.steam_id)


@app.patch("/api/v1/commands/tournaments/{tournament_id}", status_code=202)
async def update_tournament(
    tournament_id: str,
    payload: UpdateTournamentCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.update_tournament(
        tournament_id, payload, actor_id=admin.steam_id
    )


@app.patch("/api/v1/commands/tournaments/{tournament_id}/event", status_code=202)
async def link_tournament_to_event(
    tournament_id: str,
    payload: LinkTournamentToEventCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.link_tournament_to_event(
        tournament_id, payload, actor_id=admin.steam_id
    )


@app.post("/api/v1/commands/events", status_code=202)
async def create_event(
    payload: CreateEventCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.create_event(payload, actor_id=admin.steam_id)


@app.patch("/api/v1/commands/events/{event_id}", status_code=202)
async def update_event(
    event_id: str,
    payload: UpdateEventCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.update_event(event_id, payload, actor_id=admin.steam_id)


@app.patch("/api/v1/commands/matches/{match_id}/tournament", status_code=202)
async def assign_match_tournament(
    match_id: str,
    payload: AssignMatchTournamentCommand,
    session: Annotated[AsyncSession, Depends(get_write_session)],
    admin: Annotated[AuthenticatedUser, Depends(get_current_admin_user)],
) -> dict[str, object]:
    service = CommandService(session)
    return await service.assign_match_tournament(
        match_id, payload, actor_id=admin.steam_id
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "side": "command"}
