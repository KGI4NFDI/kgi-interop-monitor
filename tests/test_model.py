from __future__ import annotations

from kgi_interop_monitor.model import GATES, SPECS, Outcome, ProbeResult, grade


def results(**outcomes):
    base = {pid: ProbeResult(pid, Outcome.PASS, "") for pid in SPECS}
    for pid, outcome in outcomes.items():
        base[pid] = ProbeResult(pid, outcome, "")
    return base


def test_catalogue_covers_layers_a_to_c_in_checklist_order():
    assert list(SPECS) == [f"A{i}" for i in range(1, 8)] + [f"B{i}" for i in range(1, 6)] + [f"C{i}" for i in range(1, 6)]
    assert "A2" not in GATES["A"] and "A6" not in GATES["A"]
    assert "B3" not in GATES["B"] and "B4" not in GATES["B"]


def test_all_clear_is_c():
    assert grade(results(), has_working_url=True) == "C"


def test_no_working_url():
    assert grade(results(), has_working_url=False) == "none"
    assert grade(results(), has_working_url=False, dump_only=True) == "dump"


def test_registry_defect_caps_at_a_star_but_the_fixed_grade_shows_the_endpoint():
    r = results(A7=Outcome.FAIL)
    assert grade(r, has_working_url=True) == "A*"
    assert grade(r, has_working_url=True, assume_registry_fixed=True) == "C"


def test_strict_ladder():
    assert grade(results(B2=Outcome.FAIL), has_working_url=True) == "A"
    assert grade(results(C1=Outcome.FAIL), has_working_url=True) == "B"
    assert grade(results(B2=Outcome.FAIL, C1=Outcome.FAIL), has_working_url=True) == "A"


def test_non_gating_rows_never_hold_the_grade_back():
    assert grade(results(B3=Outcome.FAIL, B4=Outcome.FAIL, A6=Outcome.WARN), has_working_url=True) == "C"


def test_unknown_and_blocked_do_not_clear_a_gate():
    assert grade(results(C4=Outcome.UNKNOWN), has_working_url=True) == "B"
    assert grade(results(B1=Outcome.BLOCKED), has_working_url=True) == "A"


def test_warn_and_na_clear_a_gate():
    assert grade(results(C2=Outcome.WARN, C4=Outcome.NA), has_working_url=True) == "C"
