"""
The tools a model may call, in two kinds.

`TOOLS` are the app's own: the same weather webhook whoever asks. They are a
module-level constant because they are genuinely global.

MCP tools are not. They belong to one user, reach into that user's account and
carry that user's credential, so they can only be resolved with a user id in
hand — which is what `tools_for_user` is for. Nothing here caches them; that is
app/ai/mcp/client.py's job, and it is careful about it.
"""

from langchain_core.tools import BaseTool

from app.ai.tools.weather import get_weather

TOOLS: list[BaseTool] = [get_weather]


async def tools_for_user(user_id: str, mode: str = "read") -> list[BaseTool]:
    """
    Everything this user may call this turn: the shared tools plus their own.

    `mode` is "read" or "write" and selects which face of the MCP servers is
    used — see app/ai/mcp/config.py. It defaults to "read" so that a caller who
    forgets to pass it gets the safe half rather than push access.

    Falls back to the shared tools alone if MCP resolution fails. A GitHub
    outage should cost the user their GitHub tools, not their whole turn.
    """
    # Imported inside the function so app/ai/tools/ stays importable without
    # dragging in the connector repository and the database with it.
    from app.ai.mcp.client import tools_for

    if not user_id:
        return list(TOOLS)

    return [*TOOLS, *await tools_for(user_id, mode)]
