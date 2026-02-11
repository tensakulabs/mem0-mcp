"""MCP server for self-hosted Mem0 with Qdrant vector + Neo4j graph memory."""

import os

from mem0_mcp.server import mcp


def main():
    transport = os.environ.get("MEM0_TRANSPORT", "stdio")
    mcp.run(transport=transport)
