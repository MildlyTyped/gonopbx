"""Core module — health check, call origination, active calls, WebSocket, and root."""

from fastapi import APIRouter

from pbxgen.module import GonoPBXModule
from pbxgen.ami import AMIProxy
from . import router as _core_router


class CoreModule(GonoPBXModule):
    """Module that owns the root SPA endpoint, health check, calls API, and WebSocket."""

    router_prefix = ""
    router_tags = ["Core"]

    def get_router(self) -> APIRouter:
        return _core_router.router

    async def on_module_startup(self, ami: AMIProxy) -> None:
        """Wire the AMI client and broadcast callback into the core router."""
        _core_router.set_ami_client(ami.client)
        ami.client.set_broadcast_callback(_core_router.manager.broadcast)
