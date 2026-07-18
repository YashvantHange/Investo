"""The 0-100 investment rating: eleven weighted buckets.

Weights (out of 100; ESG is an optional 11th that renormalizes the total):

    Growth 15 | Profitability 17 | Cash Flow 10 | Balance Sheet 11 | Valuation 10
    Moat 12 | Management 10 | Industry 5 | Innovation 5 | Risk 5 | (ESG 5, optional)

Valuation is quality-aware: the acceptable multiple ceilings widen with the company's economics
(returns, margins, growth), and net cash lowers the effective equity multiple -- so a proven,
cash-rich compounder is not floored for trading at a premium.

Financial buckets are computed from ratios/DCF. Qualitative buckets (moat, management,
industry, innovation, risk) use transparent heuristics from the same data; the host LLM can
refine them with evidence (news, filings) and the composite recomputes deterministically.

Each scorer returns a *normalized* value in [0, 1]; the bucket's points = normalized * weight.
These scorers are the single source of truth reused by moat.py / risk.py.
"""

from __future__ import annotations

from ..models import DCFResult, Ratios, Score, ScoreBucket

# Bucket weights (core ten sum to 100). Leans on durable quality over absolute cheapness:
# Valuation is a lighter cross-check (10) while Profitability (17), Moat (12) and the net-cash-
# aware Balance Sheet (11) carry more.
WEIGHTS = {
    "Growth": 15.0,
    "Profitability": 17.0,
    "Cash Flow": 10.0,
    "Balance Sheet": 11.0,
    "Valuation": 10.0,
    "Competitive Moat": 12.0,
    "Management": 10.0,
    "Industry Outlook": 5.0,
    "Innovation": 5.0,
    "Risk": 5.0,
}
ESG_WEIGHT = 5.0

_FINANCIAL_SECTORS = {"Financial Services", "Financials", "Banks", "Insurance"}


# --------------------------------------------------------------------------------------
# Normalization helpers
# --------------------------------------------------------------------------------------
def _lin(x: float | None, lo: float, hi: float) -> float | None:
    """Higher-is-better linear map to [0, 1]."""
    if x is None or hi == lo:
        return None
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _inv(x: float | None, lo: float, hi: float) -> float | None:
    """Lower-is-better linear map to [0, 1] (x=lo -> 1, x=hi -> 0)."""
    if x is None or hi == lo:
        return None
    return max(0.0, min(1.0, (hi - x) / (hi - lo)))


def _avg(vals: list[float | None]) -> float | None:
    vs = [v for v in vals if v is not None]
    return sum(vs) / len(vs) if vs else None


def _pct(x: float | None) -> str:
    return f"{x:.1%}" if x is not None else "n/a"


def _quality_factor(r: Ratios) -> float:
    """Business-quality read in [0, 1] from returns, margins and growth.

    Four independent signals so the factor can't be gamed by leverage-inflated ROE (operating
    margin) or a hollow top line (EPS CAGR blended into revenue growth). Each `_lin` clamps, so a
    single sky-high metric can't dominate. Reusable across scorers; neutral 0.5 when data is absent.
    """
    growth_blend = _avg([r.revenue_cagr_3y, r.eps_cagr_3y])
    if growth_blend is None:
        growth_blend = r.revenue_growth_yoy
    q = _avg([
        _lin(r.roe, 0.10, 0.30),
        _lin(r.roce, 0.12, 0.35),
        _lin(r.operating_margin, 0.05, 0.30),
        _lin(growth_blend, 0.0, 0.20),
    ])
    return q if q is not None else 0.5


# --------------------------------------------------------------------------------------
# Per-bucket scorers -> normalized [0,1]
# --------------------------------------------------------------------------------------
def score_growth(r: Ratios) -> tuple[float | None, str, dict]:
    n = _avg([
        _lin(r.revenue_growth_yoy, -0.05, 0.25),
        _lin(r.revenue_cagr_3y, 0.0, 0.20),
        _lin(r.earnings_growth_yoy, -0.05, 0.25),
    ])
    rat = f"revenue YoY {_pct(r.revenue_growth_yoy)}, 3y CAGR {_pct(r.revenue_cagr_3y)}"
    return n, rat, {"revenue_growth_yoy": r.revenue_growth_yoy, "revenue_cagr_3y": r.revenue_cagr_3y,
                    "earnings_growth_yoy": r.earnings_growth_yoy}


def score_profitability(r: Ratios) -> tuple[float | None, str, dict]:
    n = _avg([
        _lin(r.roe, 0.05, 0.25),
        _lin(r.roce, 0.08, 0.30),
        _lin(r.net_margin, 0.02, 0.25),
        _lin(r.operating_margin, 0.05, 0.30),
    ])
    rat = f"ROE {_pct(r.roe)}, ROCE {_pct(r.roce)}, net margin {_pct(r.net_margin)}"
    return n, rat, {"roe": r.roe, "roce": r.roce, "net_margin": r.net_margin}


def score_cashflow(r: Ratios) -> tuple[float | None, str, dict]:
    n = _avg([
        _lin(r.fcf_margin, 0.0, 0.20),
        _lin(r.ocf_to_ebitda, 0.5, 1.2),
    ])
    rat = f"FCF margin {_pct(r.fcf_margin)}, OCF/EBITDA {r.ocf_to_ebitda:.2f}" if r.ocf_to_ebitda else \
          f"FCF margin {_pct(r.fcf_margin)}"
    return n, rat, {"fcf_margin": r.fcf_margin, "ocf_to_ebitda": r.ocf_to_ebitda}


def score_debt(r: Ratios, sector: str | None = None) -> tuple[float | None, str, dict]:
    """Balance-sheet strength: leverage, liquidity and net-cash position (higher = stronger)."""
    is_financial = sector in _FINANCIAL_SECTORS
    parts = [
        _lin(r.interest_coverage, 2.0, 12.0),
        _lin(r.current_ratio, 1.0, 2.5),
    ]
    if not is_financial:  # leverage is structurally high for banks/NBFCs; don't penalize
        parts.append(_inv(r.debt_to_equity, 0.0, 2.0))
        # Signed net-cash term: net debt (-20% of m.cap) drags below the debt-free midpoint,
        # a fortress net-cash pile (+20%) lifts it -- so leveraged / debt-free / net-cash names
        # are separated. (Skipped for financials, where cash and debt are the business.)
        parts.append(_lin(r.net_cash_to_market_cap, -0.20, 0.20))
    n = _avg(parts)
    de = "excluded (financial sector)" if is_financial else \
         (f"{r.debt_to_equity:.2f}" if r.debt_to_equity is not None else "n/a")
    cov = f"{r.interest_coverage:.1f}x" if r.interest_coverage is not None else "n/a"
    rat = f"debt/equity {de}, interest coverage {cov}"
    if not is_financial and r.net_cash_to_market_cap is not None:
        label = "net cash" if r.net_cash_to_market_cap >= 0 else "net debt"
        rat += f", {label} {_pct(abs(r.net_cash_to_market_cap))} of m.cap"
    return n, rat, {"debt_to_equity": r.debt_to_equity, "interest_coverage": r.interest_coverage,
                    "current_ratio": r.current_ratio,
                    "net_cash_to_market_cap": r.net_cash_to_market_cap}


def score_valuation(r: Ratios, dcf: DCFResult | None = None) -> tuple[float | None, str, dict]:
    q = _quality_factor(r)
    # Ceilings widen *quadratically* with quality: average names keep today's ceilings (40 / 8 / 25);
    # only exceptional quality unlocks real headroom -- so a proven compounder isn't floored for a
    # premium multiple, while a low-quality expensive name still is.
    qf = q * q
    pe_hi = 40.0 + qf * 35.0
    pb_hi = 8.0 + qf * 7.0
    ev_hi = 25.0 + qf * 15.0
    # Ex-cash equity multiples: net cash lowers the effective P/E and P/B (dampened so a cash-heavy
    # balance sheet helps without a runaway boost; net debt raises them). EV/EBITDA is already
    # cash-adjusted, so it's left alone to avoid double-counting.
    ncm = max(-0.5, min(0.8, r.net_cash_to_market_cap or 0.0))
    cash_factor = 1.0 - 0.5 * ncm
    eff_pe = r.pe * cash_factor if r.pe is not None else None
    eff_pb = r.pb * cash_factor if r.pb is not None else None
    multiples = _avg([
        _inv(eff_pe, 8.0, pe_hi),
        _inv(eff_pb, 1.0, pb_hi),
        _inv(r.ev_ebitda, 6.0, ev_hi),
        _inv(r.peg, 1.0, 3.0) if (r.peg is not None and r.peg > 0) else None,
    ])
    mos = dcf.margin_of_safety if dcf else None
    dcf_score = None
    if mos is not None:
        # Recentred so fair value (mos~0) scores ~0.5; clamp: DCF unreliable for capex-heavy names.
        dcf_score = _lin(max(-1.0, min(0.7, mos)), -0.4, 0.4)
    # Multiples dominate (0.70); DCF is an assumption-sensitive cross-check (0.30).
    n: float | None
    if multiples is not None and dcf_score is not None:
        n = 0.70 * multiples + 0.30 * dcf_score
    else:
        n = multiples if multiples is not None else dcf_score
    # Rationale: make the quality-aware assessment explicit rather than reading as a blind penalty.
    pe = f"{r.pe:.1f}" if r.pe is not None else "n/a"
    rat = f"P/E {pe}, P/B {r.pb:.1f}" if r.pb is not None else f"P/E {pe}"
    premium = (r.pe is not None and r.pe > 40) or (r.pb is not None and r.pb > 8)
    if premium and q >= 0.66:
        rat += (" - premium multiples assessed relative to strong quality "
                "(ROE/margins/growth), which justifies part of the premium")
    if r.net_cash_to_market_cap is not None and r.net_cash_to_market_cap > 0.05:
        rat += f", net cash {_pct(r.net_cash_to_market_cap)} of m.cap"
    if mos is not None:
        rat += f", DCF margin of safety {_pct(mos)}"
    return n, rat, {"pe": r.pe, "pb": r.pb, "ev_ebitda": r.ev_ebitda,
                    "quality_factor": round(q, 3),
                    "net_cash_to_market_cap": r.net_cash_to_market_cap,
                    "dcf_margin_of_safety": mos}


def score_moat(r: Ratios, market_share_proxy: float | None = None) -> tuple[float | None, str, dict]:
    # Gross margin is not meaningful for banks/financials (reported as 0) -> treat as N/A.
    gm = r.gross_margin if (r.gross_margin and r.gross_margin > 0) else None
    n = _avg([
        _lin(gm, 0.15, 0.60),
        _lin(r.roic, 0.08, 0.25),
        _lin(r.net_margin, 0.05, 0.30),  # pricing power / durability
        _lin(market_share_proxy, 0.10, 0.50),
        _lin(r.rd_intensity, 0.0, 0.10),
    ])
    rat = f"ROIC {_pct(r.roic)}, net margin {_pct(r.net_margin)}"
    if market_share_proxy is not None:
        rat += f", peer share {_pct(market_share_proxy)}"
    return n, rat, {"roic": r.roic, "gross_margin": r.gross_margin, "net_margin": r.net_margin,
                    "market_share_proxy": market_share_proxy}


def score_management(r: Ratios, promoter_holding: float | None = None) -> tuple[float | None, str, dict]:
    cap_eff = _avg([_lin(r.roic, 0.08, 0.22), _lin(r.roe, 0.10, 0.25)])
    # A meaningful promoter stake (skin in the game) informs the score. A tiny/zero stake is
    # NOT a negative -- many well-run banks/MNCs are widely held with no promoter -- so treat
    # it like missing data and blend capital efficiency with a neutral prior instead.
    meaningful = promoter_holding is not None and promoter_holding >= 0.10
    if meaningful:
        base = _lin(promoter_holding, 0.30, 0.75)
        n = _avg([base, cap_eff]) if cap_eff is not None else base
    else:
        n = _avg([cap_eff, 0.5]) if cap_eff is not None else 0.5
    rat = f"capital efficiency ROIC {_pct(r.roic)}, ROE {_pct(r.roe)}"
    if meaningful:
        rat = f"promoter holding {_pct(promoter_holding)}, " + rat
    return n, rat, {"promoter_holding": promoter_holding, "roic": r.roic, "roe": r.roe}


_OUTLOOK_MAP = {"high": 0.85, "medium": 0.55, "low": 0.30}


def score_industry(outlook: str | None = None, cagr_hint: str | None = None) -> tuple[float | None, str, dict]:
    n = _OUTLOOK_MAP.get((outlook or "").lower())
    rat = f"industry outlook: {outlook or 'medium (default)'}"
    if cagr_hint:
        rat += f", CAGR {cagr_hint}"
    return (n if n is not None else 0.55), rat, {}


def score_innovation(r: Ratios, product_news: bool | None = None) -> tuple[float | None, str, dict]:
    base = _lin(r.rd_intensity, 0.0, 0.08)
    if base is None:
        base = 0.45  # many firms don't report R&D; assume moderate
    if product_news:
        base = min(1.0, base + 0.15)
    rat = f"R&D intensity {_pct(r.rd_intensity)}" if r.rd_intensity is not None else "R&D not disclosed"
    return base, rat, {"rd_intensity": r.rd_intensity}


def score_risk(r: Ratios) -> tuple[float | None, str, dict]:
    """Higher = safer."""
    n = _avg([
        _inv(r.debt_to_equity, 0.0, 2.0),
        _inv(r.beta, 0.7, 1.8),
        _lin(r.interest_coverage, 2.0, 12.0),
    ])
    beta = f"{r.beta:.2f}" if r.beta is not None else "n/a"
    rat = f"beta {beta}, leverage & coverage based"
    return n, rat, {"debt_to_equity": r.debt_to_equity, "beta": r.beta,
                    "interest_coverage": r.interest_coverage}


def score_esg(esg_total: float | None) -> float | None:
    """yfinance total ESG is a *risk* score (lower = better, ~0-40). Invert to [0,1]."""
    return _inv(esg_total, 10.0, 35.0)


# --------------------------------------------------------------------------------------
# Composite
# --------------------------------------------------------------------------------------
def _verdict(total: float) -> str:
    if total >= 80:
        return "Excellent"
    if total >= 65:
        return "Strong"
    if total >= 50:
        return "Fair"
    if total >= 35:
        return "Weak"
    return "Poor"


def compute_score(
    ticker: str,
    ratios: Ratios,
    *,
    dcf: DCFResult | None = None,
    sector: str | None = None,
    market_share_proxy: float | None = None,
    promoter_holding: float | None = None,
    industry_outlook: str | None = None,
    industry_cagr_hint: str | None = None,
    product_news: bool | None = None,
    esg_total: float | None = None,
) -> Score:
    """Assemble the 11-bucket composite score, normalized to 100."""
    specs = [
        ("Growth", "computed", *score_growth(ratios)),
        ("Profitability", "computed", *score_profitability(ratios)),
        ("Cash Flow", "computed", *score_cashflow(ratios)),
        ("Balance Sheet", "computed", *score_debt(ratios, sector)),
        ("Valuation", "computed", *score_valuation(ratios, dcf)),
        ("Competitive Moat", "heuristic", *score_moat(ratios, market_share_proxy)),
        ("Management", "heuristic", *score_management(ratios, promoter_holding)),
        ("Industry Outlook", "heuristic", *score_industry(industry_outlook, industry_cagr_hint)),
        ("Innovation", "heuristic", *score_innovation(ratios, product_news)),
        ("Risk", "heuristic", *score_risk(ratios)),
    ]

    buckets: list[ScoreBucket] = []
    earned = 0.0
    possible = 0.0
    for name, kind, normalized, rationale, drivers in specs:
        weight = WEIGHTS[name]
        # Missing-data buckets default to neutral 0.5 rather than distorting the total.
        norm = normalized if normalized is not None else 0.5
        note = rationale
        if normalized is None:
            note = f"insufficient data (neutral) - {rationale}"
        points = norm * weight
        earned += points
        possible += weight
        buckets.append(ScoreBucket(
            name=name, weight=weight, score=round(points, 2), normalized=round(norm, 3),
            kind=kind,  # type: ignore[arg-type]  # always "computed"/"heuristic"
            rationale=note, drivers=drivers,
        ))

    esg_included = False
    esg_norm = score_esg(esg_total)
    if esg_norm is not None:
        esg_included = True
        points = esg_norm * ESG_WEIGHT
        earned += points
        possible += ESG_WEIGHT
        buckets.append(ScoreBucket(
            name="ESG", weight=ESG_WEIGHT, score=round(points, 2), normalized=round(esg_norm, 3),
            kind="computed", rationale=f"ESG risk score {esg_total:.1f} (lower is better)",
            drivers={"esg_total": esg_total},
        ))

    total = round((earned / possible) * 100.0, 1) if possible else 0.0
    return Score(
        ticker=ticker.upper(),
        total=total,
        verdict=_verdict(total),
        buckets=buckets,
        esg_included=esg_included,
        note="Qualitative buckets use heuristic baselines; refine with evidence for a sharper score.",
    )
