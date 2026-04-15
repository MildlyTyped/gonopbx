"""Call Forwarding module — per-extension call forwarding rules."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from . import router as _callforward_router


class CallForwardModule(GonoPBXModule):
    router_prefix = "/api/callforward"
    router_tags = ["Call Forwarding"]

    def get_router(self) -> APIRouter:
        return _callforward_router.router
