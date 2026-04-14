"""
Plugin interfaces for the PBX config/dialplan generation system.

Dialplan plugins implement :class:`DialplanPlugin` and are registered via
:func:`~pbxgen.pipeline.register_plugin`.  The generation pipeline invokes
them in ascending *priority* order during the **contribute** phase (add new
material) and then the **patch** phase (amend existing material).

Example plugin skeleton::

    from pbxgen.interfaces import GenerationContext, DialplanPlugin
    from pbxgen.dialplan.ops import DialplanOps
    from pbxgen.dialplan.model import Step

    class FeatureCodePlugin:
        priority = 10  # 0 is reserved for the core plugin

        def contribute(self, ops: DialplanOps, ctx: GenerationContext) -> None:
            ops.ensure_context("module-featurecodes")
            ops.append_step("module-featurecodes", "*69",
                            Step("NoOp", "Last-caller recall"))
            ops.append_step("module-featurecodes", "*69",
                            Step("Hangup"))
            # Wire into the main internal context
            ops.add_include("internal", "module-featurecodes")

        def patch(self, ops: DialplanOps, ctx: GenerationContext) -> None:
            pass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

from typing import Protocol, runtime_checkable

if TYPE_CHECKING:
    from .dialplan.ops import DialplanOps

from database import (
    CallForward,
    InboundRoute,
    IVRMenu,
    RingGroup,
    SIPPeer,
    SIPTrunk,
    VoicemailMailbox,
)


@dataclass
class GenerationContext:
    """Carries all DB data needed by plugins during config generation.

    Plugins should treat this as read-only.  All mutations to the output
    must go through :class:`~pbxgen.dialplan.ops.DialplanOps`.
    """

    routes: List[InboundRoute] = field(default_factory=list)
    forwards: List[CallForward] = field(default_factory=list)
    mailboxes: List[VoicemailMailbox] = field(default_factory=list)
    peers: List[SIPPeer] = field(default_factory=list)
    trunks: List[SIPTrunk] = field(default_factory=list)
    ring_groups: List[RingGroup] = field(default_factory=list)
    ivr_menus: List[IVRMenu] = field(default_factory=list)


@runtime_checkable
class DialplanPlugin(Protocol):
    """Interface that dialplan extension modules must implement.

    Attributes:
        priority: Execution order.  Lower values run first.  The built-in
                  ``CoreDialplanPlugin`` uses ``priority = 0``; custom modules
                  should use 10 or higher so they can reference or amend core
                  contexts.
    """

    priority: int

    def contribute(self, ops: "DialplanOps", ctx: GenerationContext) -> None:
        """Add new contexts, extensions, or includes to the dialplan.

        Called in the *contribute* phase (before *patch*).  Use the ops API
        to create or populate contexts rather than mutating the IR directly.
        """
        ...

    def patch(self, ops: "DialplanOps", ctx: GenerationContext) -> None:
        """Amend material created by lower-priority plugins.

        Called in the *patch* phase, after all contribute calls have finished.
        Use this to insert/prepend steps, add includes, or append raw lines
        to contexts that core or other modules created.
        """
        ...


@runtime_checkable
class ConfigPlugin(Protocol):
    """Interface for PJSIP / voicemail / queue config extension modules.

    Placeholder for a future config-file generation pipeline analogous to
    :class:`DialplanPlugin`.  Implement :meth:`contribute_pjsip` to inject
    extra sections into the generated ``pjsip.conf``.
    """

    priority: int

    def contribute_pjsip(self, sections: dict, ctx: GenerationContext) -> None:
        """Add or amend PJSIP ``[section]`` dicts before rendering."""
        ...
