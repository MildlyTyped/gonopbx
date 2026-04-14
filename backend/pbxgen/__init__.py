"""
PBX Config Generation Plugin Framework.

Usage – registering a global dialplan plugin::

    from pbxgen import register_plugin
    from pbxgen.interfaces import GenerationContext, DialplanPlugin
    from pbxgen.dialplan.ops import DialplanOps

    class RecordingPlugin:
        priority = 10  # runs after core (priority 0)

        def contribute(self, ops: DialplanOps, ctx: GenerationContext) -> None:
            # Add a new context that enables call recording
            ops.ensure_context("module-recording")
            ops.append_step("module-recording", "_X.", Step("MixMonitor", "..."))
            ops.add_include("internal", "module-recording")

        def patch(self, ops: DialplanOps, ctx: GenerationContext) -> None:
            pass

    register_plugin(RecordingPlugin())

Usage – registering a global AMI event plugin::

    from pbxgen import register_ami_plugin
    from pbxgen.ami import AMIProxy

    class HangupNotifyPlugin:
        subscribed_events = ["Hangup"]

        async def on_startup(self, ami: AMIProxy) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        async def on_ami_event(self, event_name, event, ami: AMIProxy) -> None:
            cause = event.get("Cause", "0")
            # ... handle hangup

    register_ami_plugin(HangupNotifyPlugin())
"""

from .ami import AMIEventDispatcher, AMIProxy, get_ami_plugins, register_ami_plugin
from .interfaces import AMIPlugin, ConfigPlugin, DialplanPlugin, GenerationContext
from .pipeline import DialplanPipeline, get_registered_plugins, register_plugin

__all__ = [
    # Dialplan / config generation
    "GenerationContext",
    "DialplanPlugin",
    "ConfigPlugin",
    "DialplanPipeline",
    "register_plugin",
    "get_registered_plugins",
    # AMI events
    "AMIPlugin",
    "AMIProxy",
    "AMIEventDispatcher",
    "register_ami_plugin",
    "get_ami_plugins",
]
