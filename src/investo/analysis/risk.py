"""Risk assessment: leverage, market, currency, concentration and regulatory exposure.

Produces a signal pack + a 0-5 heuristic risk score (higher = safer) reusing
:func:`scoring.score_risk`. Currency/customer-concentration/regulatory items are sector- and
data-informed hints for the host LLM to expand.
"""

from __future__ import annotations

from typing import Any

from ..models import Ratios, RiskSignals
from ..sources import data
from .scoring import score_risk

# Export-heavy Indian sectors carry USD/INR translation exposure.
_FX_EXPOSED_SECTORS = {"Technology", "Healthcare"}

_REGULATORY_BY_SECTOR = {
    "Financial Services": ["RBI / SEBI regulation", "Capital-adequacy & NPA norms"],
    "Healthcare": ["USFDA inspections", "NPPA price controls"],
    "Energy": ["Regulated pricing / subsidies", "Environmental & emission norms"],
    "Utilities": ["Regulated tariffs", "DISCOM payment cycles"],
    "Communication Services": ["Spectrum & licensing (DoT/TRAI)"],
    "Basic Materials": ["Environmental clearances", "Mining & export duties"],
}


def risk_assessment(
    symbol: str,
    ratios: Ratios | None = None,
    info: dict[str, Any] | None = None,
) -> RiskSignals:
    from .ratios import compute_ratios

    if info is None:
        info = data.get_info(symbol)
    if ratios is None:
        ratios = compute_ratios(symbol, info=info)

    sector = info.get("sector")
    normalized, _rationale, _drivers = score_risk(ratios)
    score5 = round((normalized if normalized is not None else 0.5) * 5.0, 1)

    signals: list[str] = []
    if ratios.debt_to_equity is not None:
        if ratios.debt_to_equity > 1.0:
            signals.append(f"Elevated leverage: debt/equity {ratios.debt_to_equity:.2f}.")
        else:
            signals.append(f"Manageable leverage: debt/equity {ratios.debt_to_equity:.2f}.")
    if ratios.interest_coverage is not None and ratios.interest_coverage < 3.0:
        signals.append(f"Thin interest coverage ({ratios.interest_coverage:.1f}x) -- debt-servicing risk.")
    if ratios.beta is not None and ratios.beta > 1.3:
        signals.append(f"High market sensitivity (beta {ratios.beta:.2f}).")

    currency_exposure = None
    if sector in _FX_EXPOSED_SECTORS:
        currency_exposure = "High USD revenue share -> INR appreciation is a headwind."
        signals.append(currency_exposure)

    regulatory_flags = _REGULATORY_BY_SECTOR.get(sector or "", [])

    if not signals:
        signals.append("No major quantitative risk flags; watch customer concentration & competition.")

    return RiskSignals(
        ticker=symbol.upper(),
        debt_to_equity=ratios.debt_to_equity,
        interest_coverage=ratios.interest_coverage,
        beta=ratios.beta,
        currency_exposure=currency_exposure,
        customer_concentration="Not available from public ratios; check the annual report.",
        regulatory_flags=regulatory_flags,
        risk_score=score5,
        signals=signals,
        note=f"Heuristic safety score {score5}/5 (higher = safer).",
    )
