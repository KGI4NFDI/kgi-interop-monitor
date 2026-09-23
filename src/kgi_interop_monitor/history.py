"""Run history: what each run found, kept so defects can be watched over time.

Layout of a results directory (see docs/decisions/0006-results-branch.md):

    latest.json                 the full report of the last run, with evidence
    history.jsonl               one compact line per run, append-only
    runs/YYYY/MM/<run_id>.json.gz  the full report of the first run of each UTC day

Full reports are about 180 KB compressed. Keeping one per run at four runs a
day would grow the repository by roughly 250 MB a year, so only one per day is
kept in full; every run keeps its compact line.
"""

from __future__ import annotations

import gzip
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .model import SPECS

LETTER = {"pass": "P", "warn": "W", "fail": "F", "unknown": "U", "blocked": "B", "n/a": "N"}
OUTCOME = {v: k for k, v in LETTER.items()}
PROBES = list(SPECS)


def compact(report: dict) -> dict:
    """One history line: per KG the grade, the outcome of every probe (one
    letter each, in checklist order) and the headline KPIs."""
    kgs = {}
    for kg in report.get("kgs", []):
        kpis = kg.get("kpis", {})
        kgs[kg["id"]] = {
            "g": kg["grade"],
            "gf": kg["grade_if_registry_fixed"],
            "o": "".join(LETTER.get(kg["results"].get(p, {}).get("outcome"), "-") for p in PROBES),
            "ok": kpis.get("available"),
            "ms": kpis.get("latency_ms"),
            "p": (kpis.get("protocol") or {}).get("passed"),
            "t": kpis.get("triples"),
        }
    return {
        "run_id": report["run_id"],
        "started_at": report["started_at"],
        "status": report["status"],
        "version": report["monitor"]["version"],
        "vantage": report["monitor"]["vantage"],
        "layers": report["monitor"]["layers"],
        "seconds": report.get("seconds"),
        "probes": PROBES,
        "h1": next((f["outcome"] for f in report.get("hub_findings", []) if f["id"] == "H1"), None),
        "kgs": kgs,
    }


def record(report: dict, root: Path) -> dict:
    """Store one run. Returns the paths written, for the caller to print."""
    root.mkdir(parents=True, exist_ok=True)
    written = {}
    latest = root / "latest.json"
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    written["latest"] = latest
    with (root / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(compact(report), ensure_ascii=False, separators=(",", ":")) + "\n")
    written["history"] = root / "history.jsonl"
    started = datetime.fromisoformat(report["started_at"])
    day_dir = root / "runs" / f"{started:%Y}" / f"{started:%m}"
    already = list(day_dir.glob(f"{started:%Y-%m-%d}T*.json.gz")) if day_dir.exists() else []
    if not already:
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{report['run_id']}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False)
        written["daily"] = path
    return written


def load(root: Path) -> list[dict]:
    path = root / "history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest(root: Path) -> dict | None:
    path = root / "latest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    ranked = sorted(values)
    k = (len(ranked) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ranked) - 1)
    return round(ranked[lo] + (ranked[hi] - ranked[lo]) * (k - lo), 1)


def kpis(entries: list[dict], days: int = 7, now: datetime | None = None) -> dict:
    """Per KG over the window: availability, latency percentiles, flaps and
    the series the page draws. Runs where the instrument itself was unhealthy
    are excluded: they say nothing about the endpoints."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    valid = [e for e in entries if e["status"] == "ok" and datetime.fromisoformat(e["started_at"]) >= since]
    out: dict[str, dict] = {}
    for entry in valid:
        for kid, k in entry["kgs"].items():
            s = out.setdefault(kid, {"runs": 0, "available": 0, "latency": [], "flaps": 0, "series": [], "_last": None})
            s["runs"] += 1
            if k.get("ok"):
                s["available"] += 1
            if k.get("ms") is not None:
                s["latency"].append(k["ms"])
            if s["_last"] is not None and s["_last"] != bool(k.get("ok")):
                s["flaps"] += 1
            s["_last"] = bool(k.get("ok"))
            s["series"].append({"t": entry["started_at"], "g": k["g"], "ms": k.get("ms"), "ok": k.get("ok"),
                                "fails": k["o"].count("F")})
    for s in out.values():
        s.pop("_last")
        s["availability"] = round(100 * s["available"] / s["runs"], 1) if s["runs"] else None
        s["latency_p50"] = _percentile(s["latency"], 0.5)
        s["latency_p95"] = _percentile(s["latency"], 0.95)
        s.pop("latency")
    return {"window_days": days, "runs": len(valid), "kgs": out}


def layer_series(entries: list[dict]) -> list[dict]:
    """Failing checks per layer per run: the defect curve the page draws."""
    rows = []
    for e in entries:
        if e["status"] != "ok":
            rows.append({"t": e["started_at"], "status": e["status"]})
            continue
        probes = e.get("probes", PROBES)
        counts = {"A": 0, "B": 0, "C": 0}
        for k in e["kgs"].values():
            for pid, letter in zip(probes, k["o"]):
                if letter == "F" and pid[0] in counts:
                    counts[pid[0]] += 1
        grades: dict[str, int] = {}
        for k in e["kgs"].values():
            grades[k["g"]] = grades.get(k["g"], 0) + 1
        rows.append({"t": e["started_at"], "status": "ok", "fails": counts, "grades": grades,
                     "version": e.get("version")})
    return rows


def median_or_none(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None
