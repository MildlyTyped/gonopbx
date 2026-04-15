"""
Renderer: converts a :class:`~pbxgen.dialplan.model.Dialplan` IR to the
``extensions.conf`` text format.

Only :func:`render_dialplan` is part of the public API.  The private helpers
``_render_step`` and ``_render_context`` are implementation details.
"""

from __future__ import annotations

from .model import Context, Dialplan, Step


def _render_step(exten: str, step: Step, is_first: bool) -> str:
    """Render a single :class:`~pbxgen.dialplan.model.Step` line.

    The Asterisk dialplan format is::

        exten => <exten>,1,<App>(<args>)       # first priority
         same => n,<App>(<args>)               # subsequent priorities
         same => n(<label>),<App>(<args>)      # labelled priority
    """
    app_call = f"{step.app}({step.args})" if step.args else f"{step.app}()"

    if is_first:
        if step.label:
            line = f"exten => {exten},1({step.label}),{app_call}"
        else:
            line = f"exten => {exten},1,{app_call}"
    else:
        if step.label:
            line = f" same => n({step.label}),{app_call}"
        else:
            line = f" same => n,{app_call}"

    if step.comment:
        line += f"  ; {step.comment}"

    return line + "\n"


def _render_context(ctx: Context) -> str:
    """Render one :class:`~pbxgen.dialplan.model.Context` block."""
    lines = f"[{ctx.name}]\n"

    for inc in ctx.includes:
        lines += f"include => {inc}\n"

    lines += ctx.raw_lines

    for exten, steps in ctx.extensions.items():
        for i, step in enumerate(steps):
            lines += _render_step(exten, step, is_first=(i == 0))

    return lines


def render_dialplan(dialplan: Dialplan) -> str:
    """Convert a :class:`~pbxgen.dialplan.model.Dialplan` IR to ``extensions.conf`` text.

    The output order is:
    1. ``dialplan.preamble`` (verbatim – ``[general]`` + ``[globals]``)
    2. For each context in insertion order:
       a. ``[context_name]``
       b. ``include => …`` lines
       c. ``raw_lines`` (verbatim content from the core plugin)
       d. Structured extensions contributed by external plugins
    """
    result = dialplan.preamble
    for ctx in dialplan.contexts.values():
        result += _render_context(ctx)
    return result
