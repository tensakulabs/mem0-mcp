"""
mem0-mcp server — MCP tools for self-hosted Mem0 memory.

Reads from Qdrant directly (sees ALL memories across agents).
Writes via OpenMemory API (keeps SQLite + Qdrant in sync).
Queries Neo4j for graph memory (entity relationships).
"""

import os
import json
import httpx
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP

# --- Configuration ---

API_BASE = os.environ.get("MEM0_API_BASE", "http://127.0.0.1:8765")
QDRANT_URL = os.environ.get("MEM0_QDRANT_URL", "http://127.0.0.1:6333")
OLLAMA_URL = os.environ.get("MEM0_OLLAMA_URL", "http://127.0.0.1:11435")
EMBED_MODEL = os.environ.get("MEM0_EMBED_MODEL", "nomic-embed-text:latest")
EMBED_PROVIDER = os.environ.get("MEM0_EMBED_PROVIDER", "ollama")  # "ollama" or "openai"
EMBED_API_KEY = os.environ.get("MEM0_EMBED_API_KEY", "")
EMBED_BASE_URL = os.environ.get("MEM0_EMBED_BASE_URL", "")
COLLECTION = os.environ.get("MEM0_COLLECTION", "openmemory")
USER_ID = os.environ.get("MEM0_USER_ID", "justin")

NEO4J_URL = os.environ.get("MEM0_NEO4J_URL", "bolt://127.0.0.1:7687")
NEO4J_USER = os.environ.get("MEM0_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("MEM0_NEO4J_PASSWORD", "mem0graph")

# --- Server ---

mcp = FastMCP("mem0", instructions=(
    "Memory tools for persistent cross-session memory. "
    "Use search_memories to find relevant context before starting work. "
    "Use add_memory to store important facts, preferences, and decisions. "
    "Use search_graph to find relationships between entities."
))

# --- Clients ---

api_client = httpx.Client(base_url=API_BASE, timeout=30)
qdrant_client = httpx.Client(base_url=QDRANT_URL, timeout=30)
ollama_client = httpx.Client(base_url=OLLAMA_URL, timeout=60)
embed_client = (
    httpx.Client(
        base_url=EMBED_BASE_URL,
        headers={"Authorization": f"Bearer {EMBED_API_KEY}"},
        timeout=30,
    )
    if EMBED_PROVIDER == "openai" and EMBED_BASE_URL
    else None
)

_neo4j_driver = None


def _get_neo4j():
    """Lazy-init Neo4j driver (only connects when graph tools are used)."""
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    return _neo4j_driver


# --- Helpers ---


def _embed(text: str) -> list[float]:
    """Get embedding vector from configured provider (Ollama or OpenAI-compatible)."""
    if EMBED_PROVIDER == "openai" and embed_client:
        resp = embed_client.post(
            "/embeddings",
            json={"model": EMBED_MODEL, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    resp = ollama_client.post(
        "/api/embed",
        json={"model": EMBED_MODEL, "input": text},
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def _extract_memory(payload: dict) -> str:
    """Extract memory text from Qdrant payload (handles both schemas)."""
    return payload.get("data", payload.get("memory", payload.get("text", "unknown")))


# --- Vector Memory Tools ---


@mcp.tool()
def search_memories(query: str) -> str:
    """Semantically search memories for relevant context.

    Use this at the start of tasks to recall relevant preferences,
    decisions, patterns, and facts from previous sessions.

    Args:
        query: Natural language search query (e.g., "TypeScript preferences",
               "server architecture", "coding style")
    """
    vector = _embed(query)
    resp = qdrant_client.post(
        f"/collections/{COLLECTION}/points/search",
        json={
            "vector": vector,
            "limit": 10,
            "with_payload": True,
            "filter": {
                "should": [
                    {"key": "user_id", "match": {"value": USER_ID}},
                    {"key": "userId", "match": {"value": USER_ID}},
                ]
            },
        },
    )
    resp.raise_for_status()
    results = resp.json().get("result", [])
    if not results:
        return "No matching memories found."
    lines = []
    for r in results:
        content = _extract_memory(r.get("payload", {}))
        score = r.get("score", 0)
        lines.append(f"- {content} (relevance: {score:.2f})")
    return "\n".join(lines)


@mcp.tool()
def add_memory(text: str) -> str:
    """Store a new memory for future recall.

    Use this to remember important facts, user preferences, architectural
    decisions, project context, and lessons learned.

    Args:
        text: The fact or information to remember (e.g., "Justin prefers
              TypeScript over Python for new projects")
    """
    resp = api_client.post(
        "/api/v1/memories/",
        json={"text": text, "user_id": USER_ID},
    )
    resp.raise_for_status()
    data = resp.json()
    if data is None:
        return f"Memory submitted successfully (stored via {API_BASE})"
    results = data.get("results", data.get("items", []))
    if results:
        stored = [
            r.get("memory", r.get("text", ""))
            for r in results
            if r.get("event") in ("ADD", "UPDATE", None)
        ]
        if stored:
            return f"Stored {len(stored)} memory/memories: " + "; ".join(stored)
    return f"Memory processed. Response: {json.dumps(data)[:500]}"


@mcp.tool()
def list_memories() -> str:
    """List all stored memories for the current user.

    Returns all memories from both Arc and Atlas in the shared store.
    """
    resp = qdrant_client.post(
        f"/collections/{COLLECTION}/points/scroll",
        json={
            "limit": 100,
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "should": [
                    {"key": "user_id", "match": {"value": USER_ID}},
                    {"key": "userId", "match": {"value": USER_ID}},
                ]
            },
        },
    )
    resp.raise_for_status()
    points = resp.json().get("result", {}).get("points", [])
    if not points:
        return "No memories stored."
    lines = []
    for p in points:
        payload = p.get("payload", {})
        content = _extract_memory(payload)
        mid = str(p.get("id", ""))[:8]
        source = payload.get("source_app", payload.get("runId", "unknown"))
        lines.append(f"- [{mid}] ({source}) {content}")
    return f"{len(points)} memories:\n" + "\n".join(lines)


@mcp.tool()
def delete_memory(memory_id: str) -> str:
    """Delete a specific memory by its ID.

    Args:
        memory_id: The full UUID of the memory to delete
    """
    # Try OpenMemory API first (cleans up SQLite + Qdrant)
    try:
        resp = api_client.delete(f"/api/v1/memories/{memory_id}/")
        resp.raise_for_status()
        return f"Deleted memory {memory_id}"
    except httpx.HTTPStatusError:
        pass
    # Fallback: delete directly from Qdrant (for Atlas-created memories)
    resp = qdrant_client.post(
        f"/collections/{COLLECTION}/points/delete",
        json={"points": [memory_id]},
    )
    resp.raise_for_status()
    return f"Deleted memory {memory_id} (from Qdrant directly)"


# --- Graph Memory Tools ---


@mcp.tool()
def search_graph(query: str) -> str:
    """Search the knowledge graph for entity relationships.

    Finds entities matching the query and their connections.
    Use this to understand relationships between people, projects,
    technologies, and concepts.

    Args:
        query: Entity or topic to search for (e.g., "Justin", "OpenClaw",
               "Hetzner server")
    """
    driver = _get_neo4j()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (n)
            WHERE toLower(n.name) CONTAINS toLower($search_term)
               OR toLower(n.id) CONTAINS toLower($search_term)
            OPTIONAL MATCH (n)-[r]->(m)
            RETURN n.name AS source, n.id AS source_id,
                   type(r) AS relation, r.relationship AS rel_detail,
                   m.name AS target, m.id AS target_id
            LIMIT 25
            """,
            search_term=query,
        )
        records = list(result)

    if not records:
        return f"No graph entities found matching '{query}'."

    lines = []
    seen = set()
    for rec in records:
        source = rec["source"] or rec["source_id"] or "?"
        if rec["relation"]:
            rel = rec["rel_detail"] or rec["relation"]
            target = rec["target"] or rec["target_id"] or "?"
            key = (source, rel, target)
            if key not in seen:
                seen.add(key)
                lines.append(f"- {source} --[{rel}]--> {target}")
        else:
            if source not in seen:
                seen.add(source)
                lines.append(f"- {source} (no relationships)")

    return f"{len(lines)} graph results:\n" + "\n".join(lines)


@mcp.tool()
def get_entity(name: str) -> str:
    """Get all relationships for a specific entity.

    Returns both incoming and outgoing connections.

    Args:
        name: The entity name (e.g., "Justin", "TypeScript", "Hetzner")
    """
    driver = _get_neo4j()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (n)
            WHERE toLower(n.name) = toLower($entity_name)
               OR toLower(n.id) = toLower($entity_name)
            OPTIONAL MATCH (n)-[r_out]->(target)
            OPTIONAL MATCH (source)-[r_in]->(n)
            RETURN n.name AS entity,
                   collect(DISTINCT {rel: type(r_out), detail: r_out.relationship, target: target.name}) AS outgoing,
                   collect(DISTINCT {rel: type(r_in), detail: r_in.relationship, source: source.name}) AS incoming
            """,
            entity_name=name,
        )
        records = list(result)

    if not records or not records[0]["entity"]:
        return f"Entity '{name}' not found in graph."

    rec = records[0]
    lines = [f"Entity: {rec['entity']}"]

    outgoing = [r for r in rec["outgoing"] if r["rel"]]
    if outgoing:
        lines.append("\nOutgoing:")
        for r in outgoing:
            rel = r["detail"] or r["rel"]
            lines.append(f"  --> [{rel}] {r['target'] or '?'}")

    incoming = [r for r in rec["incoming"] if r["rel"]]
    if incoming:
        lines.append("\nIncoming:")
        for r in incoming:
            rel = r["detail"] or r["rel"]
            lines.append(f"  <-- [{rel}] {r['source'] or '?'}")

    if not outgoing and not incoming:
        lines.append("  (no relationships)")

    return "\n".join(lines)
