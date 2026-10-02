"""
The knowledge graphs of the KGI4NFDI registry, kept in
resources/knowledge_graphs.yaml.

Created on 2026-09-29

@author: danielviladrich
"""

from dataclasses import field
from pathlib import Path
from typing import Dict, Optional

from basemkit.yamlable import lod_storable


@lod_storable
class KnowledgeGraph:
    """
    one knowledge graph record of the KGI4NFDI registry
    """

    name: str
    # label of the NFDI consortium that created the knowledge graph
    consortium: Optional[str] = None
    website: Optional[str] = None
    # dcat:endpointURL exactly as the registry stores it - can be prose or
    # several URLs packed into one value
    endpoint: Optional[str] = None

    @property
    def endpoint_is_url(self) -> bool:
        """
        is the registered endpoint value a URL?
        """
        is_url = bool(self.endpoint) and self.endpoint.startswith(
            ("http://", "https://")
        )
        return is_url


@lod_storable
class KnowledgeGraphs:
    """
    the knowledge graphs of the KGI4NFDI registry, keyed by registry id
    """

    # where and when the snapshot was taken
    source: str = ""
    fetched: Optional[str] = None
    consortium_source: Optional[str] = None
    kgs: Dict[str, KnowledgeGraph] = field(default_factory=dict)

    @classmethod
    def default_path(cls) -> Path:
        """
        the config file shipped with the package

        Returns:
            the path of resources/knowledge_graphs.yaml
        """
        yaml_path = Path(__file__).parent / "resources" / "knowledge_graphs.yaml"
        return yaml_path

    @classmethod
    def of_yaml(cls, yaml_path: Optional[str] = None) -> "KnowledgeGraphs":
        """
        read the knowledge graphs from the given config file

        Args:
            yaml_path: the config file, the shipped one when None

        Returns:
            the knowledge graphs
        """
        if yaml_path is None:
            yaml_path = cls.default_path()
        kgs = cls.load_from_yaml_file(str(yaml_path))
        return kgs
