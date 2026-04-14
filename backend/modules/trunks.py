"""Trunks module — SIP trunk management and PJSIP config generation."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from pbxgen.ami import AMIProxy
import routers.trunks as _trunks_router


class TrunksModule(GonoPBXModule):
    router_prefix = "/api/trunks"
    router_tags = ["SIP Trunks"]

    def get_router(self) -> APIRouter:
        return _trunks_router.router

    async def on_module_startup(self, ami: AMIProxy) -> None:
        """Wire the underlying AMI client into the trunks router."""
        _trunks_router.set_ami_client(ami._client)
