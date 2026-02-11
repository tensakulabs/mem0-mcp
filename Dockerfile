FROM python:3.10-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

# Default: stdio (for Claude Code local MCP)
# Override with MEM0_TRANSPORT=sse for remote server mode
ENV MEM0_TRANSPORT=stdio
ENV MEM0_SSE_PORT=8080

EXPOSE 8080

CMD ["mem0-mcp"]
