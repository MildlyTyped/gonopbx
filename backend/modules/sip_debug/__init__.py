"""SIP Debug module — PJSIP history capture and SIP message inspection."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from pbxgen.ami import AMIProxy
from . import router as _sip_debug_router


class SIPDebugModule(GonoPBXModule):
    router_prefix = "/api/sip-debug"
    router_tags = ["SIP Debug"]

    def get_router(self) -> APIRouter:
        return _sip_debug_router.router

    async def on_module_startup(self, ami: AMIProxy) -> None:
        """Wire the underlying AMI client into the SIP debug router."""
        _sip_debug_router.set_ami_client(ami.client)
