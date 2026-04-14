"""
Plugin interfaces for the PBX config/dialplan generation system and AMI events.

Dialplan plugins implement :class:`DialplanPlugin` and are registered via
:func:`~pbxgen.pipeline.register_plugin`.  The generation pipeline invokes
them in ascending *priority* order during the **contribute** phase (add new
material) and then the **patch** phase (amend existing material).

AMI plugins implement :class:`AMIPlugin` and are registered via
:func:`~pbxgen.ami.register_ami_plugin`.  The AMI event dispatcher invokes
:meth:`AMIPlugin.on_ami_event` for every event whose name appears in
:attr:`AMIPlugin.subscribed_events` (or for *every* event when the attribute
is ``None``).

Example dialplan plugin skeleton::

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

Example AMI plugin skeleton::

    from pbxgen.interfaces import AMIPlugin
    from pbxgen.ami import AMIProxy, register_ami_plugin

    class CallNotifyPlugin:
        # Only receive the events we care about (None = receive all)
        subscribed_events = ["Hangup", "DialBegin"]

        async def on_startup(self, ami: AMIProxy) -> None:
            # Called once when the AMI client finishes connecting
            pass

        async def on_shutdown(self) -> None:
            pass  # clean up resources

        async def on_ami_event(
            self, event_name: str, event: dict, ami: AMIProxy
        ) -> None:
            if event_name == "Hangup":
                cause = event.get("Cause", "0")
                # Send an action back to Asterisk if needed
                # await ami.send_action("Command", Command="core show version")

    register_ami_plugin(CallNotifyPlugin())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from typing import Protocol, runtime_checkable

if TYPE_CHECKING:
    from .dialplan.ops import DialplanOps
    from .ami import AMIProxy

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


@runtime_checkable
class AMIPlugin(Protocol):
    """Interface for modules that react to Asterisk Manager Interface events.

    Modules implementing this protocol can:

    * Subscribe to specific AMI event types via :attr:`subscribed_events`.
    * React to events asynchronously via :meth:`on_ami_event`.
    * Send AMI actions back to Asterisk via the :class:`~pbxgen.ami.AMIProxy`
      passed to every handler call.
    * Perform one-time initialisation after the AMI client connects via
      :meth:`on_startup`.
    * Clean up resources on shutdown via :meth:`on_shutdown`.

    Attributes:
        subscribed_events: An optional list of AMI event names this plugin
            wants to receive (e.g. ``["Hangup", "DialBegin"]``).  When
            ``None`` the plugin receives **all** events.  Filtering here is
            more efficient than filtering inside :meth:`on_ami_event`.
    """

    subscribed_events: Optional[List[str]]

    async def on_startup(self, ami: "AMIProxy") -> None:
        """Called once after the AMI client successfully connects.

        Use this to send initial AMI actions, subscribe to specific event
        classes, or seed local state.
        """
        ...

    async def on_shutdown(self) -> None:
        """Called once just before the AMI client disconnects.

        Use this to release resources, flush state, or send farewell actions.
        """
        ...

    async def on_ami_event(
        self, event_name: str, event: dict, ami: "AMIProxy"
    ) -> None:
        """Handle one AMI event.

        Args:
            event_name: The value of the ``Event`` field, e.g. ``"Hangup"``.
            event:      The full event dict as received from panoramisk.
            ami:        Proxy for sending AMI actions back to Asterisk.  Use
                        ``await ami.send_action(...)`` rather than accessing
                        the underlying Manager directly.
        """
        ...
