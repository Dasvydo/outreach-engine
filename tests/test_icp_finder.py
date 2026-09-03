"""The finder produces valid rows for all three markets, and dedup is real.

These run against the recorded-shape SERP fixtures with `--no-probe`, so they are
deterministic and need no site fetches. They do still perform live MX lookups,
because the Microsoft 365 gate is the whole point of the finder and a test that
mocks it away would not be testing the thing that matters.
"""

import csv

import pytest

from engine import icp_finder
from engine.signals import SiteProfile, dev_team_signal, size_estimate, to_band


MARKETS = ("dk", "lt", "global")


@pytest.mark.parametrize("market", MARKETS)
def test_every_market_produces_valid_rows(market, clean_ledger, tmp_path):
    summary = icp_finder.run_market(
        market, probe=False, lists_dir=tmp_path, run_date="2026-09-03")

    assert summary["new"] > 0, f"{market} produced no rows at all"

    rows = list(csv.DictReader(open(summary["csv"], encoding="utf-8")))
    assert len(rows) == summary["new"]

    for row in rows:
        # The first ten columns are the contract recovered from the real
        # leads_*.csv files in Drive. They must all be present.
        assert row["date_added"] == "2026-09-03"
        assert row["domain"]
        assert row["company"]
        assert row["market"] == market
        assert row["segment"] in ("accounting", "insurance", "housing_admin")
        assert row["locale"] == icp_finder.LOCALE_BY_MARKET[market]
        # The hard gate. Nothing but Microsoft 365 gets into a list.
        assert row["mail_provider"] == "microsoft", row
        assert ".mail.protection.outlook.com" in row["mx_host"] or \
               ".mx.microsoft" in row["mx_host"]
        assert row["hook_seed"], "every row carries its segment opener"
        assert 0.0 <= float(row["fit_score"]) <= 1.0
        if row["team_size"]:
            assert row["team_size"] in ("1-9", "10-24", "25-49", "50+")


def test_csv_header_keeps_the_existing_leads_contract(clean_ledger, tmp_path):
    """The real leads_2026-08-18.csv in Drive starts with these ten columns."""
    existing = ["date_added", "company", "domain", "country", "vertical",
                "est_size", "fit_score", "hook_seed", "status", "notes"]
    assert icp_finder.CSV_COLUMNS[:10] == existing

    summary = icp_finder.run_market("dk", probe=False, lists_dir=tmp_path,
                                    run_date="2026-09-03")
    with open(summary["csv"], encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header[:10] == existing


def test_running_twice_adds_nothing(clean_ledger, tmp_path):
    """Dedup, proved. Second run is all duplicates and an identical CSV."""
    first = icp_finder.run_market("dk", probe=False, lists_dir=tmp_path / "a",
                                  run_date="2026-09-03")
    second = icp_finder.run_market("dk", probe=False, lists_dir=tmp_path / "b",
                                   run_date="2026-09-03")

    assert first["new"] > 0
    assert second["new"] == 0, "the second run added rows it should have deduped"
    assert second["already_in_ledger"] == first["new"]

    # And the artefact proves it: same header, and not one data row the second
    # time. A CSV that merely happened to be the same length would not.
    body_a = (tmp_path / "a" / "dk-2026-09-03.csv").read_text(encoding="utf-8")
    body_b = (tmp_path / "b" / "dk-2026-09-03.csv").read_text(encoding="utf-8")
    lines_a = body_a.strip().splitlines()
    lines_b = body_b.strip().splitlines()
    assert lines_b[0] == lines_a[0], "header changed between runs"
    assert len(lines_a) > 1, "the first run wrote no rows, so the test proves nothing"
    assert len(lines_b) == 1, f"second run wrote {len(lines_b) - 1} data rows"


def test_dedup_holds_across_all_three_markets(clean_ledger, tmp_path):
    firsts = {m: icp_finder.run_market(m, probe=False, lists_dir=tmp_path / "1",
                                       run_date="2026-09-03") for m in MARKETS}
    seconds = {m: icp_finder.run_market(m, probe=False, lists_dir=tmp_path / "2",
                                        run_date="2026-09-03") for m in MARKETS}
    for market in MARKETS:
        assert firsts[market]["new"] > 0
        assert seconds[market]["new"] == 0, f"{market} re-added rows on the second run"


def test_the_mx_gate_actually_rejects(clean_ledger, tmp_path):
    """A gate that never rejects is not a gate."""
    summary = icp_finder.run_market("dk", probe=False, lists_dir=tmp_path,
                                    run_date="2026-09-03")
    assert summary["failed_mx_gate"] > 0
    assert summary["mx_rejects"], "nothing was rejected, so the gate is not working"


def test_hard_gate_failures_stay_out_of_the_outreach_csv(clean_ledger, tmp_path):
    """A firm over the sovereignty ceiling is written to the ledger, not the list."""
    summary = icp_finder.run_market("dk", probe=False, lists_dir=tmp_path,
                                    run_date="2026-09-03")
    rows = list(csv.DictReader(open(summary["csv"], encoding="utf-8")))
    domains = {r["domain"] for r in rows}
    for reject in summary["gate_rejects"]:
        assert reject.split(" ")[0] not in domains


def test_the_newer_microsoft_mx_endpoint_is_recognised():
    """Regression. *.mx.microsoft was classified OTHER and failed real firms.

    Found on 2026-09-03 by probing 84 real ICP domains: redmark.dk and vbtm.nl
    both run Microsoft 365 on the newer endpoint and were being dropped.
    """
    from engine.enrich import Provider, _SIGNATURES
    assert any(needle == ".mx.microsoft" and provider is Provider.MICROSOFT
               for needle, provider in _SIGNATURES)


# --- soft signals ---------------------------------------------------------

def test_dev_team_signal_scores_and_never_hard_blocks():
    clean = SiteProfile("firm.dk", paths=("/", "/om-os"), text="Vi laver revision.")
    assert dev_team_signal(clean)[0] == 0.0

    loud = SiteProfile("firm.dk", paths=("/", "/engineering"),
                       text="We are hiring a Senior Backend Engineer",
                       links='<a href="https://github.com/acme-dev/">gh</a>')
    score, reasons = dev_team_signal(loud)
    assert score == 1.0
    assert len(reasons) == 3
    # Still a float, not a boolean. The spec says score it, never hard-block.
    assert isinstance(score, float)


def test_size_estimate_reads_all_three_languages():
    assert size_estimate(SiteProfile("a", text="We are 34 employees"))[0] == 34
    assert size_estimate(SiteProfile("b", text="Vi er 18 medarbejdere"))[0] == 18
    assert size_estimate(SiteProfile("c", text="Mus yra 12 darbuotoju"))[0] == 12


def test_unknown_size_is_none_and_never_zero():
    employees, reason = size_estimate(SiteProfile("d", text="Welcome to our site"))
    assert employees is None
    assert reason == "unknown"
    assert to_band(None) is None


def test_bands_match_the_qualifier_contract():
    assert to_band(4) == "1-9"
    assert to_band(14) == "10-24"
    assert to_band(30) == "25-49"
    assert to_band(120) == "50+"
