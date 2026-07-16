"""PDF/HTML export tests (no network, and — crucially — no real browser launch).

Every test here stubs ``subprocess.run`` or Playwright. A test that actually shelled out to Chrome
would be slow, flaky, and machine-dependent — exactly what this offline suite exists to avoid.
"""

import dataclasses
import subprocess
from pathlib import Path

import pytest

from investo import export
from investo.models import AnalysisReport, CompanyProfile, TickerCandidate


def _set_chrome_path(monkeypatch, value: str) -> None:
    """CONFIG is a frozen dataclass, so swap in a copy rather than assigning a field."""
    monkeypatch.setattr(export, "CONFIG", dataclasses.replace(export.CONFIG, chrome_path=value))


def _report() -> AnalysisReport:
    return AnalysisReport(
        query="KPIT Technologies",
        resolved=TickerCandidate(symbol="KPITTECH.NS", name="KPIT Technologies Limited"),
        profile=CompanyProfile(ticker="KPITTECH.NS", name="KPIT Technologies Limited"),
    )


# --------------------------------------------------------------------------------------
# Browser discovery
# --------------------------------------------------------------------------------------
def test_configured_chrome_path_is_honoured(monkeypatch, tmp_path):
    exe = tmp_path / "my-chrome.exe"
    exe.write_text("")
    _set_chrome_path(monkeypatch, str(exe))
    assert export.find_browser() == exe


def test_missing_override_warns_and_falls_through(monkeypatch):
    # A stale INVESTO_CHROME must not be fatal — discovery continues.
    _set_chrome_path(monkeypatch, r"C:\nope\ghost.exe")
    monkeypatch.setattr(export, "_candidate_paths", lambda: [])
    monkeypatch.setattr(export.shutil, "which", lambda name: None)
    assert export.find_browser() is None  # fell through, didn't raise


def test_discovery_finds_an_installed_browser(monkeypatch, tmp_path):
    real = tmp_path / "chrome"
    real.write_text("")
    _set_chrome_path(monkeypatch, "")
    monkeypatch.setattr(export, "_candidate_paths", lambda: [tmp_path / "ghost", real])
    assert export.find_browser() == real


def test_discovery_falls_back_to_path(monkeypatch, tmp_path):
    real = tmp_path / "chromium"
    real.write_text("")
    _set_chrome_path(monkeypatch, "")
    monkeypatch.setattr(export, "_candidate_paths", lambda: [])
    monkeypatch.setattr(export.shutil, "which",
                        lambda name: str(real) if name == "chromium" else None)
    assert export.find_browser() == real


# --------------------------------------------------------------------------------------
# The Windows path quirk that a hand-built file:// URL gets wrong
# --------------------------------------------------------------------------------------
def test_windows_style_path_becomes_a_percent_escaped_file_uri():
    # resolve().as_uri() is the whole reason we don't concatenate "file://" + str(path).
    uri = Path("C:/a b/report.html").resolve().as_uri()
    assert uri.startswith("file:///")
    assert "%20" in uri  # the space is escaped, not left raw


# --------------------------------------------------------------------------------------
# Headless Chrome path — stubbed subprocess, never a real launch
# --------------------------------------------------------------------------------------
def test_chrome_pdf_reports_engine_and_writes_a_file(monkeypatch, tmp_path):
    browser = tmp_path / "chrome.exe"
    browser.write_text("")
    out = tmp_path / "out.pdf"

    def fake_run(cmd, **kwargs):
        # Chrome writes the PDF to the --print-to-pdf target; imitate that.
        target = next(a.split("=", 1)[1] for a in cmd if a.startswith("--print-to-pdf="))
        Path(target).write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(export.subprocess, "run", fake_run)
    engine = export._chrome_pdf(browser, "<html></html>", out, timeout=30)
    assert "headless" in engine
    assert out.read_bytes().startswith(b"%PDF")


def test_chrome_exit_zero_but_no_file_is_treated_as_failure(monkeypatch, tmp_path):
    # The load-bearing one: --print-to-pdf can exit 0 having written nothing. The return code
    # is not trustworthy; the file is.
    browser = tmp_path / "chrome.exe"
    browser.write_text("")
    monkeypatch.setattr(export.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, b"", b"boom"))
    with pytest.raises(export.PdfExportError):
        export._chrome_pdf(browser, "<html></html>", tmp_path / "out.pdf", timeout=30)


def test_chrome_uses_a_throwaway_profile_and_the_new_headless(monkeypatch, tmp_path):
    browser = tmp_path / "chrome.exe"
    browser.write_text("")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        target = next(a.split("=", 1)[1] for a in cmd if a.startswith("--print-to-pdf="))
        Path(target).write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(export.subprocess, "run", fake_run)
    export._chrome_pdf(browser, "<html></html>", tmp_path / "out.pdf", timeout=30)
    cmd = seen["cmd"]
    assert "--headless=new" in cmd
    assert any(a.startswith("--user-data-dir=") for a in cmd), "throwaway profile is mandatory"
    assert any(a.startswith("file:///") for a in cmd), "must pass a file:// URI"


def test_chrome_timeout_becomes_a_pdf_error(monkeypatch, tmp_path):
    browser = tmp_path / "chrome.exe"
    browser.write_text("")

    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(export.subprocess, "run", boom)
    with pytest.raises(export.PdfExportError, match="timed out"):
        export._chrome_pdf(browser, "<html></html>", tmp_path / "out.pdf", timeout=30)


# --------------------------------------------------------------------------------------
# The no-backend path gives an actionable message
# --------------------------------------------------------------------------------------
def test_no_backend_raises_with_all_three_remedies(monkeypatch, tmp_path):
    monkeypatch.setattr(export, "find_browser", lambda: None)

    def no_playwright(html, out, timeout):
        raise export._PlaywrightUnavailable("Playwright is not installed")

    monkeypatch.setattr(export, "_playwright_pdf", no_playwright)
    with pytest.raises(export.PdfExportError) as exc:
        export.html_to_pdf("<html></html>", tmp_path / "out.pdf")
    msg = str(exc.value)
    assert "Chrome" in msg
    assert "playwright install" in msg
    assert "INVESTO_CHROME" in msg


def test_html_to_pdf_prefers_chrome_when_present(monkeypatch, tmp_path):
    browser = tmp_path / "chrome.exe"
    browser.write_text("")
    monkeypatch.setattr(export, "find_browser", lambda: browser)
    monkeypatch.setattr(export, "_chrome_pdf", lambda *a, **k: "chrome.exe (headless)")
    engine, warnings = export.html_to_pdf("<html></html>", tmp_path / "out.pdf")
    assert engine == "chrome.exe (headless)"
    assert warnings == []


def test_html_to_pdf_falls_through_to_playwright_when_chrome_fails(monkeypatch, tmp_path):
    browser = tmp_path / "chrome.exe"
    browser.write_text("")
    monkeypatch.setattr(export, "find_browser", lambda: browser)

    def chrome_fails(*a, **k):
        raise export.PdfExportError("chrome broke")

    monkeypatch.setattr(export, "_chrome_pdf", chrome_fails)
    monkeypatch.setattr(export, "_playwright_pdf", lambda *a, **k: "playwright-chromium")
    engine, warnings = export.html_to_pdf("<html></html>", tmp_path / "out.pdf")
    assert engine == "playwright-chromium"
    assert any("Headless browser failed" in w for w in warnings)


# --------------------------------------------------------------------------------------
# Filenames and save entry points
# --------------------------------------------------------------------------------------
def test_default_filename_is_dated_and_filesystem_safe():
    r = _report()
    r.resolved.symbol = "M&M.NS"  # a real ticker with a shell-hostile character
    name = export.default_filename(r, "pdf")
    assert name.startswith("investo-M-M.NS-")
    assert name.endswith(".pdf")
    assert "&" not in name


def test_save_html_writes_and_creates_parents(tmp_path):
    out = export.save_html(_report(), tmp_path / "nested" / "dir" / "r.html")
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_save_html_with_a_directory_appends_the_default_name(tmp_path):
    out = export.save_html(_report(), tmp_path)
    assert out.parent == tmp_path
    assert out.name.startswith("investo-KPITTECH.NS-")


def test_save_pdf_writes_the_html_sidecar_even_when_the_engine_fails(monkeypatch, tmp_path):
    # A PDF failure must still leave a usable report on disk, not an empty hand.
    def fail(html, out, timeout=None):
        raise export.PdfExportError("no engine")

    monkeypatch.setattr(export, "html_to_pdf", fail)
    out = tmp_path / "kpit.pdf"
    with pytest.raises(export.PdfExportError):
        export.save_pdf(_report(), out)
    assert out.with_suffix(".html").exists(), "the .html sidecar should survive a PDF failure"


def test_save_pdf_returns_engine_and_path_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(export, "html_to_pdf",
                        lambda html, out, timeout=None: ("chrome (headless)", []))
    # html_to_pdf is stubbed, so nothing writes the .pdf; assert on the returned metadata.
    out, engine, warnings = export.save_pdf(_report(), tmp_path / "k.pdf")
    assert out.name == "k.pdf"
    assert engine == "chrome (headless)"
    assert out.with_suffix(".html").exists()
