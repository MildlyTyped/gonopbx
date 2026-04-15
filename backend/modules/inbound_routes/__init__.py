"""Inbound Routes module — DID-to-extension routing and dialplan generation."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from . import router as _routes_router


class InboundRoutesModule(GonoPBXModule):
    router_prefix = "/api/routes"
    router_tags = ["Inbound Routes"]

    def get_router(self) -> APIRouter:
        return _routes_router.router
