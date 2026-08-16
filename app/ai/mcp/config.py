"""
Which MCP servers exist and how to talk to them.

One frozen dataclass per provider, so adding Gmail later is an entry in SERVERS
plus an OAuth flow — no change to the client, the registry, or the node.
"""

from dataclasses import dataclass, field

from app.core.config import settings


@dataclass(frozen=True)
class MCPServer:
    """A remote MCP server, and the subset of it we are willing to bind."""

    provider: str
    label: str
    url: str
    transport: str = "streamable_http"

    # What we ask for at OAuth time. Recorded here next to the server that needs
    # them so the two cannot drift apart.
    scopes: tuple[str, ...] = ()

    # Which of the server's tools get bound to the model. Empty tuple means all.
    #
    # This is not a nice-to-have. GitHub's MCP server exposes on the order of
    # 30-90 tools, and every bound tool puts its full JSON schema into the
    # prompt on every turn that uses this route. That costs tokens on an 8B
    # model whose whole appeal is being fast and cheap, and — more importantly —
    # measurably degrades tool *selection*: given ninety near-synonymous
    # options, a small model picks badly. Start narrow, widen on evidence.
    allowlist: tuple[str, ...] = field(default_factory=tuple)

    def headers(self, token: str) -> dict[str, str]:
        """The auth headers for one user's session with this server."""
        return {"Authorization": f"Bearer {token}"}


GITHUB = MCPServer(
    provider="github",
    label="GitHub",
    url=settings.github_mcp_url,
    scopes=tuple(settings.github_oauth_scopes.split()),
    # Read-only to start. Anything that writes to a user's repositories should
    # be a deliberate, separate decision — and if it stays read-only, the OAuth
    # scope can be narrowed from `repo` to `public_repo` for a much smaller
    # blast radius on a leaked token.
    allowlist=(
        "search_repositories",
        "get_file_contents",
        "list_issues",
        "get_issue",
        "list_pull_requests",
        "get_pull_request",
        "search_code",
        "list_commits",
    ),
)

SERVERS: dict[str, MCPServer] = {GITHUB.provider: GITHUB}


def get_server(provider: str) -> MCPServer | None:
    return SERVERS.get(provider)
