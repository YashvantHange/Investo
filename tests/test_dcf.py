"""DCF tests using in-memory fixtures (no network)."""

from investo.analysis.dcf import compute_dcf
from investo.analysis.ratios import compute_ratios
from investo.models import FinancialPeriod, Financials


def _fixture() -> tuple[dict, Financials]:
    info = {
        "financialCurrency": "INR", "currency": "INR", "exchange": "NSI",
        "sharesOutstanding": 100.0, "currentPrice": 20.0,
        "totalDebt": 100.0, "totalCash": 50.0,
    }
    fin = Financials(
        ticker="X.NS", currency="INR", period_type="annual",
        income_statement=[
            FinancialPeriod(period="2024", values={"Total Revenue": 1000, "EBIT": 220, "Net Income": 150,
                                                    "EBITDA": 260, "Diluted EPS": 15}),
            FinancialPeriod(period="2023", values={"Total Revenue": 900, "EBIT": 190, "Net Income": 130,
                                                    "EBITDA": 230, "Diluted EPS": 13}),
            FinancialPeriod(period="2022", values={"Total Revenue": 820, "EBIT": 170, "Net Income": 115,
                                                    "EBITDA": 210, "Diluted EPS": 11}),
        ],
        balance_sheet=[
            FinancialPeriod(period="2024", values={"Total Debt": 100, "Cash And Cash Equivalents": 50,
                                                    "Total Assets": 2000, "Current Assets": 600,
                                                    "Current Liabilities": 300, "Invested Capital": 800,
                                                    "Stockholders Equity": 900}),
        ],
        cash_flow=[
            FinancialPeriod(period="2024", values={"Free Cash Flow": 120}),
            FinancialPeriod(period="2023", values={"Free Cash Flow": 100}),
            FinancialPeriod(period="2022", values={"Free Cash Flow": 80}),
        ],
    )
    return info, fin


def test_dcf_produces_positive_intrinsic():
    info, fin = _fixture()
    ratios = compute_ratios("X.NS", info=info, financials=fin)
    dcf = compute_dcf("X.NS", info=info, financials=fin, ratios=ratios,
                      growth_rate=0.10, discount_rate=0.12, terminal_growth=0.04, years=5)
    assert dcf.base_fcf == 100.0  # mean of 120, 100, 80
    assert dcf.intrinsic_value_per_share is not None
    assert dcf.intrinsic_value_per_share > 0
    assert dcf.enterprise_value > dcf.equity_value  # net debt subtracted


def test_margin_of_safety_sign_tracks_price():
    info, fin = _fixture()
    ratios = compute_ratios("X.NS", info=info, financials=fin)
    dcf = compute_dcf("X.NS", info=info, financials=fin, ratios=ratios,
                      growth_rate=0.10, discount_rate=0.12, terminal_growth=0.04, years=5)
    intrinsic = dcf.intrinsic_value_per_share
    # margin_of_safety = (intrinsic - price) / intrinsic; price=20 in fixture.
    expected = (intrinsic - 20.0) / intrinsic
    assert abs(dcf.margin_of_safety - expected) < 1e-6


def test_discount_must_exceed_terminal_growth():
    info, fin = _fixture()
    ratios = compute_ratios("X.NS", info=info, financials=fin)
    dcf = compute_dcf("X.NS", info=info, financials=fin, ratios=ratios,
                      discount_rate=0.04, terminal_growth=0.05)
    assert dcf.intrinsic_value_per_share is None
    assert "discount rate" in (dcf.note or "")
