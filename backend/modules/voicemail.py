"""Voicemail module — mailbox management and voicemail.conf generation."""

from fastapi import APIRouter
from pbxgen.module import GonoPBXModule
import routers.voicemail as _voicemail_router


class VoicemailModule(GonoPBXModule):
    router_prefix = "/api/voicemail"
    router_tags = ["Voicemail"]

    def get_router(self) -> APIRouter:
        return _voicemail_router.router
