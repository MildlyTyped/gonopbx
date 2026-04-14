"""Settings module — admin-only system settings management."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.settings as _settings_router


class SettingsModule(GonoPBXModule):
    router_prefix = "/api/settings"
    router_tags = ["Settings"]

    def get_router(self) -> APIRouter:
        return _settings_router.router
