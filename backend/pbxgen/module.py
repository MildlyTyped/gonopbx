"""
GonoPBX Module System.

A :class:`GonoPBXModule` is a self-contained unit that bundles:

* A FastAPI :class:`~fastapi.APIRouter` (routes / controllers).
* Optional lifecycle hooks called by the core after the AMI client connects.
* Optional dialplan-generation capability (:class:`~pbxgen.interfaces.DialplanPlugin`).
* Optional AMI-event handling capability (:class:`~pbxgen.interfaces.AMIPlugin`).
* Optional frontend extension: a compiled JS bundle that is injected into the
  SPA ``index.html`` served by :meth:`ModuleRegistry.wire_static`.

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

**Adding a frontend extension to a module**::

    from pathlib import Path
    from pbxgen.module import GonoPBXModule, register_module

    class RecordingModule(GonoPBXModule):
        router_prefix = "/api/recording"
        router_tags = ["Recording"]
        frontend_assets_dir = str(Path(__file__).parent / "frontend_dist")
        frontend_extension_js = "recording.js"

        def get_router(self): ...

    register_module(RecordingModule())

The registry will:

1. Mount ``/module-assets/RecordingModule/`` → the module's ``frontend_dist/``.
2. Inject ``<script type="module" src="/module-assets/RecordingModule/recording.js">``
   into every ``index.html`` response.
3. Include the module in ``GET /api/frontend/modules`` for runtime introspection.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
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

    To contribute a frontend extension set :attr:`frontend_assets_dir` to the
    directory that contains the compiled JS bundle and optionally set
    :attr:`frontend_extension_js` to the entry-point filename.
    """

    #: URL prefix for every route in this module's router.
    router_prefix: str = ""

    #: OpenAPI tag(s) applied to this module's routes.
    router_tags: List[str] = []

    #: Absolute (or relative) path to the directory that contains this
    #: module's compiled frontend assets.  ``None`` means the module has no
    #: frontend extension.
    frontend_assets_dir: Optional[str] = None

    #: Name of the primary JS entry-point file inside
    #: :attr:`frontend_assets_dir` to inject into the SPA.  When ``None``
    #: **and** :attr:`frontend_assets_dir` is set, every ``.js`` file in
    #: that directory is injected (sorted alphabetically).
    frontend_extension_js: Optional[str] = None

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
        #: Set by :meth:`wire_static` once the SPA index has been built.
        #: ``GET /`` in ``main.py`` reads this to serve HTML instead of JSON.
        self._spa_index_html: Optional[str] = None

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

    def wire_static(self, app: "FastAPI", dist_dir) -> None:
        """Mount the compiled frontend SPA and register the SPA catch-all.

        This method **must** be called *after* all API routes have been
        registered (i.e. at the end of the application setup in ``main.py``)
        so that the ``/{full_path:path}`` catch-all does not shadow real API
        endpoints.

        If *dist_dir* does not exist the method logs a warning and returns
        without doing anything — the API continues to function normally on its
        own port.

        Behaviour
        ---------
        1. Mounts ``<dist_dir>/assets`` → ``/assets`` (core frontend assets).
        2. For each registered module that declares :attr:`~GonoPBXModule.frontend_assets_dir`,
           mounts that directory under ``/module-assets/<ClassName>/`` and
           collects the script(s) to inject.
        3. Registers ``GET /api/frontend/modules`` — a JSON manifest of all
           active frontend extensions, useful for runtime introspection.
        4. Reads ``<dist_dir>/index.html``, injects ``<script>`` tags for
           every module extension just before ``</body>``, and caches the
           result in :attr:`_spa_index_html`.
        5. Registers ``GET /{full_path:path}`` as a catch-all that returns the
           (possibly augmented) ``index.html`` for any path not already claimed
           by an API route — preserving client-side SPA routing.

        Args:
            app: The FastAPI application instance.
            dist_dir: Path to the Vite build output directory (the directory
                      that contains ``index.html`` and the ``assets/`` folder).
        """
        from starlette.staticfiles import StaticFiles
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        dist_dir = Path(dist_dir)
        if not dist_dir.is_dir():
            logger.warning(
                "Frontend dist directory %s does not exist; "
                "skipping static file hosting.  The API remains available on "
                "its own port.",
                dist_dir,
            )
            return

        # ------------------------------------------------------------------
        # 1.  Core assets  (dist/assets → /assets)
        # ------------------------------------------------------------------
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="frontend_assets",
            )
            logger.info("Mounted frontend assets at /assets from %s", assets_dir)

        # ------------------------------------------------------------------
        # 2.  Per-module frontend assets + script inventory
        # ------------------------------------------------------------------
        module_extensions: List[Any] = []  # [{"name": str, "scripts": [str]}]

        for module in self._modules:
            module_name = type(module).__name__
            raw_dir = getattr(module, "frontend_assets_dir", None)
            if raw_dir is None:
                continue

            module_assets_path = Path(raw_dir)
            if not module_assets_path.is_dir():
                logger.warning(
                    "Module %s declares frontend_assets_dir=%s but that "
                    "directory does not exist; skipping.",
                    module_name,
                    module_assets_path,
                )
                continue

            mount_path = f"/module-assets/{module_name}"
            app.mount(
                mount_path,
                StaticFiles(directory=str(module_assets_path)),
                name=f"module_assets_{module_name}",
            )
            logger.info(
                "Mounted module frontend assets for %s at %s",
                module_name,
                mount_path,
            )

            ext_js = getattr(module, "frontend_extension_js", None)
            if ext_js is not None:
                scripts = [f"{mount_path}/{ext_js}"]
            else:
                scripts = sorted(
                    f"{mount_path}/{f.name}"
                    for f in module_assets_path.iterdir()
                    if f.suffix == ".js"
                )

            if scripts:
                module_extensions.append({"name": module_name, "scripts": scripts})
                logger.info(
                    "Module %s will inject frontend script(s): %s",
                    module_name,
                    scripts,
                )

        # ------------------------------------------------------------------
        # 3.  /api/frontend/modules — runtime manifest
        # ------------------------------------------------------------------
        @app.get("/api/frontend/modules", tags=["Frontend"])
        async def get_frontend_modules():  # noqa: F811
            """Return the list of frontend extensions registered by GonoPBX modules."""
            return {"modules": module_extensions}

        # ------------------------------------------------------------------
        # 4.  Build (and cache) the injected index.html
        # ------------------------------------------------------------------
        index_path = dist_dir / "index.html"
        if not index_path.is_file():
            logger.warning(
                "index.html not found in %s; cannot activate SPA hosting.",
                dist_dir,
            )
            return

        base_html = index_path.read_text(encoding="utf-8")
        script_tags = "".join(
            f'<script type="module" src="{script}"></script>'
            for ext in module_extensions
            for script in ext["scripts"]
        )
        index_html = (
            base_html.replace("</body>", f"{script_tags}</body>", 1)
            if script_tags
            else base_html
        )

        # Publish so that ``GET /`` in main.py can serve the SPA at the root.
        self._spa_index_html = index_html

        # ------------------------------------------------------------------
        # 5.  SPA catch-all  (must be the last route registered)
        # ------------------------------------------------------------------
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_catch_all(full_path: str, request: Request):  # noqa: F811
            """Serve index.html for any path not handled by an API route."""
            return HTMLResponse(index_html)

        logger.info(
            "Frontend SPA hosting active (dist=%s).  "
            "%d module frontend extension(s) loaded.",
            dist_dir,
            len(module_extensions),
        )

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
