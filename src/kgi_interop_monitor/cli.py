"""Command line: ``kgi-interop-monitor run`` and friends."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, history, registry
from .model import SPECS
from .runner import CONTROL_URL, RunConfig, run

SYMBOL = {"pass": "+", "warn": "!", "fail": "X", "unknown": "?", "blocked": "#", "n/a": "."}


def table(report: dict) -> str:
    probes = [p for p in SPECS if any(p in kg["results"] for kg in report["kgs"])]
    lines = [f"{'id':7} {'title':34} {'grade':6} {'fixed':6} {'ms':>6} {'P':>5} " + " ".join(f"{p:2}" for p in probes)]
    for kg in sorted(report["kgs"], key=lambda k: (k["title"].lower(), k["id"])):
        cells = " ".join(f"{SYMBOL.get(kg['results'].get(p, {}).get('outcome', ''), ' '):2}" for p in probes)
        kpis = kg.get("kpis", {})
        ms = f"{kpis['latency_ms']:.0f}" if kpis.get("latency_ms") else "-"
        proto = f"{kpis['protocol']['passed']}/{kpis['protocol']['total']}" if kpis.get("protocol") else "-"
        lines.append(f"{kg['id']:7} {kg['title'][:34]:34} {kg['grade']:6} {kg['grade_if_registry_fixed']:6} "
                     f"{ms:>6} {proto:>5} {cells}")
    lines.append("")
    lines.append("+ pass  ! warn  X fail  ? unknown  # blocked  . n/a")
    return "\n".join(lines)


def cmd_run(args: argparse.Namespace) -> int:
    config = RunConfig(
        registry_endpoint=args.registry,
        hub_endpoint=args.hub,
        control_url=args.control,
        only=set(args.only.split(",")) if args.only else None,
        layers=args.layers,
        max_workers=args.workers,
        heavy=args.heavy,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    )
    report = run(config)
    written = history.record(report, Path(args.results))
    paths = ", ".join(str(p) for p in written.values())
    if report["status"] != "ok":
        print(f"run {report['run_id']}: {report['status']}: {report.get('status_detail', '')}", file=sys.stderr)
        print(f"wrote {paths}")
        return 2
    print(table(report))
    s = report["summary"]
    print(f"\n{s['kgs']} records; working as registered {s['working_as_registered']}, "
          f"after repair {s['working_after_repair']}; grades {s['grades']}; {report['seconds']} s")
    for finding in report["registry_findings"]:
        print(f"registry {finding['id']} [{finding['outcome']}] {finding['summary']}")
    for finding in report.get("hub_findings", []):
        print(f"hub      {finding['id']} [{finding['outcome']}] {finding['summary']}")
    print(f"wrote {paths}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kgi-interop-monitor", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="run the checklist probes against the registry")
    p.add_argument("--registry", default=registry.KGI_HUB, help="SPARQL endpoint of the KGI registry")
    p.add_argument("--hub", default=registry.KGI_HUB, help="federation hub used for B4")
    p.add_argument("--control", default=CONTROL_URL, help="independent URL for the control probe")
    p.add_argument("--only", help="comma-separated record ids, e.g. KGR28,KGR74")
    p.add_argument("--layers", default="ABC", help="layers to run, e.g. A or AB")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--heavy", action="store_true", help="also run scan-prone probes on large endpoints")
    p.add_argument("--connect-timeout", type=float, default=10.0)
    p.add_argument("--read-timeout", type=float, default=30.0)
    p.add_argument("--results", default="results", help="results directory (latest.json, history.jsonl, runs/)")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
