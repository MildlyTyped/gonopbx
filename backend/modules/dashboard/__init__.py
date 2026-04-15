"""Dashboard module — real-time system status and statistics."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from pbxgen.ami import AMIProxy
from . import router as _dashboard_router


class DashboardModule(GonoPBXModule):
    router_prefix = "/api/dashboard"
    router_tags = ["Dashboard"]

    def get_router(self) -> APIRouter:
        return _dashboard_router.router

    async def on_module_startup(self, ami: AMIProxy) -> None:
        """Wire the underlying AMI client into the dashboard router."""
        _dashboard_router.set_ami_client(ami.client)
