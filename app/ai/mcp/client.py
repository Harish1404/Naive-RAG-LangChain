"""
Resolving a user id to that user's live MCP tools.

Listing tools is a network round-trip to the provider's MCP server, so results
are cached per user for a short TTL. Read the warning on the cache before
changing anything here.
"""

import logging
import time
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.ai.mcp.config import READ, SERVERS, MCPServer
from app.core import crypto
from app.core.config import settings
from app.repositories.connector_repo import STATUS_CONNECTED, connector_repo

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# The cache.
#
# Keyed on (user_id, mode), and both halves of that key are load-bearing.
#
# user_id, because a cached BaseTool closes over the connection it was built
# from and that connection carries the user's bearer token in its headers.
# Widening to something shared — a provider name, a "default" bucket — hands one
# user another user's GitHub account.
#
# mode, because the read face and the write face are different tool sets from
# different endpoints. Sharing one entry between them would let a turn that only
# meant to read a repository be handed push_files and create_pull_request, which
# is exactly the pairing the read/write split exists to prevent.
#
# Three rules follow:
#   * never read an entry for a user other than the one asking
#   * never read an entry for a mode other than the one asked for
#   * always invalidate on connect and disconnect, or a disconnected user keeps
#     working from tools built with the token we just revoked
# ─────────────────────────────────────────────────────────────────────────────
_cache: dict[tuple[str, str], tuple[float, list[BaseTool]]] = {}


def invalidate(user_id: str) -> None:
    """
    Drop this user's cached tools, in every mode.

    Both faces are built from the same credential, so revoking it has to clear
    both. Dropping only the read entry would leave a live write tool set built
    with a token the user just disconnected.
    """
    dropped = [key for key in _cache if key[0] == user_id]
    for key in dropped:
        _cache.pop(key, None)
    if dropped:
        logger.info(f"MCP tool cache invalidated for {user_id} ({len(dropped)} entries)")


def invalidate_all() -> None:
    """Drop everything. For tests and for a config change at runtime."""
    _cache.clear()


def _cached(user_id: str, mode: str) -> list[BaseTool] | None:
    entry = _cache.get((user_id, mode))
    if entry is None:
        return None

    expires_at, tools = entry
    if time.monotonic() >= expires_at:
        _cache.pop((user_id, mode), None)
        return None

    return tools


def _select(tools: list[BaseTool], server: MCPServer, mode: str) -> list[BaseTool]:
    """Narrow a server's tools to this mode's allowlist."""
    allowlist = server.allowlist_for(mode)
    if not allowlist:
        # Never reached with the current config, and deliberately fails closed
        # rather than binding all 44 tools if someone empties an allowlist.
        logger.error(f"{server.provider}: empty {mode} allowlist; binding nothing")
        return []

    allowed = set(allowlist)
    kept = [tool for tool in tools if tool.name in allowed]

    missing = allowed - {tool.name for tool in kept}
    if missing:
        # Not fatal: the server renamed or dropped a tool, and the rest still
        # work. Worth saying out loud, because the allowlist is now stale.
        logger.warning(
            f"{server.provider}: allowlisted tools not offered by the server: "
            f"{sorted(missing)}"
        )

    return kept


async def _connections_for(user_id: str, mode: str) -> dict[str, dict[str, Any]]:
    """
    Build the per-server connection config for everything this user connected.

    This is where the user's token is decrypted, and the resulting dict is the
    thing that must never be shared between users. `mode` picks which endpoint
    to point at — /readonly for reads, the full one for writes.
    """
    connections: dict[str, dict[str, Any]] = {}

    for doc in await connector_repo.list_for_user(user_id):
        provider = doc.get("provider")
        server = SERVERS.get(provider)
        if server is None:
            continue

        if doc.get("status") != STATUS_CONNECTED:
            # Previously errored — do not keep retrying a token we already know
            # is dead on every single turn.
            continue

        ciphertext = await connector_repo.get_token_ciphertext(user_id, provider)
        if not ciphertext:
            continue

        try:
            token = crypto.decrypt(ciphertext)
        except crypto.CryptoError as e:
            # Key rotated, or the row was tampered with. Mark it so the UI can
            # ask the user to reconnect instead of silently returning no tools.
            logger.error(f"Could not decrypt {provider} token for {user_id}: {e}")
            await connector_repo.mark_error(
                user_id, provider, "Stored credential could not be read — reconnect"
            )
            continue

        connections[provider] = {
            "transport": server.transport,
            "url": server.url_for(mode),
            "headers": server.headers(token),
        }

    return connections


async def tools_for(user_id: str, mode: str = READ) -> list[BaseTool]:
    """
    This user's MCP tools for `mode`. `[]` when nothing is connected.

    `mode` is READ or WRITE. READ hits GitHub's /readonly endpoint, where no
    write tool is offered at all; WRITE hits the full endpoint and is reached
    only from the MCP_WRITE node, which the router picks only when the user
    explicitly asked to create something.

    Returning an empty list rather than raising is deliberate: "you have not
    connected anything" is a normal state that the calling node turns into a
    sentence, not an error.
    """
    cached = _cached(user_id, mode)
    if cached is not None:
        return cached

    connections = await _connections_for(user_id, mode)
    if not connections:
        # Cached too, so a user with nothing connected does not hit Mongo on
        # every turn just to be told the same thing.
        _cache[(user_id, mode)] = (time.monotonic() + settings.mcp_tool_cache_ttl, [])
        return []

    client = MultiServerMCPClient(connections)

    tools: list[BaseTool] = []
    for provider in connections:
        server = SERVERS[provider]
        try:
            fetched = await client.get_tools(server_name=provider)
        except Exception as e:
            # One provider being down must not take out the others, and must
            # not take out the chat turn either.
            logger.error(f"Could not list {provider} MCP tools for {user_id}: {e}")
            await connector_repo.mark_error(user_id, provider, str(e))
            continue

        selected = _select(fetched, server, mode)
        logger.info(
            f"{provider} [{mode}]: {len(selected)} of {len(fetched)} tools bound "
            f"for {user_id}"
        )
        tools.extend(selected)

        await connector_repo.mark_used(user_id, provider)

    _cache[(user_id, mode)] = (time.monotonic() + settings.mcp_tool_cache_ttl, tools)
    return tools
