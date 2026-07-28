"""User role enumeration for RBAC claims."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    PLAYER = "PLAYER"
    ADMIN = "ADMIN"
