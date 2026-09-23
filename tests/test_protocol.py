from __future__ import annotations

import pytest

from kgi_interop_monitor.protocol import TESTS, run_suite

from .fake_endpoint import FakeEndpoints


@pytest.fixture(scope="module")
def fake():
    with FakeEndpoints() as f:
        yield f


def by_id(suite):
    return {t["id"]: t for t in suite["tests"]}


def test_thirteen_read_only_tests_and_no_put():
    assert len(TESTS) == 13
    assert {t.method for t in TESTS} == {"GET", "POST"}
    assert not any(t.id.startswith("update") for t in TESTS)


def test_healthy_endpoint(fake):
    suite = run_suite(fake.url("/healthy/sparql"))
    t = by_id(suite)
    for tid in ("query_get", "query_post_form", "query_post_direct", "query_content_type_select",
                "query_content_type_ask", "bad_multiple_queries", "bad_query_wrong_media_type",
                "bad_query_missing_form_type", "bad_query_missing_direct_type", "bad_query_non_utf8",
                "bad_query_syntax"):
        assert t[tid]["passed"], (tid, t[tid]["detail"])
    assert suite["total"] == 13 and suite["passed"] == 13


def test_virtuoso_like_fails_form_post_and_syntax(fake):
    t = by_id(run_suite(fake.url("/virtuoso/sparql")))
    assert not t["query_post_form"]["passed"] and "boolean" in t["query_post_form"]["detail"]
    assert not t["bad_query_syntax"]["passed"] and "HTTP 200" in t["bad_query_syntax"]["detail"]
    assert t["query_get"]["passed"] and t["query_post_direct"]["passed"]


def test_a_web_page_passes_nothing_positive(fake):
    t = by_id(run_suite(fake.url("/ui/")))
    assert not any(t[x]["passed"] for x in ("query_get", "query_post_form", "query_post_direct"))
