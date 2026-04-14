"""Peers module — SIP peer management and PJSIP config generation."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.peers as _peers_router


class PeersModule(GonoPBXModule):
    router_prefix = "/api/peers"
    router_tags = ["SIP Peers"]

    def get_router(self) -> APIRouter:
        return _peers_router.router
