"""
The one list of tools a model may call.

Three places used to name `get_weather` directly — the bind at model-build time,
the "is this a tool I know?" check in the loop, and the invoke. All three now
read from here, so a second tool is a new module plus one line in TOOLS.
"""

from langchain_core.tools import BaseTool

from app.ai.tools.weather import get_weather

TOOLS: list[BaseTool] = [get_weather]

_BY_NAME: dict[str, BaseTool] = {tool.name: tool for tool in TOOLS}


def get_tool(name: str) -> BaseTool | None:
    """The tool with this name, or None if the model invented one."""
    return _BY_NAME.get(name)
