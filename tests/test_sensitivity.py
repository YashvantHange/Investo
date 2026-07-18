"""DCF-sensitivity tests (no network — stubbed data facade).

The point of interest is not just the grid but the N+1 guard: a 5x5 grid calls compute_dcf 25
times, and get_financials is uncached, so the module must fetch statements exactly once.
"""


from investo.analysis import sensitivity
from investo.models import DCFResult, Financials, Ratios


def _wire(monkeypatch, *, intrinsic=1000.0, price=1000.0):
    """Stub the data facade and compute_dcf with a monotone, analytic surrogate.

    intrinsic rises with growth and falls with the discount rate — the real DCF's qualitative
    behaviour — so grid/breakeven logic can be checked without the network.
    """
    calls = {"financials": 0, "info": 0}

    monkeypatch.setattr(sensitivity.data, "get_info",
                        lambda s: (calls.__setitem__("info", calls["info"] + 1),
                                   {"currency": "INR"})[1])
    monkeypatch.setattr(sensitivity.data, "get_financials",
                        lambda s, *a, **k: (calls.__setitem__("financials",
                                                              calls["financials"] + 1),
                                            Financials(ticker=s))[1])
    monkeypatch.setattr(sensitivity, "compute_ratios",
                        lambda s, **k: Ratios(ticker=s))

    def fake_dcf(symbol, *, info=None, financials=None, ratios=None,
                 discount_rate=None, terminal_growth=None, growth_rate=None, **kw):
        r = discount_rate if discount_rate is not None else 0.12
        g = terminal_growth if terminal_growth is not None else 0.04
        gr = growth_rate if growth_rate is not None else 0.10
        # Monotone surrogate: up with growth, down with discount rate.
        value = intrinsic * (1 + (gr - 0.10) * 5) * (1 + (g - 0.04) * 3) * (0.12 / r)
        return DCFResult(ticker=symbol, currency="INR", discount_rate=r, terminal_growth=g,
                         growth_rate=gr, intrinsic_value_per_share=value, current_price=price)

    monkeypatch.setattr(sensitivity, "compute_dcf", fake_dcf)
    return calls


def test_get_financials_is_fetched_exactly_once(monkeypatch):
    # The N+1 guard: 25 grid cells + base + break-even bisection must reuse one statement fetch.
    calls = _wire(monkeypatch)
    sensitivity.dcf_sensitivity("KPITTECH.NS", "IN")
    assert calls["financials"] == 1


def test_grid_is_five_by_five_with_the_expected_axes(monkeypatch):
    _wire(monkeypatch)
    s = sensitivity.dcf_sensitivity("KPITTECH.NS", "IN")
    assert len(s.discount_rates) == 5
    assert len(s.terminal_growths) == 5
    assert len(s.grid) == 5 and all(len(row) == 5 for row in s.grid)


def test_cells_where_rate_not_above_growth_are_none(monkeypatch):
    _wire(monkeypatch)
    s = sensitivity.dcf_sensitivity("KPITTECH.NS", "IN")
    for gi, g in enumerate(s.terminal_growths):
        for ri, r in enumerate(s.discount_rates):
            if r <= g:
                assert s.grid[gi][ri] is None


def test_intrinsic_is_monotonic_in_the_grid(monkeypatch):
    _wire(monkeypatch)
    s = sensitivity.dcf_sensitivity("KPITTECH.NS", "IN")
    mid = len(s.discount_rates) // 2
    # Along a row, value falls as the discount rate rises.
    row = [c for c in s.grid[mid] if c is not None]
    assert row == sorted(row, reverse=True)
    # Down a column, value rises as terminal growth rises.
    col = [s.grid[gi][mid] for gi in range(len(s.terminal_growths))
           if s.grid[gi][mid] is not None]
    assert col == sorted(col)


def test_breakeven_growth_recovers_the_price(monkeypatch):
    # Price set equal to the base intrinsic -> break-even growth ~ the base growth (0.10).
    _wire(monkeypatch, intrinsic=1000.0, price=1000.0)
    s = sensitivity.dcf_sensitivity("KPITTECH.NS", "IN")
    assert s.implied_breakeven_growth is not None
    assert abs(s.implied_breakeven_growth - 0.10) < 0.01


def test_no_dcf_yields_a_note_not_a_crash(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(sensitivity, "compute_dcf",
                        lambda *a, **k: DCFResult(ticker="X", note="no FCF"))
    s = sensitivity.dcf_sensitivity("X", "IN")
    assert s.grid == []
    assert s.note is not None


def test_unreachable_breakeven_is_none(monkeypatch):
    # Price far above any achievable intrinsic -> no break-even within the growth ceiling.
    _wire(monkeypatch, intrinsic=1000.0, price=10_000_000.0)
    s = sensitivity.dcf_sensitivity("X", "IN")
    assert s.implied_breakeven_growth is None
