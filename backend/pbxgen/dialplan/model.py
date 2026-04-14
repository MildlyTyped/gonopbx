"""
Intermediate Representation (IR) for an Asterisk dialplan (extensions.conf).

Build a :class:`Dialplan` object, mutate it via
:class:`~pbxgen.dialplan.ops.DialplanOps`, then convert to text with
:func:`~pbxgen.dialplan.render.render_dialplan`.

Design notes
------------
* :class:`Context` supports **both** a verbatim ``raw_lines`` string *and* a
  structured ``extensions`` dict.  The core plugin uses ``raw_lines`` so that
  the existing complex generation logic does not need to be rewritten.
  New/external plugins use the structured ``extensions`` + :class:`Step` API.
* ``raw_lines`` is rendered first; structured extensions are appended after.
  This means core content always precedes module-contributed content within
  the same context.
* ``includes`` are rendered as ``include => <name>`` lines at the top of the
  context header, before any content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Step:
    """One priority step in an Asterisk extension.

    Rendered as::

        exten => <exten>,1,<app>(<args>)      # first step  (is_first=True)
         same => n,<app>(<args>)              # subsequent steps
         same => n(<label>),<app>(<args>)     # labelled step

    Args:
        app:     Asterisk application name, e.g. ``"Dial"``, ``"NoOp"``.
        args:    Application argument string, e.g. ``"PJSIP/1001,30,tT"``.
        label:   Optional priority label, e.g. ``"busy"`` or ``"noanswer"``.
        comment: Optional inline comment appended after the step line.
    """

    app: str
    args: str = ""
    label: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class Context:
    """One ``[context]`` block in ``extensions.conf``.

    Attributes:
        name:       Context name, e.g. ``"internal"`` or ``"from-trunk"``.
        includes:   Ordered list of context names for ``include =>`` lines,
                    rendered before any content.
        raw_lines:  Verbatim text appended directly after the context header
                    and includes.  Used by the core plugin.
        extensions: Structured extension definitions added by plugins.
                    Each key is an extension pattern (e.g. ``"_X."``),
                    each value an ordered list of :class:`Step` objects.
                    Rendered after ``raw_lines``.
    """

    name: str
    includes: List[str] = field(default_factory=list)
    raw_lines: str = ""
    extensions: Dict[str, List[Step]] = field(default_factory=dict)


@dataclass
class Dialplan:
    """Complete in-memory dialplan ready for rendering.

    Attributes:
        preamble:  Verbatim text before the first context, typically the
                   ``[general]`` and ``[globals]`` sections.
        contexts:  Ordered mapping of context name → :class:`Context`.
                   Insertion order is preserved (Python 3.7+) so plugins
                   appending new contexts appear at the end.
    """

    preamble: str = ""
    contexts: Dict[str, Context] = field(default_factory=dict)
