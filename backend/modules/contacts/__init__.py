"""Contacts module — global and per-extension address book."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
from . import router as _contacts_router


class ContactsModule(GonoPBXModule):
    router_prefix = "/api/contacts"
    router_tags = ["Contacts"]

    def get_router(self) -> APIRouter:
        return _contacts_router.router
