"""Rendering an :class:`~investo.models.AnalysisReport` as a research note.

``render_html`` returns a self-contained, theme-aware, print-ready document — no external assets,
no script, so it is CSP-safe and the PDF path has nothing to fetch. Pass ``standalone=False`` for
a body fragment (e.g. to embed in an Artifact).

The layout: ``sections`` holds the ordered registry (pure data, output-agnostic), ``html`` the
HTML backend, ``charts`` the inline-SVG exhibits, ``fmt`` the shared formatters and ``css`` the
stylesheet.
"""

from __future__ import annotations

from .charts import Chart
from .html import HTML_RENDERERS, render_html
from .sections import SECTIONS, Section, build_guidance

__all__ = ["Chart", "HTML_RENDERERS", "SECTIONS", "Section", "build_guidance", "render_html"]
