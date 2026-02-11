# mem0-mcp

MCP server for **self-hosted** Mem0 with Qdrant vector search + Neo4j graph memory.

> **Looking for Mem0 Cloud?** The [official mem0-mcp-server](https://pypi.org/project/mem0-mcp-server/) works with the managed platform at [app.mem0.ai](https://app.mem0.ai). This project is for self-hosted deployments where you run your own Qdrant, Ollama, and Neo4j.

## Why this exists

The official MCP server requires a Mem0 Cloud API key. If you self-host Mem0 with your own Qdrant and Ollama, there's no off-the-shelf MCP server that connects to your infrastructure. This one does.

**What it connects to:**
- **Qdrant** for vector memory (semantic search)
- **Neo4j** for graph memory (entity relationships)
- **Ollama** for embeddings (no OpenAI/Anthropic keys needed)
- **OpenMemory API** for writes (keeps SQLite + Qdrant in sync)

## Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `search_memories` | Semantic search across all memories | Ollama embed + Qdrant |
| `add_memory` | Store a new memory | OpenMemory API |
| `list_memories` | List all stored memories | Qdrant scroll |
| `delete_memory` | Delete a memory by ID | API + Qdrant fallback |
| `search_graph` | Find entity relationships | Neo4j |
| `get_entity` | Get all connections for an entity | Neo4j |

## Prerequisites

A self-hosted Mem0 stack running somewhere accessible:
- **Qdrant** (vector store)
- **Ollama** with an embedding model (e.g., `nomic-embed-text`)
- **OpenMemory API** ([mem0ai/mem0](https://github.com/mem0ai/mem0/tree/main/openmemory))
- **Neo4j 5+** Community or Enterprise (optional, for graph memory)

If these are on a remote server, use SSH tunnels to forward the ports locally.

## Setup

### 1. Install

```bash
pip install git+https://github.com/tensakulabs/mem0-mcp.git
```

### 2. Configure Claude Code

```bash
claude mcp add -s user mem0-mcp -- \
  uvx --from git+https://github.com/tensakulabs/mem0-mcp.git mem0-mcp
```

Or add to your MCP config manually:

```json
{
  "mcpServers": {
    "mem0": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tensakulabs/mem0-mcp.git", "mem0-mcp"],
      "env": {
        "MEM0_QDRANT_URL": "http://127.0.0.1:6333",
        "MEM0_OLLAMA_URL": "http://127.0.0.1:11435",
        "MEM0_API_BASE": "http://127.0.0.1:8765",
        "MEM0_NEO4J_URL": "bolt://127.0.0.1:7687",
        "MEM0_NEO4J_PASSWORD": "your-password",
        "MEM0_USER_ID": "your-user-id"
      }
    }
  }
}
```

### 3. SSH tunnels (if remote)

If your Mem0 stack is on a remote server:

```bash
ssh -f -N \
  -L 8765:127.0.0.1:8765 \
  -L 6333:127.0.0.1:6333 \
  -L 11435:127.0.0.1:11434 \
  -L 7687:127.0.0.1:7687 \
  user@your-server
```

## Configuration

All via environment variables with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM0_API_BASE` | `http://127.0.0.1:8765` | OpenMemory API (for writes) |
| `MEM0_QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant REST API |
| `MEM0_OLLAMA_URL` | `http://127.0.0.1:11435` | Ollama (for embeddings) |
| `MEM0_EMBED_MODEL` | `nomic-embed-text:latest` | Embedding model name |
| `MEM0_COLLECTION` | `openmemory` | Qdrant collection name |
| `MEM0_USER_ID` | `justin` | User ID for memory filtering |
| `MEM0_NEO4J_URL` | `bolt://127.0.0.1:7687` | Neo4j Bolt endpoint |
| `MEM0_NEO4J_USER` | `neo4j` | Neo4j username |
| `MEM0_NEO4J_PASSWORD` | `mem0graph` | Neo4j password |

## Architecture

```
Claude Code / Claude Desktop
  └── MCP stdio → mem0-mcp
        ├── READS  → Qdrant (vector search, all memories)
        ├── SEARCH → Ollama (embed query) + Qdrant (similarity)
        ├── GRAPH  → Neo4j (entity relationships)
        └── WRITES → OpenMemory API (SQLite + Qdrant sync)
```

**Why hybrid read/write?** The OpenMemory API uses SQLite as its source of truth for the memory list. If other agents (like OpenClaw) write directly to Qdrant, the API won't see those memories. Reading from Qdrant directly sees everything. Writing through the API keeps both stores in sync.

## License

MIT
