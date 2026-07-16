"""CLI tests for `investo analyze` output routing (no network).

`analyze` is monkeypatched to a canned report, so these test argument routing and file/exit
behaviour, not the analysis. The old CLI shipped with none of this and had a silent precedence
bug where --html quietly suppressed --json.
"""

import json

import pytest

from investo import cli
from investo.models import AnalysisReport, CompanyProfile, TickerCandidate


@pytest.fixture(autouse=True)
def _canned_analyze(monkeypatch):
    report = AnalysisReport(
        query="KPIT Technologies",
        resolved=TickerCandidate(symbol="KPITTECH.NS", name="KPIT Technologies Limited"),
        profile=CompanyProfile(ticker="KPITTECH.NS", name="KPIT Technologies Limited"),
    )
    monkeypatch.setattr("investo.analysis.report.analyze", lambda query, market: report)
    return report


def _run(argv: list[str]) -> int:
    args = cli.build_parser().parse_args(argv)
    return args.func(args)


def test_no_output_flag_prints_the_terminal_report(capsys):
    assert _run(["analyze", "KPIT"]) == 0
    out = capsys.readouterr().out
    assert "KPIT Technologies Limited" in out
    assert not out.lstrip().startswith("{")  # not JSON


def test_json_flag_emits_valid_json(capsys):
    assert _run(["analyze", "KPIT", "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["query"] == "KPIT Technologies"


def test_html_flag_writes_a_file_and_creates_parents(tmp_path, capsys):
    target = tmp_path / "sub" / "dir" / "report.html"
    assert _run(["analyze", "KPIT", "--html", str(target)]) == 0
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert "Wrote HTML report" in capsys.readouterr().out


def test_bare_html_flag_uses_a_default_name(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert _run(["analyze", "KPIT", "--html"]) == 0
    written = list(tmp_path.glob("investo-KPITTECH.NS-*.html"))
    assert len(written) == 1


def test_json_and_html_compose_neither_is_discarded(tmp_path, capsys):
    # The precedence-bug regression: the old CLI let --html silently suppress --json.
    target = tmp_path / "r.html"
    assert _run(["analyze", "KPIT", "--json", "--html", str(target)]) == 0
    out = capsys.readouterr().out
    assert json.loads(out.split("Wrote HTML report")[0])  # JSON was printed
    assert target.exists()  # and the HTML was written


def test_pdf_success_reports_the_engine(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("investo.export.save_pdf",
                        lambda report, path: (tmp_path / "k.pdf", "chrome (headless)", []))
    assert _run(["analyze", "KPIT", "--pdf", str(tmp_path / "k.pdf")]) == 0
    assert "chrome (headless)" in capsys.readouterr().out


def test_pdf_failure_exits_two_and_keeps_the_html(tmp_path, monkeypatch, capsys):
    from investo.export import PdfExportError, save_html

    # Mirror the real save_pdf contract: write the .html sidecar, then fail on the PDF engine.
    def stub(report, path):
        save_html(report, tmp_path / "k.html")
        raise PdfExportError("no engine available; run playwright install chromium")

    monkeypatch.setattr("investo.export.save_pdf", stub)
    code = _run(["analyze", "KPIT", "--pdf", str(tmp_path / "k.pdf")])
    err = capsys.readouterr().err
    assert code == 2
    assert "PDF export failed" in err
    assert (tmp_path / "k.html").exists()  # a failed PDF still leaves a report


def test_pdf_warnings_go_to_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("investo.export.save_pdf",
                        lambda report, path: (tmp_path / "k.pdf", "playwright-chromium",
                                              ["Headless browser failed; trying Playwright."]))
    assert _run(["analyze", "KPIT", "--pdf", str(tmp_path / "k.pdf")]) == 0
    captured = capsys.readouterr()
    assert "Headless browser failed" in captured.err
    assert "playwright-chromium" in captured.out
