"""Turn a rendered report into a file — HTML always, PDF when a browser engine is available.

PDF generation deliberately takes on **no required dependency**. It shells out to a headless
Chrome/Edge/Chromium if one is installed (the common case — most machines have one), falls back to
a Playwright-managed Chromium if that package is present, and otherwise raises an error that tells
the user exactly how to fix it. The HTML is always written first, so a PDF failure still leaves a
usable artifact on disk rather than nothing.

Four details below are load-bearing and each was a real bug in an earlier draft; they are called
out at their site.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .config import CONFIG

if TYPE_CHECKING:
    from .models import AnalysisReport

_log = logging.getLogger("investo.export")

# Sanitised into default filenames. `M&M.NS` is a real ticker, so `&` must not survive into a path.
_UNSAFE = str.maketrans(dict.fromkeys('<>:"/\\|?*&%', "-"))


class PdfExportError(RuntimeError):
    """Raised when no PDF backend could produce a file. The message names the remedies."""


# --------------------------------------------------------------------------------------
# Browser discovery
# --------------------------------------------------------------------------------------
def _candidate_paths() -> list[Path]:
    """Platform install locations for a Chromium-family browser, most-preferred first."""
    out: list[Path] = []
    if sys.platform == "win32":
        roots = [os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                 os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA", "")]
        rel = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
            r"Chromium\Application\chrome.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
        ]
        out = [Path(root) / r for root in roots if root for r in rel]
    elif sys.platform == "darwin":
        out = [Path(p) for p in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        )]
    else:
        out = [Path(p) for p in (
            "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium", "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge", "/usr/bin/brave-browser",
        )]
    return out


def find_browser() -> Path | None:
    """Locate a headless-capable browser: the configured override, an install path, then PATH.

    An override that is set but missing is a warning, not a fatal error — we still try the other
    routes rather than dying on a stale env var.
    """
    override = CONFIG.chrome_path
    if override:
        p = Path(override)
        if p.exists():
            return p
        _log.warning("INVESTO_CHROME=%s does not exist; falling back to discovery", override)

    for path in _candidate_paths():
        if path.exists():
            return path

    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "chrome", "msedge", "microsoft-edge", "brave", "brave-browser"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


# --------------------------------------------------------------------------------------
# HTML -> PDF
# --------------------------------------------------------------------------------------
def html_to_pdf(html: str, out_path: Path, *, timeout: float | None = None) -> tuple[str, list[str]]:
    """Render ``html`` to ``out_path`` as PDF. Returns (engine, warnings); raises on total failure.

    Tries headless Chrome/Edge, then Playwright, then gives up with an actionable message.
    """
    timeout = CONFIG.pdf_timeout if timeout is None else timeout
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    browser = find_browser()
    if browser is not None:
        try:
            return _chrome_pdf(browser, html, out_path, timeout), warnings
        except PdfExportError as exc:
            warnings.append(f"Headless browser failed ({exc}); trying Playwright.")

    try:
        return _playwright_pdf(html, out_path, timeout), warnings
    except _PlaywrightUnavailable as exc:
        warnings.append(str(exc))

    raise PdfExportError(
        "No PDF engine available. Do one of:\n"
        "  • install Google Chrome, Microsoft Edge or Chromium, or\n"
        "  • pip install 'investo[pdf]' && playwright install chromium, or\n"
        "  • set INVESTO_CHROME to a Chrome/Edge executable.\n"
        "The HTML report was still written."
    )


def _chrome_pdf(browser: Path, html: str, out_path: Path, timeout: float) -> str:
    """Headless Chrome/Edge via --print-to-pdf. Four non-obvious requirements, each marked."""
    # (1) A TemporaryDirectory with our own file inside it — NOT NamedTemporaryFile. On Windows a
    #     still-open NamedTemporaryFile cannot be reopened by path, which is exactly what Chrome
    #     needs to do.
    with tempfile.TemporaryDirectory(prefix="investo-pdf-") as tmp:
        tmp_dir = Path(tmp)
        src = tmp_dir / "report.html"
        src.write_text(html, encoding="utf-8")
        profile = tmp_dir / "profile"  # (3) throwaway profile, see below

        # (2) resolve().as_uri() builds file:///C:/... and percent-escapes spaces. A hand-built
        #     "file://" + str(path) gets both the slashes and the spaces wrong on Windows.
        url = src.resolve().as_uri()

        cmd = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            # (3) A throwaway --user-data-dir is mandatory: without it, headless can attach to an
            #     already-running browser's profile and silently produce nothing. This is the
            #     single most common "works in CI, not on my machine" cause.
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out_path}",
            url,
        ]
        # --no-sandbox only where it's needed (root in a Linux container); never on Win/macOS.
        if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")

        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise PdfExportError(f"{browser.name} timed out after {timeout:.0f}s") from exc
        except OSError as exc:
            raise PdfExportError(f"could not launch {browser.name}: {exc}") from exc

        # (4) Do NOT trust the return code. Chrome can exit 0 having written nothing; the only
        #     reliable check is that the file exists and is non-empty.
        if not out_path.exists() or out_path.stat().st_size == 0:
            tail = proc.stderr.decode("utf-8", "replace")[-300:].strip()
            raise PdfExportError(f"{browser.name} produced no PDF"
                                 f"{f' — {tail}' if tail else ''}")
    return f"{browser.name} (headless)"


class _PlaywrightUnavailable(RuntimeError):
    """Playwright isn't installed, or its browser binary hasn't been downloaded."""


def _playwright_pdf(html: str, out_path: Path, timeout: float) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _PlaywrightUnavailable(
            "Playwright is not installed (pip install 'investo[pdf]')."
        ) from exc

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                # Let the document's @page rule own the sheet size and margins (A4 + running
                # header/footer room) rather than Playwright's defaults, so the PDF matches print.
                page.pdf(path=str(out_path), print_background=True, prefer_css_page_size=True,
                         margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # The distinctive "download the browser" error is recoverable-with-instructions, so it is
        # reported as unavailable (fall through to the actionable message) rather than a hard fail.
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            raise _PlaywrightUnavailable(
                "Playwright is installed but its Chromium isn't (run: playwright install chromium)."
            ) from exc
        raise PdfExportError(f"Playwright failed to render the PDF: {msg}") from exc

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise PdfExportError("Playwright produced no PDF.")
    return "playwright-chromium"


# --------------------------------------------------------------------------------------
# Filenames and the save entry points (used by both the CLI and the MCP tool)
# --------------------------------------------------------------------------------------
def default_filename(report: AnalysisReport, ext: str) -> str:
    """A stable, filesystem-safe default name: investo-<SYMBOL>-<YYYY-MM-DD>.<ext>."""
    from datetime import date

    sym = (report.resolved.symbol if report.resolved else None) or report.query
    sym = sym.translate(_UNSAFE).strip("-") or "report"
    return f"investo-{sym}-{date.today().isoformat()}.{ext.lstrip('.')}"


def _resolve_out(report: AnalysisReport, path: str | os.PathLike | None, ext: str) -> Path:
    """Turn a user path (or None, or a directory) into a concrete file path, creating parents."""
    if path is None:
        out = Path.cwd() / default_filename(report, ext)
    else:
        out = Path(path).expanduser()
        if out.is_dir() or str(path).endswith(("/", "\\")):
            out = out / default_filename(report, ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def save_html(report: AnalysisReport, path: str | os.PathLike | None = None) -> Path:
    from .render import render_html

    out = _resolve_out(report, path, "html")
    out.write_text(render_html(report), encoding="utf-8")
    return out


def save_pdf(
    report: AnalysisReport,
    path: str | os.PathLike | None = None,
    *,
    keep_html: bool = True,
) -> tuple[Path, str, list[str]]:
    """Write a PDF (and, by default, an .html sidecar). Returns (pdf_path, engine, warnings).

    The HTML is written first and on purpose: if the PDF engine fails, the caller still has a
    usable report on disk rather than an empty hand.
    """
    from .render import render_html

    out = _resolve_out(report, path, "pdf")
    html = render_html(report)
    if keep_html:
        out.with_suffix(".html").write_text(html, encoding="utf-8")
    engine, warnings = html_to_pdf(html, out)
    return out, engine, warnings
