"""Server-tool registration and safety tests (no network).

These don't invoke the tools (that would hit the network); they check the wiring — that the new
tools are registered, that the one file-writing tool is correctly marked non-read-only, that the
export path is sandboxed, and that the manifest lists exactly what the server registers.
"""

import json
from pathlib import Path

import pytest

from investo import server

_NEW_TOOLS = {"technical_snapshot", "dcf_sensitivity", "compare_companies",
              "peer_group_directory", "export_report"}


def _tools() -> dict:
    return server.mcp._tool_manager._tools


def test_all_new_tools_are_registered():
    names = set(_tools())
    assert _NEW_TOOLS <= names
    assert len(names) == 28  # 23 existing + 5 new


# Both tools write a file to disk: export_report always, analyze_company when emit_html is on
# (the default). Everything else is pure read-only retrieval.
_FILE_WRITING_TOOLS = {"export_report", "analyze_company"}


def test_only_the_file_writing_tools_are_non_read_only():
    for name, tool in _tools().items():
        ann = tool.annotations
        read_only = ann.readOnlyHint if ann else None
        if name in _FILE_WRITING_TOOLS:
            assert read_only is False, f"{name} writes a file and must not claim readOnlyHint=True"
        else:
            assert read_only is True, f"{name} should be read-only"


def test_new_tools_have_descriptions():
    tools = _tools()
    for name in _NEW_TOOLS:
        assert (tools[name].description or "").strip(), f"{name} has no description"


# --------------------------------------------------------------------------------------
# The export path is LLM-controlled -> it must not escape the sandbox
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("evil", [
    "../../etc/passwd",
    "../../../Windows/System32/drivers/etc/hosts",
    "sub/../../escape",
    "/etc/shadow",  # POSIX-absolute — rejected uniformly, on Windows too
])
def test_export_path_escapes_are_rejected(evil):
    with pytest.raises(ValueError, match="inside the export directory"):
        server._safe_export_path(evil, "pdf")


def _export_dir(monkeypatch, tmp_path):
    """`_safe_export_path` imports CONFIG from investo.config each call, so patch it there."""
    import dataclasses

    import investo.config as config
    monkeypatch.setattr(config, "CONFIG", dataclasses.replace(config.CONFIG,
                                                              export_dir=str(tmp_path)))


def test_a_plain_name_lands_inside_the_sandbox(tmp_path, monkeypatch):
    _export_dir(monkeypatch, tmp_path)
    out = server._safe_export_path("kpit-report", "pdf")
    assert out.parent == tmp_path.resolve()
    assert out.name == "kpit-report.pdf"


def test_a_subdirectory_name_is_allowed(tmp_path, monkeypatch):
    _export_dir(monkeypatch, tmp_path)
    out = server._safe_export_path("reports/kpit", "html")
    assert out.is_relative_to(tmp_path.resolve())
    assert out.name == "kpit.html"


def test_export_path_forces_the_requested_extension(tmp_path, monkeypatch):
    _export_dir(monkeypatch, tmp_path)
    assert server._safe_export_path("report.txt", "pdf").suffix == ".pdf"
    assert server._safe_export_path("report", "html").suffix == ".html"


# --------------------------------------------------------------------------------------
# Automatic HTML export (what analyze_company does when emit_html is on)
# --------------------------------------------------------------------------------------
def test_attach_html_report_writes_into_the_sandbox_and_records_metadata(tmp_path, monkeypatch):
    _export_dir(monkeypatch, tmp_path)
    from investo.models import AnalysisReport, CompanyProfile, TickerCandidate

    report = AnalysisReport(
        query="KPIT",
        resolved=TickerCandidate(symbol="KPITTECH.NS", name="KPIT Technologies Limited"),
        profile=CompanyProfile(ticker="KPITTECH.NS", name="KPIT Technologies Limited"),
    )
    server._attach_html_report(report)

    assert report.html_report_path, "the report should record where the HTML was written"
    written = Path(report.html_report_path)
    assert written.exists() and written.is_relative_to(tmp_path.resolve())
    assert written.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert report.html_bytes and report.html_bytes > 0
    assert report.investo_version and report.generated_at


# --------------------------------------------------------------------------------------
# Manifest parity — this repo is structurally prone to drift here
# --------------------------------------------------------------------------------------
def test_manifest_lists_exactly_the_registered_tools():
    manifest = json.loads((Path(__file__).resolve().parent.parent / "manifest.json").read_text())
    manifest_names = {t["name"] for t in manifest["tools"]}
    registered = set(_tools())
    assert manifest_names == registered, (
        f"manifest and server disagree; "
        f"only in manifest: {manifest_names - registered}; "
        f"only in server: {registered - manifest_names}"
    )
