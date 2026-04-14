"""IVR module — Interactive Voice Response menu management."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.ivr as _ivr_router


class IVRModule(GonoPBXModule):
    router_prefix = "/api/ivr"
    router_tags = ["IVR"]

    def get_router(self) -> APIRouter:
        return _ivr_router.router
