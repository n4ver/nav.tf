"""Query-side FastAPI dependencies."""

from __future__ import annotations

from .db import get_read_session

__all__ = ["get_read_session"]
