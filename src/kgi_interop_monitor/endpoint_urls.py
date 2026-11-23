"""
The SPARQL protocol URL of a knowledge graph whose registered
dcat:endpointURL is a query web page (a dcat:landingPage in DCAT terms):
proposed by candidates(), confirmed by an ASK {} that answers, and kept as
endpoint_url in resources/knowledge_graphs.yaml only while the registered
value does not answer by itself.

candidates() is restored from normalize.py (commit 7537fb7, deleted in
8aa7a2b).

Created on 2026-11-19

@author: danielviladrich
"""

import argparse
import re
import sys
import urllib.parse
from typing import Dict, List, Optional, Tuple

import requests

from kgi_interop_monitor.kgs import KnowledgeGraphs

# last path segments that usually name a query web page, not the endpoint
UI_TAILS = (
    "query",
    "query.html",
    "sparql-ui",
    "yasgui",
    "snorql",
    "sparql-assistent",
    "sparql-endpoint",
    "ui",
)
MAX_CANDIDATES = 10
URL_RE = re.compile(r"https?://[^\s;,<>\"'|]+", re.I)
ASK_QUERY = "ASK {}"
SPARQL_JSON = "application/sparql-results+json"


def candidates(url: str) -> List[str]:
    """
    where else the SPARQL endpoint of the given URL may be, most likely first

    Args:
        url: the registered endpoint value

    Returns:
        at most MAX_CANDIDATES URLs, the registered one excluded
    """
    parts = urllib.parse.urlsplit(url.strip())
    found: List[str] = []
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return found
    root = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")

    def add(candidate: str) -> None:
        # a trailing-slash variant of the registered URL is a real candidate:
        # some servers answer on /sparql but not /sparql/, or the reverse
        if candidate != url.strip() and candidate not in found:
            found.append(candidate)

    # a UI route after the fragment, as in Fuseki: "#/dataset/<name>/query"
    fuseki = re.match(
        r"/?dataset/([^/]+)/(query|sparql|info|edit|upload)", parts.fragment or ""
    )
    if fuseki:
        add(f"{root}{path}/{fuseki.group(1)}/sparql")
        add(f"{root}{path}/{fuseki.group(1)}/query")
    if parts.fragment or parts.query:
        add(f"{root}{path or '/'}")

    segments = [segment for segment in path.split("/") if segment]
    tail = segments[-1].lower() if segments else ""
    parent = ("/" + "/".join(segments[:-1]) if segments else "").rstrip("/")

    if tail in UI_TAILS or tail.endswith(".html"):
        add(f"{root}{parent}/sparql")
        add(f"{root}{parent}")
    if tail != "sparql":
        add(f"{root}{path}/sparql")
    add(f"{root}{path}/" if path else f"{root}/")
    if path:
        add(f"{root}{path}")
    # Wikibase query services: UI at the host root or /query, endpoint at
    # /sparql, with the Blazegraph path as the historical alternative
    if (parts.hostname or "").startswith("query.") or tail == "query":
        add(f"{root}/sparql")
        add(f"{root}/bigdata/namespace/wdq/sparql")
    add(f"{root}/sparql")
    # Fuseki-style services answer on /query (Nomisma does, next to a UI at
    # /sparql/) - a query web page there just fails the check, cheaply
    add(f"{root}/query")
    # QLever UI deployments serve the API under /api/
    add(f"{root}/api/")
    if parts.scheme == "http":
        add(urllib.parse.urlunsplit(("https",) + tuple(parts[1:4]) + ("",)))
    found = found[:MAX_CANDIDATES]
    return found


def answers_ask(url: str, timeout: float = 15.0) -> bool:
    """
    is there a SPARQL service at the given URL? - it answers ASK {} with a
    SPARQL JSON boolean, by GET or else by a form POST

    Args:
        url: the URL to ask
        timeout: seconds per request

    Returns:
        True if a SPARQL JSON boolean came back
    """
    headers = {"Accept": SPARQL_JSON, "User-Agent": "kgi-interop-monitor"}
    answered = False
    for method in ("GET", "POST"):
        try:
            if method == "GET":
                response = requests.get(
                    url, params={"query": ASK_QUERY}, headers=headers, timeout=timeout
                )
            else:
                response = requests.post(
                    url, data={"query": ASK_QUERY}, headers=headers, timeout=timeout
                )
            answered = response.ok and isinstance(response.json().get("boolean"), bool)
        except Exception:
            answered = False
        if answered:
            break
    return answered


def find_endpoint_url(
    endpoint: str, timeout: float = 15.0
) -> Tuple[Optional[str], str]:
    """
    the endpoint_url for a registered endpoint value: None when the
    registered value answers by itself or no candidate answers

    Args:
        endpoint: the registered endpoint value
        timeout: seconds per request

    Returns:
        the first candidate that answers ASK {} or None, and why
    """
    endpoint_url = None
    reason = "registered value answers"
    # several URLs packed into one value ("a; b"): each is a candidate first
    urls = [url.rstrip(".)") for url in URL_RE.findall(endpoint)]
    tries = [url for url in urls if url != endpoint.strip()]
    for url in urls[:1]:
        tries.extend(
            candidate for candidate in candidates(url) if candidate not in tries
        )
    if not answers_ask(endpoint, timeout):
        reason = "nothing answers"
        for candidate in tries[:MAX_CANDIDATES]:
            if answers_ask(candidate, timeout):
                endpoint_url = candidate
                reason = "candidate answers"
                break
    return endpoint_url, reason


def update(kgs: KnowledgeGraphs, timeout: float = 15.0) -> Dict[str, Optional[str]]:
    """
    set or remove endpoint_url for every knowledge graph whose registered
    endpoint value is a URL

    Args:
        kgs: the knowledge graphs, changed in place
        timeout: seconds per request

    Returns:
        mapping of registry id to its new endpoint_url
    """
    changes = {}
    for key, kg in kgs.kgs.items():
        if not kg.endpoint_is_url:
            continue
        endpoint_url, reason = find_endpoint_url(kg.endpoint, timeout)
        print(f"{key}: {kg.endpoint} -> {endpoint_url or '-'} ({reason})")
        kg.endpoint_url = endpoint_url
        changes[key] = endpoint_url
    return changes


def write_endpoint_urls(yaml_path: str, kgs: KnowledgeGraphs) -> None:
    """
    write the endpoint_url lines into the YAML file, right after each
    record's endpoint line, keeping everything else as it is

    Args:
        yaml_path: the knowledge graph config file
        kgs: the knowledge graphs with their endpoint_url
    """
    with open(yaml_path, encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    out = []
    key = None
    for line in lines:
        if line.lstrip().startswith("endpoint_url:"):
            continue
        out.append(line)
        match = re.match(r"^  (KGR\d+):$", line)
        if match:
            key = match.group(1)
        elif key and line.startswith("    endpoint:"):
            endpoint_url = kgs.kgs[key].endpoint_url
            if endpoint_url:
                out.append(f"    endpoint_url: {endpoint_url}")
    with open(yaml_path, "w", encoding="utf-8") as stream:
        stream.write("\n".join(out) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    """
    command line entry point: probe the registered endpoints and update the
    endpoint_url lines of the knowledge graph config file

    Args:
        argv: the command line arguments, sys.argv[1:] when None

    Returns:
        the process exit code
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--yaml", default=str(KnowledgeGraphs.default_path()))
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)
    kgs = KnowledgeGraphs.of_yaml(args.yaml)
    update(kgs, args.timeout)
    write_endpoint_urls(args.yaml, kgs)
    exit_code = 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
