"""
AMI Plugin Registry and Dispatcher.

This module provides:

* :class:`AMIProxy` – a safe, thin wrapper around the underlying Asterisk
  Manager connection.  Plugins use this to send AMI actions without touching
  the raw ``panoramisk.Manager`` object.

* :class:`AMIEventDispatcher` – dispatches incoming AMI events to every
  registered :class:`~pbxgen.interfaces.AMIPlugin` in sequence, honouring
  each plugin's :attr:`~pbxgen.interfaces.AMIPlugin.subscribed_events` filter.

* :func:`register_ami_plugin` / :func:`get_ami_plugins` – global registry
  (populated at application startup).

Typical startup wiring (inside the FastAPI ``lifespan`` handler)::

    from pbxgen.ami import register_ami_plugin
    from my_modules.recording import RecordingPlugin

    register_ami_plugin(RecordingPlugin())
    # ... later, when AsteriskAMIClient is created:
    ami_client.set_dispatcher(dispatcher)

Writing a plugin::

    from pbxgen.ami import AMIProxy, register_ami_plugin
    from pbxgen.interfaces import AMIPlugin

    class RecordingPlugin:
        subscribed_events = ["Hangup", "DialBegin"]

        async def on_startup(self, ami: AMIProxy) -> None:
            pass  # e.g. check AMI version

        async def on_shutdown(self) -> None:
            pass  # flush any open files

        async def on_ami_event(
            self, event_name: str, event: dict, ami: AMIProxy
        ) -> None:
            if event_name == "DialBegin":
                caller = event.get("CallerIDNum", "")
                # Start recording via MixMonitor
                await ami.send_action(
                    "MixMonitorMute",
                    Channel=event.get("Channel", ""),
                    State="0",
                )

    register_ami_plugin(RecordingPlugin())
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import AMIPlugin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global AMI plugin registry
# ---------------------------------------------------------------------------

_ami_plugin_registry: List["AMIPlugin"] = []


def register_ami_plugin(plugin: "AMIPlugin") -> None:
    """Register an AMI plugin globally.

    Call this at application startup (before the AMI client connects) so
    that :meth:`AMIPlugin.on_startup` is invoked when the connection is
    established.
    """
    _ami_plugin_registry.append(plugin)
    logger.info(
        "Registered AMI plugin %s (subscribed_events=%s)",
        type(plugin).__name__,
        getattr(plugin, "subscribed_events", None),
    )


def get_ami_plugins() -> List["AMIPlugin"]:
    """Return a snapshot of the global AMI plugin registry."""
    return list(_ami_plugin_registry)


# ---------------------------------------------------------------------------
# AMIProxy – safe interface for plugins to send AMI actions
# ---------------------------------------------------------------------------

class AMIProxy:
    """Safe, plugin-facing wrapper around the Asterisk Manager connection.

    Plugins receive an instance of this class in every lifecycle and event
    handler call.  They should **not** keep a reference across calls; always
    use the instance passed to the current handler.

    Attributes:
        connected: ``True`` when the underlying AMI client is connected.
    """

    def __init__(self, ami_client: Any) -> None:
        """
        Args:
            ami_client: The :class:`~ami_client.AsteriskAMIClient` instance.
        """
        self._client = ami_client

    @property
    def connected(self) -> bool:
        """Whether the AMI client is currently connected."""
        return getattr(self._client, "connected", False)

    @property
    def client(self) -> Any:
        """The underlying :class:`~ami_client.AsteriskAMIClient` instance.

        Use sparingly — prefer :meth:`send_action` and
        :meth:`get_active_channels` for all AMI interactions.  This property
        exists to allow modules that need to pass the raw client to legacy
        helper functions (e.g. ``set_ami_client``) without accessing a
        private attribute.
        """
        return self._client

    async def send_action(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """Send an AMI action and return the response dict.

        Args:
            action: AMI action name, e.g. ``"Originate"``, ``"Command"``.
            **kwargs: Additional AMI fields, e.g. ``Channel="PJSIP/1001"``.

        Returns:
            The AMI response as a dict.

        Raises:
            RuntimeError: When the AMI client is not connected.
            Exception: Propagated from the underlying manager on AMI errors.

        Example::

            response = await ami.send_action(
                "Originate",
                Channel="PJSIP/1001",
                Context="internal",
                Exten="1002",
                Priority=1,
                CallerID="Test <9000>",
                Timeout=30000,
                Async="true",
            )
        """
        if not self.connected:
            raise RuntimeError("AMI client is not connected")
        return await self._client.send_action(action, **kwargs)

    async def get_active_channels(self) -> list:
        """Return the list of currently active call dicts tracked by the AMI client."""
        return await self._client.get_active_channels()


# ---------------------------------------------------------------------------
# AMIEventDispatcher
# ---------------------------------------------------------------------------

class AMIEventDispatcher:
    """Dispatches AMI events to registered :class:`~pbxgen.interfaces.AMIPlugin` instances.

    The dispatcher is created by :class:`~ami_client.AsteriskAMIClient` on
    startup and receives every raw AMI event *after* the client's own
    built-in handlers have run.

    Plugin :attr:`~pbxgen.interfaces.AMIPlugin.subscribed_events` is used to
    filter which plugins receive a given event, avoiding unnecessary coroutine
    overhead for plugins that only care about a few event types.

    Lifecycle
    ---------
    * :meth:`on_startup` is called once after AMI connection is established.
    * :meth:`dispatch` is called for every incoming AMI event.
    * :meth:`on_shutdown` is called before the AMI client disconnects.
    """

    def __init__(self, ami_client: Any) -> None:
        self._proxy = AMIProxy(ami_client)

    async def on_startup(self) -> None:
        """Invoke :meth:`~pbxgen.interfaces.AMIPlugin.on_startup` on all plugins."""
        for plugin in get_ami_plugins():
            try:
                await plugin.on_startup(self._proxy)
            except Exception:
                logger.exception(
                    "Error in on_startup for AMI plugin %s",
                    type(plugin).__name__,
                )

    async def on_shutdown(self) -> None:
        """Invoke :meth:`~pbxgen.interfaces.AMIPlugin.on_shutdown` on all plugins."""
        for plugin in get_ami_plugins():
            try:
                await plugin.on_shutdown()
            except Exception:
                logger.exception(
                    "Error in on_shutdown for AMI plugin %s",
                    type(plugin).__name__,
                )

    async def dispatch(self, event_name: str, event: dict) -> None:
        """Forward *event* to every plugin that subscribed to *event_name*.

        This is called by :class:`~ami_client.AsteriskAMIClient` after its
        own core handling is done, so plugins always see fully-processed
        state (e.g. CDR already saved).

        Args:
            event_name: The ``Event`` field from the AMI event.
            event:      The full event dict.
        """
        for plugin in get_ami_plugins():
            subscribed = getattr(plugin, "subscribed_events", None)
            if subscribed is not None and event_name not in subscribed:
                continue
            try:
                await plugin.on_ami_event(event_name, event, self._proxy)
            except Exception:
                logger.exception(
                    "Error dispatching AMI event %s to plugin %s",
                    event_name,
                    type(plugin).__name__,
                )
