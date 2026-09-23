from __future__ import annotations

import copy
from datetime import datetime, timezone

from kgi_interop_monitor import history


def report(run_id: str, started: str, ok: bool = True, grade: str = "B", a3: str = "pass") -> dict:
    return {
        "run_id": run_id,
        "started_at": started,
        "status": "ok",
        "seconds": 1.0,
        "monitor": {"version": "0.1.0", "vantage": "test", "layers": "ABC"},
        "hub_findings": [{"id": "H1", "outcome": "fail"}],
        "kgs": [{"id": "KGR1", "grade": grade, "grade_if_registry_fixed": "C",
                 "results": {"A3": {"outcome": a3}, "B2": {"outcome": "fail"}},
                 "kpis": {"available": ok, "latency_ms": 100.0 if ok else None, "protocol": {"passed": 13},
                          "triples": 42}}],
    }


def test_compact_line_has_one_letter_per_probe():
    line = history.compact(report("r1", "2026-09-23T00:00:00+00:00"))
    o = line["kgs"]["KGR1"]["o"]
    assert len(o) == len(history.PROBES)
    assert o[history.PROBES.index("A3")] == "P" and o[history.PROBES.index("B2")] == "F"
    assert o[history.PROBES.index("C1")] == "-"
    assert line["h1"] == "fail"


def test_record_keeps_latest_every_line_and_one_daily_snapshot(tmp_path):
    history.record(report("2026-09-23T0017Z", "2026-09-23T00:17:00+00:00"), tmp_path)
    history.record(report("2026-09-23T0617Z", "2026-09-23T06:17:00+00:00"), tmp_path)
    written = history.record(report("2026-09-24T0017Z", "2026-09-24T00:17:00+00:00"), tmp_path)
    assert len(history.load(tmp_path)) == 3
    assert history.latest(tmp_path)["run_id"] == "2026-09-24T0017Z"
    snapshots = sorted(p.name for p in (tmp_path / "runs").rglob("*.json.gz"))
    assert snapshots == ["2026-09-23T0017Z.json.gz", "2026-09-24T0017Z.json.gz"]
    assert "daily" in written


def test_kpis_availability_latency_and_flaps():
    entries = [history.compact(report(f"r{i}", f"2026-09-23T0{i}:00:00+00:00", ok=ok))
               for i, ok in enumerate([True, False, True, True])]
    k = history.kpis(entries, now=datetime(2026, 9, 23, 12, tzinfo=timezone.utc))["kgs"]["KGR1"]
    assert k["runs"] == 4 and k["availability"] == 75.0 and k["flaps"] == 2
    assert k["latency_p50"] == 100.0


def test_unhealthy_runs_are_not_counted_against_endpoints():
    bad = history.compact(report("r0", "2026-09-23T00:00:00+00:00"))
    bad["status"] = "instrument-unhealthy"
    good = history.compact(report("r1", "2026-09-23T01:00:00+00:00"))
    k = history.kpis([bad, good], now=datetime(2026, 9, 23, 12, tzinfo=timezone.utc))
    assert k["runs"] == 1


def test_layer_series_counts_failures_per_layer():
    fixed = report("r2", "2026-09-24T00:00:00+00:00", a3="pass")
    broken = report("r1", "2026-09-23T00:00:00+00:00", a3="fail")
    rows = history.layer_series([history.compact(broken), history.compact(fixed)])
    assert rows[0]["fails"] == {"A": 1, "B": 1, "C": 0}
    assert rows[1]["fails"] == {"A": 0, "B": 1, "C": 0}
