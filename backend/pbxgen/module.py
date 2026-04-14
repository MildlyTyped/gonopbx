"""
GonoPBX Module System.

A :class:`GonoPBXModule` is a self-contained unit that bundles:

* A FastAPI :class:`~fastapi.APIRouter` (routes / controllers).
* Optional lifecycle hooks called by the core after the AMI client connects.
* Optional dialplan-generation capability (:class:`~pbxgen.interfaces.DialplanPlugin`).
* Optional AMI-event handling capability (:class:`~pbxgen.interfaces.AMIPlugin`).

The :class:`ModuleRegistry` singleton discovers all registered modules and
wires them into the FastAPI application.

Typical usage
-------------
**Defining a module**::

    from fastapi import APIRouter
    from pbxgen.module import GonoPBXModule, register_module
    from pbxgen.ami import AMIProxy

    _router = APIRouter()

    @_router.get("/hello")
    async def hello():
        return {"hello": "world"}

    class HelloModule:
        router_prefix = "/api/hello"
        router_tags = ["Hello"]

        def get_router(self) -> APIRouter:
            return _router

    register_module(HelloModule())

**Bootstrapping in main.py**::

    import modules  # registers all bundled modules as a side-effect
    from pbxgen.module import module_registry

    app = FastAPI(lifespan=lifespan)
    module_registry.wire_routes(app)

    @asynccontextmanager
    async def lifespan(app):
        ...
        await module_registry.startup(ami_proxy)
        yield
        await module_registry.shutdown()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional, TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from fastapi import FastAPI
    from .ami import AMIProxy

logger = logging.getLogger(__name__)


class GonoPBXModule:
    """Base class (and informal protocol) for GonoPBX modules.

    Subclasses must set :attr:`router_prefix` and :attr:`router_tags` and
    override :meth:`get_router`.  Lifecycle hooks are optional.

    A module may *additionally* implement :class:`~pbxgen.interfaces.DialplanPlugin`
    and/or :class:`~pbxgen.interfaces.AMIPlugin`; the :class:`ModuleRegistry` will
    auto-register it with the appropriate sub-system.
    """

    #: URL prefix for every route in this module's router.
    router_prefix: str = ""

    #: OpenAPI tag(s) applied to this module's routes.
    router_tags: List[str] = []

    def get_router(self) -> APIRouter:
        """Return the :class:`~fastapi.APIRouter` for this module."""
        raise NotImplementedError(f"{type(self).__name__} must implement get_router()")

    async def on_module_startup(self, ami: "AMIProxy") -> None:
        """Called once after the AMI client successfully connects.

        Override to perform one-time initialisation that requires the AMI
        client, e.g. wiring the AMI client reference into the underlying
        router.

        Args:
            ami: Write-only proxy to the Asterisk Manager Interface.
        """

    async def on_module_shutdown(self) -> None:
        """Called once just before the AMI client disconnects.

        Override to release resources or flush state.
        """


# ---------------------------------------------------------------------------
# ModuleRegistry
# ---------------------------------------------------------------------------

class ModuleRegistry:
    """Collects :class:`GonoPBXModule` instances and wires them into the app.

    The registry is also capable of auto-registering a module with the
    dialplan-plugin and AMI-plugin sub-systems if the module implements the
    corresponding protocols.
    """

    def __init__(self) -> None:
        self._modules: List[Any] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, module: Any) -> None:
        """Register *module* with the core.

        If *module* also satisfies :class:`~pbxgen.interfaces.DialplanPlugin`
        it is forwarded to :func:`~pbxgen.pipeline.register_plugin`.

        If *module* also satisfies :class:`~pbxgen.interfaces.AMIPlugin`
        it is forwarded to :func:`~pbxgen.ami.register_ami_plugin`.

        Args:
            module: Any object that implements the :class:`GonoPBXModule`
                    interface (``router_prefix``, ``router_tags``,
                    ``get_router``).
        """
        self._modules.append(module)
        logger.info("Registered module %s (prefix=%s)", type(module).__name__, getattr(module, "router_prefix", ""))

        # Auto-register with the dialplan plugin sub-system if applicable.
        try:
            from .interfaces import DialplanPlugin
            from .pipeline import register_plugin
            if isinstance(module, DialplanPlugin):
                register_plugin(module)
                logger.info("  → also registered as DialplanPlugin")
        except Exception:
            logger.exception("Failed to auto-register %s as DialplanPlugin", type(module).__name__)

        # Auto-register with the AMI plugin sub-system if applicable.
        try:
            from .interfaces import AMIPlugin
            from .ami import register_ami_plugin
            if isinstance(module, AMIPlugin):
                register_ami_plugin(module)
                logger.info("  → also registered as AMIPlugin")
        except Exception:
            logger.exception("Failed to auto-register %s as AMIPlugin", type(module).__name__)

    # ------------------------------------------------------------------
    # Route wiring
    # ------------------------------------------------------------------

    def wire_routes(self, app: "FastAPI") -> None:
        """Include every module's router into *app*.

        Args:
            app: The FastAPI application instance.
        """
        for module in self._modules:
            try:
                router = module.get_router()
                prefix = getattr(module, "router_prefix", "")
                tags = getattr(module, "router_tags", [])
                app.include_router(router, prefix=prefix, tags=tags)
                logger.info("Wired routes for %s at %s", type(module).__name__, prefix)
            except Exception:
                logger.exception("Failed to wire routes for module %s", type(module).__name__)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self, ami: "AMIProxy") -> None:
        """Call :meth:`GonoPBXModule.on_module_startup` on every module.

        Args:
            ami: The :class:`~pbxgen.ami.AMIProxy` to pass to each module.
        """
        for module in self._modules:
            hook = getattr(module, "on_module_startup", None)
            if hook is not None and callable(hook):
                try:
                    result = hook(ami)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Error in on_module_startup for %s", type(module).__name__)

    async def shutdown(self) -> None:
        """Call :meth:`GonoPBXModule.on_module_shutdown` on every module."""
        for module in self._modules:
            hook = getattr(module, "on_module_shutdown", None)
            if hook is not None and callable(hook):
                try:
                    result = hook()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Error in on_module_shutdown for %s", type(module).__name__)

    def get_modules(self) -> List[Any]:
        """Return a snapshot of all registered modules."""
        return list(self._modules)


# ---------------------------------------------------------------------------
# Module-level singleton and convenience helpers
# ---------------------------------------------------------------------------

#: Global module registry singleton.  Import this from both module files and
#: ``main.py`` to share the same registry instance.
module_registry = ModuleRegistry()


def register_module(module: Any) -> None:
    """Register *module* with the global :data:`module_registry`.

    Convenience wrapper so module files can do::

        from pbxgen.module import register_module
        register_module(MyModule())
    """
    module_registry.register(module)


def get_modules() -> List[Any]:
    """Return all modules registered with the global :data:`module_registry`."""
    return module_registry.get_modules()
