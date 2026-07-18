"""Scoring-model tests (no network)."""

from investo.analysis import scoring
from investo.models import Ratios


def _good() -> Ratios:
    return Ratios(
        ticker="GOOD", roe=0.30, roce=0.35, roic=0.28, net_margin=0.20, operating_margin=0.25,
        gross_margin=0.50, fcf_margin=0.18, ocf_to_ebitda=1.0, debt_to_equity=0.1,
        interest_coverage=50.0, current_ratio=2.2, pe=15.0, pb=4.0, ev_ebitda=12.0,
        revenue_growth_yoy=0.18, revenue_cagr_3y=0.16, earnings_growth_yoy=0.20, beta=0.8,
    )


def _poor() -> Ratios:
    return Ratios(
        ticker="POOR", roe=0.03, roce=0.04, roic=0.02, net_margin=0.01, operating_margin=0.02,
        gross_margin=0.10, fcf_margin=-0.05, ocf_to_ebitda=0.4, debt_to_equity=3.0,
        interest_coverage=1.0, current_ratio=0.7, pe=80.0, pb=15.0, ev_ebitda=40.0,
        revenue_growth_yoy=-0.10, revenue_cagr_3y=-0.05, earnings_growth_yoy=-0.15, beta=1.8,
    )


def test_good_beats_poor():
    good = scoring.compute_score("GOOD", _good())
    poor = scoring.compute_score("POOR", _poor())
    assert good.total > poor.total
    assert good.total >= 65      # a strong company should score well
    assert poor.total <= 40      # a weak one should score poorly


def test_total_is_bounded_0_100():
    for r in (_good(), _poor(), Ratios(ticker="EMPTY")):
        s = scoring.compute_score("X", r)
        assert 0.0 <= s.total <= 100.0


def test_ten_buckets_without_esg_eleven_with():
    without = scoring.compute_score("X", _good())
    assert len(without.buckets) == 10
    assert without.esg_included is False

    with_esg = scoring.compute_score("X", _good(), esg_total=12.0)
    assert with_esg.esg_included is True
    assert any(b.name == "ESG" for b in with_esg.buckets)


def test_weights_sum_to_100():
    assert abs(sum(scoring.WEIGHTS.values()) - 100.0) < 1e-9


def test_verdict_thresholds():
    assert scoring._verdict(85) == "Excellent"
    assert scoring._verdict(70) == "Strong"
    assert scoring._verdict(55) == "Fair"
    assert scoring._verdict(40) == "Weak"
    assert scoring._verdict(20) == "Poor"


def test_growth_scorer_monotonic():
    low, _, _ = scoring.score_growth(Ratios(ticker="L", revenue_cagr_3y=0.02, revenue_growth_yoy=0.02))
    high, _, _ = scoring.score_growth(Ratios(ticker="H", revenue_cagr_3y=0.20, revenue_growth_yoy=0.20))
    assert high > low


def test_missing_data_is_neutral_not_zero():
    s = scoring.compute_score("X", Ratios(ticker="EMPTY"))
    # With no data every bucket falls back to neutral 0.5 -> ~50.
    assert 45 <= s.total <= 55


def test_financial_sector_excludes_debt_equity():
    r = Ratios(ticker="BANK", debt_to_equity=8.0, interest_coverage=None, current_ratio=None)
    n_fin, rat, _ = scoring.score_debt(r, sector="Financial Services")
    assert "excluded" in rat


def test_balance_sheet_bucket_renamed():
    s = scoring.compute_score("X", _good())
    names = {b.name for b in s.buckets}
    assert "Balance Sheet" in names
    assert "Debt" not in names


# --------------------------------------------------------------------------------------
# Quality-aware valuation: a premium multiple should not floor the bucket when the company's
# economics justify it, but a low-quality name at the same multiple still floors.
# --------------------------------------------------------------------------------------
def _val_base(**over) -> Ratios:
    d = dict(ticker="V", roe=0.15, roce=0.16, operating_margin=0.15, net_margin=0.10,
             revenue_cagr_3y=0.10, eps_cagr_3y=0.10, revenue_growth_yoy=0.10,
             pe=30.0, pb=6.0, ev_ebitda=18.0, peg=1.5, net_cash_to_market_cap=0.0)
    d.update(over)
    return Ratios(**d)


def test_quality_justifies_premium_multiple():
    prem_hi_q = _val_base(roe=0.30, roce=0.34, operating_margin=0.28, revenue_cagr_3y=0.20,
                          eps_cagr_3y=0.20, pe=45.0, pb=11.0, ev_ebitda=28.0, peg=2.5)
    prem_lo_q = _val_base(roe=0.08, roce=0.08, operating_margin=0.04, revenue_cagr_3y=0.02,
                          eps_cagr_3y=0.02, pe=45.0, pb=11.0, ev_ebitda=28.0, peg=2.5)
    hi = scoring.score_valuation(prem_hi_q)[0]
    lo = scoring.score_valuation(prem_lo_q)[0]
    assert hi > lo + 0.1     # quality unlocks headroom at the same rich multiple
    assert lo < 0.15         # a low-quality premium name still floors (as before)


def test_valuation_monotonic_in_each_quality_signal():
    # Increasing any single quality signal (or net cash) must never lower the valuation bucket.
    grids = {
        "roe": [0.05, 0.15, 0.25, 0.35],
        "operating_margin": [0.0, 0.10, 0.20, 0.30],
        "eps_cagr_3y": [0.0, 0.08, 0.16, 0.24],
        "net_cash_to_market_cap": [-0.3, 0.0, 0.2, 0.5],
    }
    for field, steps in grids.items():
        prev = None
        for v in steps:
            n = scoring.score_valuation(_val_base(**{field: v}))[0]
            assert n is not None
            if prev is not None:
                assert n >= prev - 1e-9, f"{field}={v}: valuation dropped ({n} < {prev})"
            prev = n


# --------------------------------------------------------------------------------------
# Net cash reward: lifts both Valuation (ex-cash multiple) and Balance Sheet; net debt drags.
# --------------------------------------------------------------------------------------
def test_net_cash_lifts_valuation_and_balance_sheet():
    base = _val_base(net_cash_to_market_cap=0.0)
    rich = _val_base(net_cash_to_market_cap=0.30)
    assert scoring.score_valuation(rich)[0] > scoring.score_valuation(base)[0]
    assert scoring.score_debt(rich)[0] > scoring.score_debt(base)[0]


def test_net_debt_drags_balance_sheet_below_debt_free():
    debt_free = Ratios(ticker="DF", debt_to_equity=0.0, net_cash_to_market_cap=0.0)
    net_debt = Ratios(ticker="ND", debt_to_equity=0.0, net_cash_to_market_cap=-0.20)
    assert scoring.score_debt(net_debt)[0] < scoring.score_debt(debt_free)[0]


# --------------------------------------------------------------------------------------
# Regression: the change must be *targeted*, not a blanket re-rank or inflation. A synthetic
# basket spanning the quality/valuation/leverage spectrum is scored and compared against a
# frozen baseline (the pre-change totals) -- rank order must be preserved (Spearman >= 0.90)
# and each archetype must move in the intended direction.
# --------------------------------------------------------------------------------------
def _archetypes() -> dict:
    return {
        "cash_rich_compounder": (Ratios(
            ticker="COMPOUNDER", roe=0.28, roce=0.30, roic=0.26, operating_margin=0.20,
            net_margin=0.16, gross_margin=0.35, fcf_margin=0.15, ocf_to_ebitda=1.0,
            debt_to_equity=0.02, interest_coverage=120.0, current_ratio=3.0, pe=45.0, pb=11.0,
            ev_ebitda=28.0, peg=2.2, revenue_growth_yoy=0.18, revenue_cagr_3y=0.20,
            earnings_growth_yoy=0.22, eps_cagr_3y=0.21, beta=0.9, net_cash_to_market_cap=0.10), None),
        "cheap_cyclical": (Ratios(
            ticker="CYCLICAL", roe=0.14, roce=0.16, roic=0.13, operating_margin=0.14,
            net_margin=0.09, gross_margin=0.22, fcf_margin=0.08, ocf_to_ebitda=0.9,
            debt_to_equity=0.5, interest_coverage=6.0, current_ratio=1.6, pe=9.0, pb=1.1,
            ev_ebitda=6.0, peg=0.9, revenue_growth_yoy=0.06, revenue_cagr_3y=0.05,
            earnings_growth_yoy=0.04, eps_cagr_3y=0.05, beta=1.2, net_cash_to_market_cap=-0.05), None),
        "deep_value": (Ratios(
            ticker="DEEPVALUE", roe=0.08, roce=0.09, roic=0.07, operating_margin=0.09,
            net_margin=0.05, gross_margin=0.18, fcf_margin=0.04, ocf_to_ebitda=0.8,
            debt_to_equity=0.6, interest_coverage=4.0, current_ratio=1.4, pe=6.0, pb=0.7,
            ev_ebitda=4.0, peg=1.2, revenue_growth_yoy=0.02, revenue_cagr_3y=0.01,
            earnings_growth_yoy=0.0, eps_cagr_3y=0.0, beta=1.1, net_cash_to_market_cap=0.0), None),
        "loss_making_growth": (Ratios(
            ticker="LOSSGROWTH", roe=-0.05, roce=-0.03, roic=-0.04, operating_margin=-0.10,
            net_margin=-0.15, gross_margin=0.55, fcf_margin=-0.12, ocf_to_ebitda=0.2,
            debt_to_equity=0.1, interest_coverage=None, current_ratio=2.5, pe=None, pb=8.0,
            ev_ebitda=40.0, peg=None, revenue_growth_yoy=0.40, revenue_cagr_3y=0.45,
            earnings_growth_yoy=None, eps_cagr_3y=None, beta=1.6, net_cash_to_market_cap=0.15), None),
        "leveraged_industrial": (Ratios(
            ticker="LEVERAGED", roe=0.15, roce=0.11, roic=0.10, operating_margin=0.12,
            net_margin=0.06, gross_margin=0.20, fcf_margin=0.05, ocf_to_ebitda=0.85,
            debt_to_equity=1.8, interest_coverage=3.0, current_ratio=1.1, pe=14.0, pb=2.0,
            ev_ebitda=9.0, peg=1.5, revenue_growth_yoy=0.09, revenue_cagr_3y=0.08,
            earnings_growth_yoy=0.07, eps_cagr_3y=0.07, beta=1.3, net_cash_to_market_cap=-0.30), None),
        "asset_heavy_bank": (Ratios(
            ticker="BANK", roe=0.16, roce=None, roic=None, operating_margin=None, net_margin=0.22,
            gross_margin=0.0, fcf_margin=None, ocf_to_ebitda=None, debt_to_equity=8.0,
            interest_coverage=None, current_ratio=None, pe=12.0, pb=1.6, ev_ebitda=None, peg=1.1,
            revenue_growth_yoy=0.12, revenue_cagr_3y=0.11, earnings_growth_yoy=0.13,
            eps_cagr_3y=0.12, beta=1.0, net_cash_to_market_cap=None), "Financial Services"),
    }


def _synth(i: int, roe: float, pe: float, ncm: float) -> Ratios:
    return Ratios(
        ticker=f"G{i}", roe=roe, roce=roe * 1.1, roic=roe * 0.95,
        operating_margin=0.02 + roe * 0.8, net_margin=roe * 0.6, gross_margin=0.25 + roe,
        fcf_margin=max(-0.05, roe * 0.6), ocf_to_ebitda=0.9, debt_to_equity=max(0.0, 0.6 - ncm),
        interest_coverage=4.0 + roe * 120, current_ratio=1.4 + max(0.0, ncm) * 2, pe=pe,
        pb=max(0.4, pe * roe * 1.1), ev_ebitda=pe * 0.6, peg=pe / max(1.0, roe * 100),
        revenue_growth_yoy=roe * 0.7, revenue_cagr_3y=roe * 0.7, earnings_growth_yoy=roe * 0.65,
        eps_cagr_3y=roe * 0.6, beta=1.0, net_cash_to_market_cap=ncm)


def _basket() -> list:
    rows = [(name, r, sector) for name, (r, sector) in _archetypes().items()]
    i = 0
    for roe in (0.06, 0.14, 0.22, 0.30):
        for pe in (10.0, 22.0, 40.0):
            for ncm in (-0.2, 0.05, 0.2):
                rows.append((f"g{i}", _synth(i, roe, pe, ncm), None))
                i += 1
    return rows


# Frozen pre-change totals (the scoring model before this change), one per basket entry.
_OLD_BASELINE = {
    "cash_rich_compounder": 67.6, "cheap_cyclical": 48.9, "deep_value": 36.0,
    "loss_making_growth": 38.0, "leveraged_industrial": 38.0, "asset_heavy_bank": 61.0,
    "g0": 40.4, "g1": 41.3, "g2": 42.3, "g3": 34.9, "g4": 35.7, "g5": 36.8, "g6": 30.0,
    "g7": 30.8, "g8": 31.9, "g9": 54.4, "g10": 55.3, "g11": 56.3, "g12": 49.5, "g13": 50.4,
    "g14": 51.4, "g15": 41.4, "g16": 42.2, "g17": 43.3, "g18": 68.5, "g19": 69.3, "g20": 70.4,
    "g21": 64.1, "g22": 65.0, "g23": 66.0, "g24": 56.9, "g25": 57.7, "g26": 58.8, "g27": 78.2,
    "g28": 79.0, "g29": 80.1, "g30": 73.2, "g31": 74.1, "g32": 75.1, "g33": 68.0, "g34": 68.8,
    "g35": 69.9,
}


def _spearman(a: list, b: list) -> float:
    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((x - mb) ** 2 for x in rb) ** 0.5
    return cov / (va * vb)


def _new_totals() -> dict:
    return {name: scoring.compute_score(name, r, sector=sector).total
            for name, r, sector in _basket()}


def test_rank_order_is_preserved():
    new = _new_totals()
    names = [n for n, _, _ in _basket()]
    old_vec = [_OLD_BASELINE[n] for n in names]
    new_vec = [new[n] for n in names]
    assert _spearman(old_vec, new_vec) >= 0.90


def test_change_is_targeted_per_archetype():
    new = _new_totals()

    def d(name):
        return new[name] - _OLD_BASELINE[name]

    assert d("cash_rich_compounder") >= 2.0                 # moderate increase
    assert abs(d("cheap_cyclical")) <= 5.0                  # ~unchanged
    assert abs(d("deep_value")) <= 5.0                      # ~unchanged
    assert abs(d("loss_making_growth")) <= 4.0             # little change
    assert -8.0 <= d("leveraged_industrial") < 0.0         # slight decrease
    assert abs(d("asset_heavy_bank")) <= 3.0               # nearly unchanged


def test_no_blanket_inflation():
    new = _new_totals()
    deltas = [new[n] - _OLD_BASELINE[n] for n, _, _ in _basket()]
    assert abs(sum(deltas) / len(deltas)) <= 2.0            # mean move near zero
