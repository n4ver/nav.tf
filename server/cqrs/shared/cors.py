"""CORS middleware for CQRS FastAPI apps."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    frontend = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    defaults = {
        frontend,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    return sorted(defaults)


def add_cors_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
