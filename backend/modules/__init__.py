"""
GonoPBX built-in modules.

Importing this package is sufficient to register all bundled modules with the
global :data:`~pbxgen.module.module_registry`.  A single line in ``main.py``::

    import modules  # noqa: F401

is all that is required before calling
:meth:`~pbxgen.module.ModuleRegistry.wire_routes`.

To add a new module:

1. Create a file in this package (e.g. ``modules/recording.py``).
2. Define a class that inherits from :class:`~pbxgen.module.GonoPBXModule`
   (optionally also implement :class:`~pbxgen.interfaces.DialplanPlugin`
   and/or :class:`~pbxgen.interfaces.AMIPlugin`).
3. Instantiate the class and pass it to :func:`~pbxgen.module.register_module`.
4. Import the new file here.
"""

from pbxgen.module import register_module

from .core import CoreModule
from .auth_module import AuthModule
from .users import UsersModule
from .peers import PeersModule
from .trunks import TrunksModule
from .inbound_routes import InboundRoutesModule
from .dashboard import DashboardModule
from .cdr import CDRModule
from .voicemail import VoicemailModule
from .callforward import CallForwardModule
from .ring_groups import RingGroupsModule
from .ivr import IVRModule
from .contacts import ContactsModule
from .settings import SettingsModule
from .audit import AuditModule
from .sip_debug import SIPDebugModule

# Register all built-in modules with the global registry.
# CoreModule is registered first so its explicit GET / route is added to the
# app before the SPA catch-all registered by wire_static().
register_module(CoreModule())
register_module(AuthModule())
register_module(UsersModule())
register_module(PeersModule())
register_module(TrunksModule())
register_module(InboundRoutesModule())
register_module(DashboardModule())
register_module(CDRModule())
register_module(VoicemailModule())
register_module(CallForwardModule())
register_module(RingGroupsModule())
register_module(IVRModule())
register_module(ContactsModule())
register_module(SettingsModule())
register_module(AuditModule())
register_module(SIPDebugModule())

__all__ = [
    "CoreModule",
    "AuthModule",
    "UsersModule",
    "PeersModule",
    "TrunksModule",
    "InboundRoutesModule",
    "DashboardModule",
    "CDRModule",
    "VoicemailModule",
    "CallForwardModule",
    "RingGroupsModule",
    "IVRModule",
    "ContactsModule",
    "SettingsModule",
    "AuditModule",
    "SIPDebugModule",
]
