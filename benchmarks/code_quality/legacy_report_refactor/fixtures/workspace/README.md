# ledgerly

Reporting module for the merchant dashboard. `ledgerly/reports.py` produces the monthly report
(text, Markdown, CSV), customer statements, category summaries and CSV exports.

Consumers: the dashboard (Markdown), the finance team's spreadsheet macros (CSV — they parse the
exact column names and number formats), and emailed statements (text). Output formats are a
contract. Run tests with `python -m pytest -q`.
