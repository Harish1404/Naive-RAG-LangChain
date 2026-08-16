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
    # Ten of the twenty-seven the /readonly endpoint offers. Verified against
    # the live server on 2026-08-17 — do not guess these names, two earlier
    # guesses (`get_issue`, `get_pull_request`) do not exist and were silently
    # dropped by the allowlist filter.
    #
    # get_me earns its place: without it the model cannot resolve "my" in "what
    # are my open PRs" to a username, and every other tool needs an owner.
    # The search_* variants are the cross-repository counterparts of the list_*
    # ones, which are per-repository.
    allowlist=(
        "get_me",
        "search_repositories",
        "get_file_contents",
        "list_commits",
        "list_issues",
        "issue_read",
        "list_pull_requests",
        "pull_request_read",
        "search_pull_requests",
        "search_code",
    ),
)

SERVERS: dict[str, MCPServer] = {GITHUB.provider: GITHUB}


def get_server(provider: str) -> MCPServer | None:
    return SERVERS.get(provider)
