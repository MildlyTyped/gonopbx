"""CDR module — call detail records and statistics."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.cdr as _cdr_router


class CDRModule(GonoPBXModule):
    router_prefix = "/api/cdr"
    router_tags = ["Call Records"]

    def get_router(self) -> APIRouter:
        return _cdr_router.router
