"""Authentication module — login, current user, password change."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from . import router as _auth_router


class AuthModule(GonoPBXModule):
    router_prefix = "/api/auth"
    router_tags = ["Authentication"]

    def get_router(self) -> APIRouter:
        return _auth_router.router
