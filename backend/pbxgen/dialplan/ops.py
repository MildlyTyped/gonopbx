"""
DialplanOps – safe mutation API for the :class:`~pbxgen.dialplan.model.Dialplan` IR.

Plugins receive a :class:`DialplanOps` instance and use it to add or amend
the dialplan without direct dict access.  All mutations go through this API
so ordering guarantees and future validation hooks are preserved.

Typical plugin usage::

    from pbxgen.dialplan.model import Step
    from pbxgen.dialplan.ops import DialplanOps

    def contribute(ops: DialplanOps, ctx):
        # Create a new context owned by this module
        ops.ensure_context("module-recording")
        ops.append_step("module-recording", "_X.",
                        Step("MixMonitor", "${UNIQUEID}.wav,b"))
        ops.append_step("module-recording", "_X.",
                        Step("Dial", "PJSIP/${EXTEN},30,tT"))
        ops.append_step("module-recording", "_X.", Step("Hangup"))

        # Wire the new context into the core [internal] context
        ops.add_include("internal", "module-recording")

    def patch(ops: DialplanOps, ctx):
        # Append a raw comment to the from-trunk context
        ops.append_raw_lines("from-trunk",
                             "; module-recording: inbound recording enabled\\n")
"""

from __future__ import annotations

from typing import List

from .model import Context, Dialplan, Step


class DialplanOps:
    """Mutation API for :class:`~pbxgen.dialplan.model.Dialplan`.

    Every write method creates missing contexts/extensions on demand so
    plugins do not need to call :meth:`ensure_context` before every
    :meth:`append_step`.
    """

    def __init__(self, dialplan: Dialplan) -> None:
        self._dp = dialplan

    @property
    def dialplan(self) -> Dialplan:
        """Read-only access to the underlying IR (for inspection only)."""
        return self._dp

    # ------------------------------------------------------------------
    # Preamble
    # ------------------------------------------------------------------

    def set_preamble(self, text: str) -> None:
        """Set the verbatim preamble (``[general]``/``[globals]``) section."""
        self._dp.preamble = text

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def ensure_context(self, name: str) -> Context:
        """Return the named context, creating an empty one if it does not exist."""
        if name not in self._dp.contexts:
            self._dp.contexts[name] = Context(name=name)
        return self._dp.contexts[name]

    def set_raw_lines(self, context_name: str, raw_lines: str) -> None:
        """Replace the verbatim content of a context.

        This is how the core plugin populates contexts using the existing
        string-building logic.  External plugins should prefer
        :meth:`append_step` / :meth:`add_include` to stay modular.
        """
        ctx = self.ensure_context(context_name)
        ctx.raw_lines = raw_lines

    def append_raw_lines(self, context_name: str, raw_lines: str) -> None:
        """Append verbatim lines to a context's raw content.

        Useful for cross-cutting concerns that must inject Asterisk directives
        which cannot be expressed as individual :class:`~pbxgen.dialplan.model.Step`
        objects (e.g. multi-line blocks or conditional sub-contexts).
        """
        ctx = self.ensure_context(context_name)
        ctx.raw_lines += raw_lines

    # ------------------------------------------------------------------
    # Include management
    # ------------------------------------------------------------------

    def add_include(self, context_name: str, include_ctx: str) -> None:
        """Add ``include => <include_ctx>`` to *context_name* if not already present.

        Includes are rendered at the top of the context block, before
        raw_lines and structured extensions.  This is the preferred way for
        modules to wire themselves into a core context::

            ops.add_include("internal", "module-queues")
            ops.add_include("internal", "module-ivr")
        """
        ctx = self.ensure_context(context_name)
        if include_ctx not in ctx.includes:
            ctx.includes.append(include_ctx)

    # ------------------------------------------------------------------
    # Extension / step management
    # ------------------------------------------------------------------

    def ensure_extension(self, context_name: str, exten: str) -> List[Step]:
        """Return (creating if needed) the step list for *exten* in *context_name*."""
        ctx = self.ensure_context(context_name)
        if exten not in ctx.extensions:
            ctx.extensions[exten] = []
        return ctx.extensions[exten]

    def append_step(self, context_name: str, exten: str, step: Step) -> None:
        """Append *step* to the end of extension *exten* in *context_name*."""
        self.ensure_extension(context_name, exten).append(step)

    def insert_step(
        self, context_name: str, exten: str, index: int, step: Step
    ) -> None:
        """Insert *step* at position *index* in extension *exten*.

        Use ``index=0`` to prepend before all existing steps, or a positive
        integer to insert at a specific position.  Negative indices are also
        supported (Python semantics).
        """
        self.ensure_extension(context_name, exten).insert(index, step)

    def prepend_step(self, context_name: str, exten: str, step: Step) -> None:
        """Insert *step* at the very beginning of extension *exten*.

        Shorthand for ``insert_step(..., index=0, ...)``.
        """
        self.insert_step(context_name, exten, 0, step)
