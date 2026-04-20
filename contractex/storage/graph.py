"""
LegalKnowledgeGraph — cross-document entity resolution and relationship modelling.

Provides a graph storage layer that:

* Indexes entities (parties, documents, clauses, jurisdictions) as nodes.
* Records typed relationships (PARTY_IN, REFERENCES, CONTAINS, etc.) as edges.
* Resolves the same real-world entity appearing under different names across
  documents (e.g. "Acme Corp" and "ACME CORPORATION" → same Party node).
* Exports to RDF/Turtle for interoperability with legal knowledge bases.

Backends
--------
* **networkx** — in-memory, no extra deps, suitable for development and testing.
  Install: ``pip install contractex[graph]``
* **Neo4j** — persistent graph database for production.
  Install: ``pip install contractex[graph]`` (includes ``neo4j`` driver).

Node types
----------
* Party        — organisation or person appearing in legal documents
* Document     — LegalDoc reference
* Clause       — extracted clause
* Jurisdiction — legal jurisdiction
* Citation     — one document citing another
* Concept      — CUAD clause type or legal concept from taxonomy

Edge types
----------
* PARTY_IN     — Party → Document
* REFERENCES   — Document → Document (citation)
* CONTAINS     — Document → Clause
* GOVERNED_BY  — Document → Jurisdiction
* INSTANCE_OF  — Clause → Concept
* SAME_ENTITY  — Party → Party (cross-document resolution)

Usage
-----
::

    from contractex.storage.graph import LegalKnowledgeGraph

    graph = LegalKnowledgeGraph()          # in-memory (networkx)
    graph.add_document(doc)

    # Find a party across documents
    nodes = graph.resolve_entity("Acme Corporation", "Party")

    # Subgraph around a document
    subgraph = graph.find_related(doc.doc_id, depth=2)

    # Export
    graph.export_rdf(Path("output/knowledge_graph.ttl"))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class GraphNode:
    """A node in the legal knowledge graph."""

    node_id: str
    node_type: str  # "Party", "Document", "Clause", "Jurisdiction", "Concept"
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in the legal knowledge graph."""

    source_id: str
    target_id: str
    edge_type: str  # "PARTY_IN", "REFERENCES", "CONTAINS", etc.
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subgraph:
    """A subset of the knowledge graph returned by ``find_related()``."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class LegalKnowledgeGraph:
    """
    Legal knowledge graph with pluggable backends.

    Parameters
    ----------
    backend:
        ``"networkx"`` (default) or ``"neo4j"``.
    neo4j_uri:
        Neo4j Bolt URI (required when ``backend="neo4j"``).
    neo4j_auth:
        ``(user, password)`` tuple for Neo4j auth.
    similarity_threshold:
        String similarity threshold for SAME_ENTITY resolution (0–1).
        Defaults to 0.85.
    """

    def __init__(
        self,
        backend: str = "networkx",
        neo4j_uri: str | None = None,
        neo4j_auth: tuple[str, str] | None = None,
        similarity_threshold: float = 0.85,
    ) -> None:
        self._backend_name = backend
        self._similarity_threshold = similarity_threshold
        self._graph: Any | None = None
        self._neo4j_driver: Any | None = None

        if backend == "neo4j":
            self._graph = self._init_neo4j(neo4j_uri, neo4j_auth)
        else:
            self._graph = self._init_networkx()

        # In-memory entity index for resolution (label → canonical node_id)
        self._entity_index: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_document(self, doc: Any) -> None:
        """
        Add a ``LegalDoc`` to the graph.

        Extracts Party, Clause, and Jurisdiction nodes from ``doc.extracted``
        and ``doc.metadata``.  Creates PARTY_IN, CONTAINS, and GOVERNED_BY
        edges.  Merges existing entities via ``resolve_entity()``.

        Parameters
        ----------
        doc:
            A ``LegalDoc`` (or subclass) instance.
        """
        doc_id = getattr(doc, "doc_id", str(id(doc)))
        doc_type = str(getattr(doc, "doc_type", "unknown"))
        title = getattr(doc, "metadata", None)
        title = getattr(title, "source_url", None) or doc_id

        doc_node = GraphNode(
            node_id=f"doc:{doc_id}",
            node_type="Document",
            label=title,
            properties={
                "doc_id": doc_id,
                "doc_type": doc_type,
                "jurisdiction": getattr(doc, "jurisdiction", None),
                "language": getattr(doc, "language", "en"),
            },
        )
        self._add_node(doc_node)

        # Jurisdiction
        jurisdiction = getattr(doc, "jurisdiction", None)
        if jurisdiction:
            j_id = f"jurisdiction:{jurisdiction.lower().replace(' ', '_')}"
            j_node = GraphNode(
                node_id=j_id,
                node_type="Jurisdiction",
                label=jurisdiction,
            )
            self._add_node(j_node)
            self._add_edge(
                GraphEdge(
                    source_id=doc_node.node_id,
                    target_id=j_id,
                    edge_type="GOVERNED_BY",
                )
            )

        # Parties (from doc.extracted["contract"]["parties"] or similar)
        extracted = getattr(doc, "extracted", {})
        contract = extracted.get("contract", {})
        parties = contract.get("parties", [])
        for party_data in parties:
            party_name = (
                party_data.get("name", "") if isinstance(party_data, dict) else str(party_data)
            )
            if not party_name:
                continue
            canonical = self._resolve_or_create_party(party_name)
            self._add_edge(
                GraphEdge(
                    source_id=canonical.node_id,
                    target_id=doc_node.node_id,
                    edge_type="PARTY_IN",
                    properties={
                        "role": party_data.get("role", "") if isinstance(party_data, dict) else ""
                    },
                )
            )

        # Clauses
        clauses = contract.get("clauses", [])
        for i, clause_data in enumerate(clauses):
            clause_id = f"clause:{doc_id}:{i}"
            clause_type = (
                clause_data.get("clause_type", "unknown")
                if isinstance(clause_data, dict)
                else "unknown"
            )
            clause_node = GraphNode(
                node_id=clause_id,
                node_type="Clause",
                label=clause_type,
                properties=clause_data if isinstance(clause_data, dict) else {},
            )
            self._add_node(clause_node)
            self._add_edge(
                GraphEdge(
                    source_id=doc_node.node_id,
                    target_id=clause_id,
                    edge_type="CONTAINS",
                )
            )

            # Concept link (CUAD taxonomy)
            if clause_type and clause_type != "unknown":
                concept_id = f"concept:cuad:{clause_type.lower().replace(' ', '_')}"
                concept_node = GraphNode(
                    node_id=concept_id,
                    node_type="Concept",
                    label=clause_type,
                )
                self._add_node(concept_node)
                self._add_edge(
                    GraphEdge(
                        source_id=clause_id,
                        target_id=concept_id,
                        edge_type="INSTANCE_OF",
                    )
                )

        logger.debug("Added document %r to knowledge graph", doc_id)

    def resolve_entity(self, name: str, entity_type: str) -> list[GraphNode]:
        """
        Find all graph nodes that match *name* for the given *entity_type*.

        Uses fuzzy string matching to find the canonical node plus any
        SAME_ENTITY-linked variants.

        Parameters
        ----------
        name:
            Entity name to look up (e.g. ``"Acme Corporation"``).
        entity_type:
            Node type to search (``"Party"``, ``"Jurisdiction"``, etc.).

        Returns
        -------
        list[GraphNode]
            Matching nodes, or empty list if none found.
        """
        results = []
        for node in self._all_nodes():
            if node.node_type != entity_type:
                continue
            if self._similarity(name, node.label) >= self._similarity_threshold:
                results.append(node)
        return results

    def find_related(self, doc_id: str, depth: int = 2) -> Subgraph:
        """
        Return the subgraph of documents related to *doc_id* up to *depth*
        hops away.

        Parameters
        ----------
        doc_id:
            Document identifier (not the graph node_id — the raw doc_id).
        depth:
            Number of hops to traverse.

        Returns
        -------
        Subgraph
        """
        node_id = f"doc:{doc_id}"
        return self._bfs_subgraph(node_id, depth)

    def add_citation(self, citing_doc_id: str, cited_doc_id: str) -> None:
        """
        Record that *citing_doc_id* cites *cited_doc_id*.

        Creates a REFERENCES edge between the two Document nodes.
        """
        self._add_edge(
            GraphEdge(
                source_id=f"doc:{citing_doc_id}",
                target_id=f"doc:{cited_doc_id}",
                edge_type="REFERENCES",
            )
        )

    def export_rdf(self, path: Path) -> None:
        """
        Export the graph to RDF/Turtle format.

        Requires ``rdflib`` (``pip install rdflib``).

        Parameters
        ----------
        path:
            Output ``.ttl`` file path.
        """
        try:
            from rdflib import RDF, Graph, Literal, Namespace, URIRef

            g = Graph()
            LEX = Namespace("https://contractex.io/ontology/")
            g.bind("lex", LEX)

            for node in self._all_nodes():
                subj = URIRef(f"https://contractex.io/entity/{node.node_id}")
                g.add((subj, RDF.type, LEX[node.node_type]))
                g.add((subj, LEX.label, Literal(node.label)))
                for k, v in node.properties.items():
                    if v is not None:
                        g.add((subj, LEX[k], Literal(str(v))))

            for edge in self._all_edges():
                s = URIRef(f"https://contractex.io/entity/{edge.source_id}")
                o = URIRef(f"https://contractex.io/entity/{edge.target_id}")
                g.add((s, LEX[edge.edge_type], o))

            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            g.serialize(destination=str(path), format="turtle")
            logger.info("Exported RDF graph to %s", path)

        except ImportError:
            raise ImportError(
                "rdflib is required for RDF export.\n" "Install with: pip install rdflib"
            ) from None

    # ------------------------------------------------------------------
    # Backend-specific internals
    # ------------------------------------------------------------------

    def _init_networkx(self) -> Any:
        try:
            import networkx as nx

            g = nx.DiGraph()
            return g
        except ImportError:
            raise ImportError(
                "networkx is required for the in-memory graph backend.\n"
                "Install with: pip install contractex[graph]"
            ) from None

    def _init_neo4j(self, uri: str | None, auth: tuple[str, str] | None) -> Any:
        try:
            from neo4j import GraphDatabase

            if not uri:
                raise ValueError("neo4j_uri is required for Neo4j backend")
            driver = GraphDatabase.driver(uri, auth=auth)
            self._neo4j_driver = driver
            return driver
        except ImportError:
            raise ImportError(
                "neo4j driver is required for the Neo4j backend.\n"
                "Install with: pip install contractex[graph]"
            ) from None

    def _add_node(self, node: GraphNode) -> None:
        if self._backend_name == "networkx":
            if not self._graph.has_node(node.node_id):
                self._graph.add_node(
                    node.node_id,
                    node_type=node.node_type,
                    label=node.label,
                    **node.properties,
                )
        else:
            self._neo4j_upsert_node(node)

    def _add_edge(self, edge: GraphEdge) -> None:
        if self._backend_name == "networkx":
            self._graph.add_edge(
                edge.source_id,
                edge.target_id,
                edge_type=edge.edge_type,
                **edge.properties,
            )
        else:
            self._neo4j_upsert_edge(edge)

    def _all_nodes(self) -> list[GraphNode]:
        if self._backend_name == "networkx":
            return [
                GraphNode(
                    node_id=nid,
                    node_type=data.get("node_type", ""),
                    label=data.get("label", nid),
                    properties={k: v for k, v in data.items() if k not in ("node_type", "label")},
                )
                for nid, data in self._graph.nodes(data=True)
            ]
        return []

    def _all_edges(self) -> list[GraphEdge]:
        if self._backend_name == "networkx":
            return [
                GraphEdge(
                    source_id=u,
                    target_id=v,
                    edge_type=data.get("edge_type", ""),
                    properties={k: v2 for k, v2 in data.items() if k != "edge_type"},
                )
                for u, v, data in self._graph.edges(data=True)
            ]
        return []

    def _bfs_subgraph(self, root_id: str, depth: int) -> Subgraph:
        if self._backend_name != "networkx":
            return Subgraph(nodes=[], edges=[])

        import networkx as nx

        try:
            nodes_in_range = nx.single_source_shortest_path_length(
                self._graph.to_undirected(), root_id, cutoff=depth
            )
        except nx.NodeNotFound:
            return Subgraph(nodes=[], edges=[])

        node_ids = set(nodes_in_range.keys())
        nodes = [
            GraphNode(
                node_id=nid,
                node_type=self._graph.nodes[nid].get("node_type", ""),
                label=self._graph.nodes[nid].get("label", nid),
            )
            for nid in node_ids
            if self._graph.has_node(nid)
        ]
        edges = [
            GraphEdge(source_id=u, target_id=v, edge_type=d.get("edge_type", ""))
            for u, v, d in self._graph.edges(data=True)
            if u in node_ids and v in node_ids
        ]
        return Subgraph(nodes=nodes, edges=edges)

    def _resolve_or_create_party(self, name: str) -> GraphNode:
        """Find or create a Party node for *name*, merging similar names."""
        # Check existing parties for similarity
        for node in self._all_nodes():
            if node.node_type != "Party":
                continue
            sim = self._similarity(name, node.label)
            if sim >= self._similarity_threshold:
                # Link as SAME_ENTITY if not exact match
                if name.lower() != node.label.lower():
                    new_id = f"party:{name.lower().replace(' ', '_')}"
                    new_node = GraphNode(node_id=new_id, node_type="Party", label=name)
                    self._add_node(new_node)
                    self._add_edge(
                        GraphEdge(
                            source_id=new_id,
                            target_id=node.node_id,
                            edge_type="SAME_ENTITY",
                        )
                    )
                    return new_node
                return node

        # Create new party node
        node_id = f"party:{name.lower().replace(' ', '_').replace('.', '')}"
        node = GraphNode(node_id=node_id, node_type="Party", label=name)
        self._add_node(node)
        return node

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Simple normalized edit-distance similarity."""
        from difflib import SequenceMatcher

        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    # ------------------------------------------------------------------
    # Neo4j stubs (full implementation via driver sessions)
    # ------------------------------------------------------------------

    def _neo4j_upsert_node(self, node: GraphNode) -> None:
        if self._neo4j_driver is None:
            return
        with self._neo4j_driver.session() as session:
            session.run(
                f"MERGE (n:{node.node_type} {{node_id: $node_id}}) "
                "SET n.label = $label, n += $props",
                node_id=node.node_id,
                label=node.label,
                props=node.properties,
            )

    def _neo4j_upsert_edge(self, edge: GraphEdge) -> None:
        if self._neo4j_driver is None:
            return
        with self._neo4j_driver.session() as session:
            session.run(
                "MATCH (a {node_id: $src}), (b {node_id: $tgt}) "
                f"MERGE (a)-[r:{edge.edge_type}]->(b) "
                "SET r += $props",
                src=edge.source_id,
                tgt=edge.target_id,
                props=edge.properties,
            )
