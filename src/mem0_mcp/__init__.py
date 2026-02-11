"""MCP server for self-hosted Mem0 with Qdrant vector + Neo4j graph memory."""

from mem0_mcp.server import mcp


def main():
    mcp.run(transport="stdio")
