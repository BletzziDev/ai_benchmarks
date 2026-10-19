from acctsvc import cli


def test_cli_end_to_end(tmp_path, capsys):
    dbp = str(tmp_path / "t.db")
    assert cli.main(["--db", dbp, "migrate"]) == 0
    assert cli.main(["--db", dbp, "create-user", "ada@example.com", "Ada Lovelace"]) == 0
    assert cli.main(["--db", dbp, "create-org", "Acme", "--owner", "1"]) == 0
    assert cli.main(["--db", dbp, "subscribe", "--org", "1", "--plan", "team", "--start", "2025-01-15"]) == 0
    assert cli.main(["--db", dbp, "invoice", "--org", "1"]) == 0
    capsys.readouterr()
    assert cli.main(["--db", dbp, "list-invoices", "--org", "1"]) == 0
    out = capsys.readouterr().out
    assert "INV-" in out and "49.00" in out


def test_cli_reports_domain_errors(tmp_path, capsys):
    dbp = str(tmp_path / "t.db")
    cli.main(["--db", dbp, "migrate"])
    assert cli.main(["--db", dbp, "create-org", "Acme", "--owner", "42"]) == 2
