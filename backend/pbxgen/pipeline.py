"""
DialplanPipeline: orchestrates plugin phases to produce ``extensions.conf``.

Plugins are executed in ascending *priority* order.

Phase 1 – **contribute**: seed / add new contexts, extensions, and raw lines.
Phase 2 – **patch**:      amend what earlier plugins produced.
Phase 3 – **render**:     convert the IR to text.

Registering a global plugin (applied to every generation call)::

    from pbxgen.pipeline import register_plugin
    register_plugin(MyRecordingPlugin())

Using a one-off pipeline with explicit plugins::

    from pbxgen.pipeline import DialplanPipeline
    pipeline = DialplanPipeline(plugins=[CoreDialplanPlugin(), MyPlugin()])
    config_text = pipeline.run(gen_ctx)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .dialplan.model import Dialplan
from .dialplan.ops import DialplanOps
from .dialplan.render import render_dialplan
from .interfaces import DialplanPlugin, GenerationContext

logger = logging.getLogger(__name__)

# Module-level registry – populated at startup via register_plugin().
_plugin_registry: List[DialplanPlugin] = []


def register_plugin(plugin: DialplanPlugin) -> None:
    """Register *plugin* globally so it runs in every pipeline invocation.

    Plugins are kept sorted by ``priority`` (ascending).  Call this during
    application startup (e.g. in the FastAPI ``lifespan`` handler) after
    all feature modules have been imported.
    """
    _plugin_registry.append(plugin)
    _plugin_registry.sort(key=lambda p: getattr(p, "priority", 100))
    logger.info(
        "Registered dialplan plugin %s (priority=%s)",
        type(plugin).__name__,
        getattr(plugin, "priority", 100),
    )


def get_registered_plugins() -> List[DialplanPlugin]:
    """Return a snapshot of the global plugin registry (safe to iterate)."""
    return list(_plugin_registry)


class DialplanPipeline:
    """Runs a list of :class:`~pbxgen.interfaces.DialplanPlugin` plugins in
    priority order to produce a complete ``extensions.conf`` string.

    Args:
        plugins: Explicit plugin list.  When *None* (default) the global
                 registry returned by :func:`get_registered_plugins` is used.
    """

    def __init__(self, plugins: Optional[List[DialplanPlugin]] = None) -> None:
        if plugins is not None:
            self.plugins = sorted(
                plugins, key=lambda p: getattr(p, "priority", 100)
            )
        else:
            self.plugins = get_registered_plugins()

    def run(self, gen_ctx: GenerationContext) -> str:
        """Execute the pipeline and return the rendered dialplan text.

        Phases
        ------
        1. **contribute** – each plugin (in priority order) adds new contexts
           or extensions to the IR via :class:`~pbxgen.dialplan.ops.DialplanOps`.
        2. **patch** – each plugin (in priority order) may amend contexts that
           earlier plugins (including core) created.
        3. **render** – the IR is converted to ``extensions.conf`` text.
        """
        dialplan = Dialplan()
        ops = DialplanOps(dialplan)
        errors: list = []

        # Phase 1: contribute
        for plugin in self.plugins:
            try:
                plugin.contribute(ops, gen_ctx)
            except Exception as exc:
                logger.exception(
                    "Error in contribute phase of plugin %s",
                    type(plugin).__name__,
                )
                errors.append((type(plugin).__name__, "contribute", exc))

        # Phase 2: patch
        for plugin in self.plugins:
            try:
                plugin.patch(ops, gen_ctx)
            except Exception as exc:
                logger.exception(
                    "Error in patch phase of plugin %s",
                    type(plugin).__name__,
                )
                errors.append((type(plugin).__name__, "patch", exc))

        if errors:
            summary = ", ".join(
                f"{name}.{phase}" for name, phase, _ in errors
            )
            logger.warning(
                "Dialplan pipeline completed with %d plugin error(s): %s. "
                "The generated dialplan may be incomplete.",
                len(errors),
                summary,
            )

        # Phase 3: render
        return render_dialplan(dialplan)
