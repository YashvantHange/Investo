"""The evidence layer — deterministic confidence, provenance and per-module quality.

Every analysis module reports *how much to trust it*, so a downstream agent can weight
conclusions correctly. Confidence is **computed, never asserted**: it is a transparent
function of three inputs, documented here and unit-tested.

    confidence = source_reliability * coverage_factor * history_factor  (+ agreement bonus)

- *source reliability* — how authoritative the underlying data is (an exchange filing beats a
  scraped estimate). When several sources back a module we take the best.
- *coverage_factor* — fraction of the fields a module expects that were actually present,
  softened so a couple of gaps don't collapse the score (``0.4 + 0.6 * coverage``).
- *history_factor* — for trend-based checks, how many years of history backed it
  (``0.5 + 0.5 * min(1, years / target)``); ``None`` for point-in-time checks (no penalty).
- *agreement bonus* — a small boost when two independent sources corroborate a figure.

The result is a ``Confidence`` with a 0-1 ``score``, a ``High/Medium/Low`` ``tier`` and a
plain-language ``reason``. This module is the single source of truth reused everywhere, exactly
as ``scoring.py`` centralizes the bucket scorers.
"""

from __future__ import annotations

from ..models import Confidence, ConfidenceTier, EvidenceMeta, Provenance

# Canonical provenance source labels — use these constants (not raw strings) across modules so
# labels stay consistent and always match the reliability table below.
SRC_NSE_FILING = "NSE Shareholding Filing"
SRC_BSE_FILING = "BSE Shareholding Filing"
SRC_SEC = "SEC EDGAR"
SRC_STATEMENTS = "Annual Reports"  # figures derived from reported financial statements
SRC_YAHOO = "Yahoo Finance"
SRC_CURATED = "Curated (Investo)"
SRC_ANALYST = "Analyst Estimates"
SRC_NEWS = "News"
SRC_HEURISTIC = "Model Heuristic"

# Source reliability weights (0-1). Keys are lower-cased substrings matched against a source
# label; the *highest* matching weight wins (order-independent). Tuned so an exchange filing
# outranks Yahoo, which outranks curated data, which outranks a pure heuristic.
SOURCE_WEIGHTS: dict[str, float] = {
    "filing": 0.95,  # NSE/BSE shareholding filings
    "edgar": 0.95,
    "sec ": 0.95,
    "annual report": 0.90,
    "statement": 0.90,
    "yahoo": 0.80,
    "curated": 0.70,
    "analyst": 0.65,
    "news": 0.55,
    "heuristic": 0.50,
    "derived": 0.55,
}
_DEFAULT_SOURCE_WEIGHT = 0.60

# Tier thresholds on the 0-1 confidence score.
_TIER_HIGH = 0.80
_TIER_MEDIUM = 0.60


def source_weight(source: str | None) -> float:
    """Reliability weight for a source label (case-insensitive; highest matching key wins)."""
    if not source:
        return _DEFAULT_SOURCE_WEIGHT
    low = source.lower()
    matches = [weight for key, weight in SOURCE_WEIGHTS.items() if key in low]
    return max(matches) if matches else _DEFAULT_SOURCE_WEIGHT


def tier(score: float) -> ConfidenceTier:
    """Map a 0-1 confidence score to its High/Medium/Low tier."""
    if score >= _TIER_HIGH:
        return "High"
    if score >= _TIER_MEDIUM:
        return "Medium"
    return "Low"


def confidence(
    *,
    sources: list[Provenance] | list[str] | None = None,
    coverage: float | None = None,
    history_years: int | None = None,
    target_years: int = 5,
    corroborated: bool = False,
    reason: str | None = None,
) -> Confidence:
    """Compute a :class:`Confidence` from source reliability, coverage and history depth.

    All inputs are optional; each missing input is treated neutrally (no penalty) so the
    formula degrades gracefully. See the module docstring for the exact factors.
    """
    labels = _source_labels(sources)
    best_source = max((source_weight(s) for s in labels), default=_DEFAULT_SOURCE_WEIGHT)

    coverage_factor = 1.0 if coverage is None else 0.4 + 0.6 * _clamp01(coverage)

    if history_years is None:
        history_factor = 1.0
    else:
        history_factor = 0.5 + 0.5 * min(1.0, history_years / max(target_years, 1))

    score = best_source * coverage_factor * history_factor
    if corroborated or len(labels) >= 2:
        score = min(1.0, score + 0.05)  # independent corroboration bonus
    score = round(_clamp01(score), 3)

    return Confidence(score=score, tier=tier(score), reason=reason or _auto_reason(
        labels, coverage, history_years, target_years, corroborated or len(labels) >= 2))


def aggregate(metas: list[EvidenceMeta | None], notes: list[str] | None = None) -> EvidenceMeta:
    """Roll several modules' :class:`EvidenceMeta` into one report-level quality block."""
    present = [m for m in metas if m is not None]
    conf_scores = [m.confidence.score for m in present if m.confidence]
    coverages = [m.data_coverage for m in present if m.data_coverage is not None]
    sources: list[Provenance] = []
    seen: set[tuple[str, str | None]] = set()
    for m in present:
        for p in m.sources:
            key = (p.source, p.detail)
            if key not in seen:
                seen.add(key)
                sources.append(p)
    missing = sorted({f for m in present for f in m.missing_fields})
    as_of = max((m.as_of for m in present if m.as_of), default=None)

    score = round(sum(conf_scores) / len(conf_scores), 3) if conf_scores else 0.5
    coverage = round(sum(coverages) / len(coverages), 3) if coverages else None
    conf = Confidence(score=score, tier=tier(score),
                      reason=f"blended across {len(present)} module(s)")
    return EvidenceMeta(
        confidence=conf, data_coverage=coverage, sources=sources, source_count=len(sources),
        missing_fields=missing, as_of=as_of, notes=list(notes or []),
    )


def build_meta(
    *,
    sources: list[Provenance] | None = None,
    present: int | None = None,
    expected: int | None = None,
    missing_fields: list[str] | None = None,
    history_years: int | None = None,
    target_years: int = 5,
    as_of: str | None = None,
    notes: list[str] | None = None,
    reason: str | None = None,
) -> EvidenceMeta:
    """Assemble a module's :class:`EvidenceMeta`, computing coverage and confidence.

    ``present``/``expected`` give data coverage; ``missing_fields`` is surfaced verbatim so a
    caller can see exactly what was unavailable.
    """
    provs = list(sources or [])
    coverage: float | None = None
    if expected:
        derived_present = present if present is not None else (expected - len(missing_fields or []))
        coverage = _clamp01(derived_present / expected) if expected else None

    conf = confidence(
        sources=provs,
        coverage=coverage,
        history_years=history_years,
        target_years=target_years,
        reason=reason,
    )
    latest = as_of or _latest_as_of(provs)
    return EvidenceMeta(
        confidence=conf,
        data_coverage=round(coverage, 3) if coverage is not None else None,
        sources=provs,
        source_count=len(provs),
        missing_fields=list(missing_fields or []),
        as_of=latest,
        notes=list(notes or []),
    )


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _source_labels(sources: list[Provenance] | list[str] | None) -> list[str]:
    if not sources:
        return []
    labels: list[str] = []
    for s in sources:
        if isinstance(s, Provenance):
            labels.append(s.source)
        elif s:
            labels.append(str(s))
    return labels


def _latest_as_of(sources: list[Provenance]) -> str | None:
    dates = [s.as_of for s in sources if s.as_of]
    return max(dates) if dates else None


def _auto_reason(
    labels: list[str],
    coverage: float | None,
    history_years: int | None,
    target_years: int,
    corroborated: bool,
) -> str:
    parts: list[str] = []
    if labels:
        # De-duplicate while preserving order for a readable "source A, source B" phrase.
        seen: list[str] = []
        for label in labels:
            if label not in seen:
                seen.append(label)
        parts.append("source: " + ", ".join(seen))
    if history_years is not None:
        parts.append(f"{history_years}y history")
    if coverage is not None:
        parts.append(f"{coverage:.0%} field coverage")
    if corroborated:
        parts.append("cross-source agreement")
    return "; ".join(parts) if parts else "limited evidence"
