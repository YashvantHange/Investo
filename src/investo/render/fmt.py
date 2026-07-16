"""Shared value formatters for every renderer.

These lived in three places (``relative._fmt``, ``cli._metric``, ``report_html._metric``), each
with its own hardcoded set of ratio names — so a new ratio metric rendered as ``2500.0%`` in two
of the three. They live here once, and units come from the data rather than from guessing at a
metric's name.
"""

from __future__ import annotations

from html import escape as _escape

# Indian financial reporting counts in crore (10^7); a rupee figure in millions reads as noise
# to the audience this tool is built for.
_CRORE = 1e7
_BILLION = 1e9
_MILLION = 1e6

EM_DASH = "—"

# Dingbats and status glyphs that upstream analysis strings sometimes carry ("Buffett ✓ …",
# "→ FAIL"). In a document meant to read as a research publication they are the single clearest
# tell of a generated artifact, so the renderer strips them at the boundary rather than trusting
# every producer to stay clean. A few are rewritten to words; the rest are dropped. Trend ▲/▼ are
# NOT here — they are placed deliberately by the renderer inside the trend column.
_GLYPH_WORDS = {
    "✓": "", "✔": "", "☑": "", "✅": "",
    "✗": "", "✘": "", "✖": "", "❌": "",
    "⚠": "", "⚠️": "",
    "→": "—", "➡": "—", "⇒": "—",
    "↑": "up", "⬆": "up", "▲": "up",
    "↓": "down", "⬇": "down", "▼": "down",
}
# Everything in the emoji/dingbat/arrow blocks, stripped wholesale as a backstop.
_DINGBAT_RANGES = (
    (0x2190, 0x21FF),   # arrows
    (0x2300, 0x23FF),   # misc technical
    (0x2460, 0x24FF),   # enclosed alphanumerics
    (0x2500, 0x27BF),   # box drawing … dingbats
    (0x2B00, 0x2BFF),   # misc symbols and arrows
    (0x1F000, 0x1FAFF),  # emoji planes
    (0xFE00, 0xFE0F),   # variation selectors
)


def _is_dingbat(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _DINGBAT_RANGES)


def clean(text: str) -> str:
    """Strip status glyphs and dingbats from an upstream string, rewriting a few to words.

    Presentation belongs to the renderer: an analysis module that writes "Buffett ✓ …" or
    "… → FAIL" states a fact, and the fact survives without the glyph.
    """
    if not text:
        return text
    out = []
    for ch in text:
        if ch in _GLYPH_WORDS:
            word = _GLYPH_WORDS[ch]
            out.append(f" {word} " if word else " ")
        elif _is_dingbat(ch):
            out.append(" ")
        else:
            out.append(ch)
    # Collapse the whitespace a dropped glyph leaves behind ("Buffett ✓ Moat" -> "Buffett Moat").
    return " ".join("".join(out).split())


def esc(text: object) -> str:
    """HTML-escape any value, cleaned of dingbats; None renders as an em dash, not 'None'."""
    if text is None:
        return EM_DASH
    return _escape(clean(str(text)))


def money(value: float | None, currency: str | None = None) -> str:
    """Format a currency amount in the units its audience actually uses."""
    if value is None:
        return EM_DASH
    cur = (currency or "").upper()
    if cur == "INR":
        if abs(value) >= _CRORE:
            return f"₹{value / _CRORE:,.0f} Cr"
        return f"₹{value:,.0f}"
    symbol = "$" if cur == "USD" else ""
    suffix = "" if symbol else f" {cur}".rstrip()
    if abs(value) >= _BILLION:
        return f"{symbol}{value / _BILLION:,.1f}B{suffix}"
    if abs(value) >= _MILLION:
        return f"{symbol}{value / _MILLION:,.1f}M{suffix}"
    return f"{symbol}{value:,.2f}{suffix}"


def price(value: float | None, currency: str | None = None) -> str:
    """A share price: never abbreviated, always two decimals."""
    if value is None:
        return EM_DASH
    cur = (currency or "").upper()
    symbol = {"INR": "₹", "USD": "$"}.get(cur, "")
    suffix = "" if symbol else f" {cur}".rstrip()
    return f"{symbol}{value:,.2f}{suffix}"


def pct(value: float | None, decimals: int = 1) -> str:
    """A fraction as a percentage: 0.153 -> '15.3%'."""
    return EM_DASH if value is None else f"{value:.{decimals}%}"


def signed_pct(value: float | None, decimals: int = 1) -> str:
    """A change, where the sign carries the meaning: 0.153 -> '+15.3%'."""
    return EM_DASH if value is None else f"{value:+.{decimals}%}"


def ratio(value: float | None, decimals: int = 1) -> str:
    """A multiple: 23.7 -> '23.7x'."""
    return EM_DASH if value is None else f"{value:.{decimals}f}x"


def num(value: float | None, decimals: int = 2) -> str:
    return EM_DASH if value is None else f"{value:,.{decimals}f}"


def metric(unit: str, value: float | None) -> str:
    """Format a relative-comparison value from its **declared** unit.

    The unit travels on the metric because inferring it from the name is how EV/EBITDA ends up
    rendered as 3000%.
    """
    if value is None:
        return EM_DASH
    return ratio(value) if unit == "ratio" else pct(value)


def band(percentile: float | None) -> str:
    """Qualitative standing from a favourable-side percentile (high always means good)."""
    if percentile is None:
        return EM_DASH
    if percentile >= 0.75:
        return "top quartile"
    if percentile >= 0.5:
        return "above median"
    if percentile >= 0.25:
        return "below median"
    return "bottom quartile"


def tone(percentile: float | None) -> str:
    """Semantic class for a percentile: drives typography, never a coloured pill."""
    if percentile is None:
        return "flat"
    if percentile >= 0.75:
        return "pos"
    if percentile >= 0.5:
        return "pos-weak"
    if percentile >= 0.25:
        return "neg-weak"
    return "neg"
