"""Tests for the CSV export."""

import csv
import io

from export import leads_to_csv, safe_cell
from tests.fake_database import LEAD_DEFAULTS


def lead(**changes):
    return {**LEAD_DEFAULTS, "id": 1, "name": "Acme", "company_key": "acme", **changes}


def read_back(data):
    text = data.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def test_formulas_are_neutralised():
    for bad in ["=HYPERLINK(\"http://x\")", "+1", "-2", "@SUM(A1)", "\t=1"]:
        assert safe_cell(bad).startswith("'")
    assert safe_cell("Normal text") == "Normal text"
    assert safe_cell(None) == ""


def test_quotes_commas_and_multiline_survive():
    body = 'Hi "Pat",\n\nLine two, with a comma.\nJohn'
    rows = read_back(leads_to_csv([lead(email_body=body, name="=cmd|' /C calc'!A0")]))
    header, row = rows
    assert row[header.index("Email body")] == body
    assert row[header.index("Company")].startswith("'=")


def test_unknown_research_says_unknown():
    rows = read_back(leads_to_csv([lead()]))
    header, row = rows
    assert row[header.index("Owner")] == "unknown"
    assert row[header.index("Revenue")] == "unknown"


def test_estimates_are_labelled():
    research = {"owner_name": {"value": "Pat", "status": "estimate", "sources": []}}
    header, row = read_back(leads_to_csv([lead(research=research)]))
    assert row[header.index("Owner")] == "Pat (estimate)"
