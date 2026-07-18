"""DCF sensitivity: intrinsic value across a discount-rate x terminal-growth grid.

A single DCF number hides how much it rests on two assumptions. This grid shows the spread, and
the implied break-even growth answers the more useful question: what future growth is the *market*
already paying for at today's price?

Performance note that shapes the whole module: ``yahoo.get_financials`` is **not** cached (only
info and FX are). A 5x5 grid calls ``compute_dcf`` 25 times, so we fetch info/financials/ratios
**once** and pass them into every call — otherwise one tool invocation becomes 25 multi-second
statement fetches on the analyze critical path. ``test_sensitivity`` asserts the single fetch.
"""

from __future__ import annotations

from ..config import CONFIG
from ..models import DcfSensitivity, Provenance
from ..sources import data
from . import evidence as ev
from .dcf import compute_dcf
from .ratios import compute_ratios

# Grid geometry: base +/- span, in steps. Kept small — the point is the shape, not a heat map.
_R_STEP = 0.015
_R_SPAN = 2  # -> 5 columns: base +/- 3.0pp
_G_STEP = 0.01
_G_SPAN = 2  # -> 5 rows: base +/- 2.0pp
_BISECT_ITERS = 40
_BISECT_HI = 0.50  # no company grows FCF > 50%/yr forever; cap the break-even search here


def dcf_sensitivity(symbol: str, market: str = "IN") -> DcfSensitivity:
    symbol = symbol.upper()
    # Fetch once; reuse across all 25 grid cells and the break-even bisection.
    info = data.get_info(symbol)
    financials = data.get_financials(symbol)
    ratios = compute_ratios(symbol, info=info, financials=financials)

    base = compute_dcf(symbol, info=info, financials=financials, ratios=ratios)
    result = DcfSensitivity(
        ticker=symbol, currency=base.currency, base=base, current_price=base.current_price,
    )

    if base.intrinsic_value_per_share is None:
        result.note = base.note or "DCF not available, so no sensitivity grid."
        result.evidence = ev.build_meta(
            sources=[Provenance(source=ev.SRC_YAHOO, detail="statements")],
            present=0, expected=1, reason="DCF not computable")
        return result

    r0 = base.discount_rate if base.discount_rate is not None else \
        CONFIG.discount_rate_for_market(market)
    g0 = base.terminal_growth if base.terminal_growth is not None else CONFIG.dcf_terminal_growth

    rates = [round(r0 + (i - _R_SPAN) * _R_STEP, 4) for i in range(2 * _R_SPAN + 1)]
    growths = [round(g0 + (j - _G_SPAN) * _G_STEP, 4) for j in range(2 * _G_SPAN + 1)]
    result.discount_rates = rates
    result.terminal_growths = growths

    grid: list[list[float | None]] = []
    for g in growths:
        row: list[float | None] = []
        for r in rates:
            if r <= g:
                row.append(None)  # matches compute_dcf's own guard; undefined here
                continue
            cell = compute_dcf(symbol, info=info, financials=financials, ratios=ratios,
                               discount_rate=r, terminal_growth=g)
            row.append(cell.intrinsic_value_per_share)
        grid.append(row)
    result.grid = grid

    result.implied_breakeven_growth = _breakeven_growth(
        symbol, info, financials, ratios, base, g0)

    notes = ["Intrinsic value per share across discount rate (columns) x terminal growth (rows)."]
    if result.implied_breakeven_growth is None:
        notes.append("Break-even growth exceeds 50%/yr or is otherwise unreachable.")
    result.evidence = ev.build_meta(
        sources=[Provenance(source=ev.SRC_YAHOO, detail="statements"),
                 Provenance(source=ev.SRC_HEURISTIC, detail="two-stage DCF")],
        present=1, expected=1, notes=notes,
    )
    return result


def _breakeven_growth(symbol, info, financials, ratios, base, g0) -> float | None:
    """The explicit-stage growth that makes intrinsic value equal today's price.

    Intrinsic value is monotonic in growth, so bisect rather than solve — there is no clean
    closed form for a two-stage-plus-Gordon model. Returns None if the price can't be reached
    within a sane growth ceiling.
    """
    price = base.current_price
    if price is None or price <= 0:
        return None

    def intrinsic_at(g: float) -> float | None:
        return compute_dcf(symbol, info=info, financials=financials, ratios=ratios,
                           growth_rate=g).intrinsic_value_per_share

    lo, hi = g0 + 0.0001, _BISECT_HI
    v_lo, v_hi = intrinsic_at(lo), intrinsic_at(hi)
    if v_lo is None or v_hi is None:
        return None
    # The price must sit between the two ends for a root to exist in [lo, hi].
    if not (min(v_lo, v_hi) <= price <= max(v_lo, v_hi)):
        return None

    ascending = v_hi >= v_lo
    for _ in range(_BISECT_ITERS):
        mid = (lo + hi) / 2
        v = intrinsic_at(mid)
        if v is None:
            return None
        if (v < price) == ascending:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)
