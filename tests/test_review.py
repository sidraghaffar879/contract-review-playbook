from contractreview.review import ContractReviewer, to_markdown
from contractreview.rules import check, extract_facts
from contractreview.segment import segment


def test_segmentation_finds_numbered_clauses():
    cl = segment(open("samples/vendor_msa.txt").read())
    assert [c.number for c in cl][:3] == ["1", "2", "3"] and cl[4].heading == "Limitation of Liability"


def test_liability_rules():
    pb = ContractReviewer().playbook["limitation_of_liability"]
    bad = extract_facts("limitation_of_liability", "Supplier's liability shall not exceed fees paid in the preceding three (3) months. Customer's liability shall not be limited.")
    assert bad["uncapped"] and bad["cap_months"] == 3
    assert check("limitation_of_liability", bad, pb)[0] == "deviation"
    good = extract_facts("limitation_of_liability", "Each party's aggregate liability shall not exceed the fees paid in the preceding twelve (12) months.")
    assert check("limitation_of_liability", good, pb)[0] == "standard"


def test_vendor_msa_is_high_risk_with_expected_deviations():
    r = ContractReviewer().review("samples/vendor_msa.txt")
    by_type = {f.clause_type: f.status for f in r.findings}
    assert by_type["limitation_of_liability"] == "deviation"
    assert by_type["non_compete"] == "deviation"
    assert by_type["governing_law"] == "deviation"
    assert by_type["auto_renewal"] == "deviation"
    assert by_type["payment_terms"] == "deviation"
    assert by_type["termination"] == "deviation"
    assert r.risk_score / r.max_score > 0.45
    assert "Proposed redline" in to_markdown(r)


def test_clean_msa_is_low_risk_and_flags_nothing_missing():
    r = ContractReviewer().review("samples/clean_msa.txt")
    assert r.summary["deviation"] == 0 and r.summary["missing"] == 0
    assert r.risk_score / r.max_score < 0.2
