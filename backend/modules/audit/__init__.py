"""Audit module — admin-only access to audit logs."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from . import router as _audit_router


class AuditModule(GonoPBXModule):
    router_prefix = "/api/audit"
    router_tags = ["Audit"]

    def get_router(self) -> APIRouter:
        return _audit_router.router
