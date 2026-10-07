"""gutsy MCP server: one tool, gut_check, for coding agents to call before risky actions."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import core

mcp = FastMCP("gutsy")


@mcp.tool()
def gut_check(action: str, context: str = "", user_request: str = "") -> dict:
    """Get a local, calibrated second opinion BEFORE a risky or irreversible action.

    Call this before: deleting files or directories (rm -rf), force-pushing or rewriting
    git history, dropping or migrating databases, deploying, sending emails or messages,
    publishing packages, spending money, or changing permissions or credentials.

    Args:
        action: the exact command or action you are about to take.
        context: what you are working on and why; relevant paths, branches, environments.
        user_request: the user's latest instruction, verbatim if possible.

    Returns a recommendation ("proceed", "confirm" = ask the user first, or "block") with
    the probabilities behind it. If the recommendation is not "proceed", stop and ask the
    user. This is advisory, not a security guarantee.
    """
    try:
        return core.gut_check(action, context, user_request)
    except core.GutsyUnavailable as e:
        return {"recommendation": "confirm", "reason": str(e), "error": True, "note": core.NOTE}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
