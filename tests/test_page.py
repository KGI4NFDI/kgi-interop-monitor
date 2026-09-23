from __future__ import annotations

import json
import re

from kgi_interop_monitor import history, page

from .test_history import report


def evil_report():
    r = report("2026-09-23T0017Z", "2026-09-23T00:17:00+00:00")
    # An HTML error page as evidence, the shape that broke the first build:
    # "<!--" then "<script" inside a script element swallows what follows.
    r["kgs"][0]["exchanges"] = [{"id": "x1", "response": {
        "body_excerpt": "<!DOCTYPE HTML> <!-- Copyright --> <script>var a = 1;</script> </body>"}}]
    r["kgs"][0]["title"] = "KG with </script> in its name & more"
    return r


def test_embedded_data_cannot_break_out_of_its_script_element(tmp_path):
    history.record(evil_report(), tmp_path)
    html = page.render(page.page_data(tmp_path))
    data_block = re.search(r'<script type="application/json" id="kgi-data">(.*?)</script>', html, re.S).group(1)
    assert "<" not in data_block and ">" not in data_block
    data = json.loads(data_block)
    assert data["report"]["kgs"][0]["title"] == "KG with </script> in its name & more"
    assert "<!-- Copyright -->" in data["report"]["kgs"][0]["exchanges"][0]["response"]["body_excerpt"]
    # the page script follows the data block intact
    assert html.count("<script") == 2 and "JSON.parse" in html.split('id="kgi-data">', 1)[1]


def test_standalone_and_fragment(tmp_path):
    history.record(evil_report(), tmp_path)
    standalone = page.render(page.page_data(tmp_path))
    fragment = page.render(page.page_data(tmp_path), standalone=False)
    assert standalone.startswith("<!doctype html>") and "<title>KGI Query-Layer Monitor</title>" in standalone.split("</head>")[0]
    assert fragment.startswith("<title>") and "<html" not in fragment


def test_page_data_carries_catalogue_and_history(tmp_path):
    history.record(evil_report(), tmp_path)
    data = page.page_data(tmp_path)
    assert [s["id"] for s in data["specs"]][:3] == ["A1", "A2", "A3"]
    assert data["runs_total"] == 1 and data["layers"][0]["status"] == "ok"
