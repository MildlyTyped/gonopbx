"""Users module — admin CRUD for user accounts."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.users as _users_router


class UsersModule(GonoPBXModule):
    router_prefix = "/api/users"
    router_tags = ["Users"]

    def get_router(self) -> APIRouter:
        return _users_router.router
