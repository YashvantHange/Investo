"""Section-registry tests (no network).

The registry exists to stop the report's section lists drifting apart, so these tests mostly
guard that promise: the keys must name real model fields, and every key must be renderable.
"""

from investo.models import AnalysisReport
from investo.render.html import HTML_RENDERERS
from investo.render.sections import SECTIONS, SECTIONS_BY_KEY, build_guidance


def test_every_section_key_is_a_real_report_field():
    # The registry is the contract between the model and every renderer; a typo'd key would
    # silently drop a whole section from the note.
    fields = set(AnalysisReport.model_fields)
    for s in SECTIONS:
        assert s.key in fields, f"section {s.key!r} names no AnalysisReport field"


def test_every_section_has_an_html_renderer():
    for s in SECTIONS:
        assert s.key in HTML_RENDERERS, f"section {s.key!r} has no HTML renderer"


def test_no_orphan_renderers():
    for key in HTML_RENDERERS:
        assert key in SECTIONS_BY_KEY, f"renderer {key!r} renders no registered section"


def test_numbers_are_contiguous_and_ordered():
    numbers = [s.number for s in SECTIONS]
    assert numbers == list(range(1, len(SECTIONS) + 1))


def test_keys_and_titles_are_unique():
    assert len({s.key for s in SECTIONS}) == len(SECTIONS)
    assert len({s.title for s in SECTIONS}) == len(SECTIONS)


def test_guidance_is_generated_from_the_registry():
    # Generated, not hand-written: the LLM narrative and the rendered document must describe
    # the same report.
    g = build_guidance()
    for s in SECTIONS:
        assert s.title.upper() in g
        assert f"`{s.key}`" in g


def test_guidance_forbids_invented_numbers_and_keeps_the_disclaimer():
    g = build_guidance()
    assert "never invent numbers" in g
    assert "not investment advice" in g
