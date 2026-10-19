from pathlib import Path

from ledgerly import export_csv, generate_customer_statement, generate_monthly_report, load_transactions, summarize_by_category

DATA = Path(__file__).resolve().parents[1] / "data" / "sample.csv"


def test_load():
    txs = load_transactions(DATA)
    assert len(txs) == 8 and txs[4]["currency"] == "USD" and txs[4]["category"] == "uncategorized"


def test_monthly_text_net_line():
    report = generate_monthly_report(load_transactions(DATA), "2024-03")
    assert report.startswith("MONTHLY REPORT 2024-03 (USD)")
    assert "NET" in report and "Top customers:" in report


def test_summary_categories():
    s = summarize_by_category(load_transactions(DATA), "2024-03")
    assert set(s) == {"books", "music", "electronics", "uncategorized"}
    assert s["books"] == {"count": 1, "gross": 120.0, "refunds": 20.0, "net": 100.0}


def test_statement_csv():
    out = generate_customer_statement(load_transactions(DATA), "C001", "2024-03-01", "2024-04-30", fmt="csv")
    assert out.splitlines()[-1] == "2024-04-01,T008,Purchase,45.00,145.00"


def test_export(tmp_path):
    assert export_csv(load_transactions(DATA), tmp_path / "out.csv", month="2024-03") == 7
