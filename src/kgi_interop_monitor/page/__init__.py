"""Build the status page from a results directory.

The page is one self-contained HTML file: layout, styles, script and data are
inlined, so it opens from disk, from a CI artifact or as a hosted page without
a server. ``template.html`` is written as a page fragment (title, styles, body
content, script); :func:`build` embeds the data and, for a standalone file,
wraps the fragment in a document.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from .. import __version__, history
from ..model import SPECS

PLACEHOLDER = "/*__DATA__*/"
HEAD_END = "<!--/head-->"
"""Marks where the fragment's head material (title, fonts, styles) ends."""


def _specs() -> list[dict]:
    return [{"id": s.id, "layer": s.layer, "title": s.title, "question": s.question, "gating": s.gating,
             "basis": s.basis, "basis_url": s.basis_url, "owner": s.owner} for s in SPECS.values()]


def page_data(results: Path, window_days: int = 7) -> dict:
    report = history.latest(results)
    if report is None:
        raise FileNotFoundError(f"no latest.json in {results}; run the monitor first")
    entries = history.load(results)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "monitor_version": __version__,
        "report": report,
        "kpis": history.kpis(entries, days=window_days),
        "layers": history.layer_series(entries),
        "runs_total": len(entries),
        "specs": _specs(),
    }


def json_for_script(data: dict) -> str:
    """JSON that can sit inside <script type="application/json">.

    Escaping only "</" is not enough: evidence excerpts are HTML error pages,
    and a "<!--" followed by "<script" inside a script element puts the HTML
    parser into its double-escaped state, where "</script>" no longer closes
    the element and the page script after it is swallowed as data. Escaping
    every <, > and & as a \\u escape keeps the JSON identical once parsed.
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render(data: dict, standalone: bool = True) -> str:
    fragment = resources.files(__name__).joinpath("template.html").read_text(encoding="utf-8")
    payload = json_for_script(data)
    html = fragment.replace(PLACEHOLDER, payload)
    if standalone:
        head, _, body = html.partition(HEAD_END)
        html = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                f"{head}</head>\n<body>\n{body}\n</body>\n</html>\n")
    return html


def build(results: Path, out: Path, standalone: bool = True) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(page_data(results), standalone), encoding="utf-8")
    return out
