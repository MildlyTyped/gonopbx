"""
PBX Config Generation Plugin Framework.

Usage – registering a global plugin::

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
"""

from .interfaces import ConfigPlugin, DialplanPlugin, GenerationContext
from .pipeline import DialplanPipeline, get_registered_plugins, register_plugin

__all__ = [
    "GenerationContext",
    "DialplanPlugin",
    "ConfigPlugin",
    "DialplanPipeline",
    "register_plugin",
    "get_registered_plugins",
]
