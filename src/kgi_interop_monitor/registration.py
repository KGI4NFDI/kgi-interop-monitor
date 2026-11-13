"""
The data contribution form of the KGI4NFDI registry, filled with the
registered values of an existing record, as a link that opens a new issue on
GitHub - the issue is only created when a person submits it there.

Created on 2026-10-26

@author: danielviladrich
"""

import json
from typing import Dict, List
from urllib.parse import urlencode


class RegistrationForm:
    """
    the registry's data contribution form for one knowledge graph, filled with
    its registered values
    """

    NEW_ISSUE_URL = "https://github.com/KGI4NFDI/kgi4nfdi_registry_data/issues/new"
    # the registry's issue template - it adds the labels and assignees the
    # admins triage by, also for people without triage rights; the link's
    # body replaces its text
    TEMPLATE = "data-contribution.md"
    TITLE = "[KGI registry entry]"
    RECORD_PREFIX = "http://kgi.services.base4nfdi.de/entity/"
    # the registry refers to consortia, institutions and contacts by Wikidata item
    WIKIDATA_ENTITY = "http://www.wikidata.org/entity/"
    # the instructions of .github/ISSUE_TEMPLATE/data-contribution.md
    INSTRUCTIONS = """To add new KG resources to the KGI registry:
1. Please fill out the following metadata attributes, delete any instructional or example text in [] brackets,
2. add a note to the registry admins in the note field below if necessary. Most fields require text, URL or Wikidata item ID.
3. If there is no Wikidata item for the value you require, please add it to Wikidata first, then mention its QID.
4. Please USE the spaced bullet points as in the template.
5. Please DON'T remove the fenced YAML block
6. If some non-essential values are missing, remove the brackets placeholders"""
    # form label, registry field and kind of value in the order of the
    # template: text, text list, url, url list or comma separated urls, items
    # - license, subjects and KG software are not stored by the registry
    FIELDS = [
        ("Name of the KG*", "name", "text"),
        ("Description", "description", "text"),
        ("Related NFDI consortium", "consortium", "items"),
        ("Related institution", "institution", "items"),
        ("Contact point*", "contact", "items"),
        ("License(s)*", "license", "items"),
        ("Subject(s)", "subjects", "items"),
        ("KG software", "kg_software", "items"),
        ("KG URL", "website", "text"),
        ("URLs for SPARQL endpoint*", "endpoint", "list"),
        ("URL for (REST) API", "api", "comma"),
        ("URL for dump files", "dumps", "comma"),
        ("Standard ontology(ies)", "ontologies", "list"),
    ]

    def __init__(self, key: str, fields: Dict[str, List[str]], labels: Dict[str, str]):
        """
        constructor

        Args:
            key: the registry id of the record the form updates
            fields: the registered values per field
            labels: the English labels of the Wikidata items
        """
        self.key = key
        self.fields = fields
        self.labels = labels

    def values(self, field: str) -> List[str]:
        """
        the registered values of the given field

        Args:
            field: the registry field

        Returns:
            the values, empty when there are none
        """
        values = list(self.fields.get(field, []))
        return values

    @staticmethod
    def quoted(value: str) -> str:
        """
        a value as YAML double-quoted scalar - non-ASCII characters as they
        are, since people read the issue

        Args:
            value: the value

        Returns:
            the quoted value
        """
        quoted = json.dumps(value, ensure_ascii=False)
        return quoted

    def item_line(self, value: str) -> str:
        """
        a Wikidata item as list entry: the bare QID the registry's
        convert_yaml_to_rdf.py needs, the label as comment

        Args:
            value: the item IRI as the registry stores it

        Returns:
            the YAML list entry
        """
        line = f"- {self.quoted(value)}"
        if value.startswith(self.WIKIDATA_ENTITY):
            line = f"- {value.removeprefix(self.WIKIDATA_ENTITY)}"
            label = self.labels.get(value)
            if label:
                line += f"  # {label}"
        return line

    def yaml_block(self) -> str:
        """
        the YAML of the form - every field present, as the registry's
        convert_yaml_to_rdf.py reads each of them

        Returns:
            the YAML lines, without the fence
        """
        lines = []
        for label, field, kind in self.FIELDS:
            values = self.values(field)
            if kind == "text":
                # the converter strips these, so never null
                lines.append(f"{label}: {self.quoted(values[0] if values else '')}")
            elif kind == "comma":
                lines.append(f"{label}: {self.quoted(', '.join(values))}")
            elif not values:
                lines.append(f"{label}: []")
            else:
                lines.append(f"{label}:")
                for value in values:
                    line = self.item_line(value) if kind == "items" else None
                    lines.append(line or f"- {self.quoted(value)}")
        yaml_block = "\n".join(lines)
        return yaml_block

    def note(self) -> str:
        """
        the note to the registry admins: which record the form updates

        Returns:
            the note
        """
        record = f"{self.RECORD_PREFIX}{self.key}"
        note = (
            f"This updates the existing registry record {self.key} ({record}) - "
            "please replace that record instead of adding a new one."
        )
        return note

    def title(self) -> str:
        """
        the issue title

        Returns:
            the template's title with the record and its name
        """
        name = (self.values("name") or [""])[0]
        title = f"{self.TITLE} Update {self.key}: {name}"
        return title

    def body(self) -> str:
        """
        the issue body: the template's instructions, the filled YAML block and
        the note to the admins

        Returns:
            the markdown of the issue
        """
        body = (
            f"{self.INSTRUCTIONS}\n\n```yaml\n{self.yaml_block()}\n```\n"
            f"Note to admin: {self.note()}\n\n*required fields."
        )
        return body

    def url(self) -> str:
        """
        the link that opens the filled form as a new issue on GitHub, from the
        registry's template so the issue gets its labels and assignees -
        labels and assignees in the link itself would need triage rights and
        give everyone else a 404

        Returns:
            the URL
        """
        query = urlencode(
            {"template": self.TEMPLATE, "title": self.title(), "body": self.body()}
        )
        url = f"{self.NEW_ISSUE_URL}?{query}"
        return url
