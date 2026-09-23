"""Reference releases for C4 (version lag) and C5 (module or ontology).

The table in references.json says which served owl:Ontology is a version of
which published ontology. That is a curated judgement, not something a probe
can infer, so it lives in data with its sources and gets reviewed like code.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from importlib import resources

from .transport import exchange, follow

VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)")


@dataclass(frozen=True)
class Reference:
    name: str
    repo: str
    ontology_iris: tuple[str, ...]
    class_prefix: str
    release_file: str

    def matches(self, ontology_iri: str) -> bool:
        return any(ontology_iri.rstrip("/#") == iri.rstrip("/#") for iri in self.ontology_iris)


def load() -> list[Reference]:
    data = json.loads(resources.files("kgi_interop_monitor").joinpath("references.json").read_text(encoding="utf-8"))
    return [Reference(o["name"], o["repo"], tuple(o["ontology_iris"]), o["class_prefix"], o["release_file"])
            for o in data["ontologies"]]


def version_tuple(text: str | None) -> tuple[int, ...] | None:
    match = VERSION_RE.search(text or "")
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def version_text(version: tuple[int, ...] | None) -> str | None:
    return ".".join(map(str, version)) if version else None


class ReleaseSource:
    """Latest GitHub release and labelled-class count of each reference,
    fetched once per run and shared between threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tags: dict[str, tuple[str | None, str]] = {}
        self._counts: dict[tuple[str, str], tuple[int | None, str]] = {}

    def latest_tag(self, ref: Reference) -> tuple[str | None, str]:
        """(tag, note). A None tag comes with the reason."""
        with self._lock:
            if ref.repo not in self._tags:
                headers = {"Accept": "application/vnd.github+json"}
                token = os.environ.get("GITHUB_TOKEN")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                x = exchange("GET", f"https://api.github.com/repos/{ref.repo}/releases/latest", headers=headers,
                             purpose="C4 release")
                if x.status == 200:
                    tag = json.loads(x.text()).get("tag_name")
                    self._tags[ref.repo] = (tag, f"latest release of {ref.repo}")
                else:
                    self._tags[ref.repo] = (None, f"GitHub answered {x.status or x.error_class} for {ref.repo}")
            return self._tags[ref.repo]

    def release_class_count(self, ref: Reference, tag: str) -> tuple[int | None, str]:
        key = (ref.repo, tag)
        with self._lock:
            if key not in self._counts:
                url = ref.release_file.format(tag=tag)
                hops = follow("GET", url, headers={"Accept": "text/turtle, */*;q=0.1"}, purpose="C5 release file",
                              read_timeout=60)
                x = hops[-1]
                if x.status != 200:
                    self._counts[key] = (None, f"release file {url} answered {x.status or x.error_class}")
                else:
                    self._counts[key] = (count_labelled_classes(x.body, ref.class_prefix), url)
            return self._counts[key]


def count_labelled_classes(turtle: bytes, prefix: str) -> int:
    from rdflib import Graph
    from rdflib.namespace import OWL, RDF, RDFS

    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    return len({c for c in graph.subjects(RDF.type, OWL.Class)
                if str(c).startswith(prefix) and graph.value(c, RDFS.label) is not None})
