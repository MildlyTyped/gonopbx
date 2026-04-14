"""Ring Groups module — ring group (queue) management."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.groups as _groups_router


class RingGroupsModule(GonoPBXModule):
    router_prefix = "/api/groups"
    router_tags = ["Ring Groups"]

    def get_router(self) -> APIRouter:
        return _groups_router.router
