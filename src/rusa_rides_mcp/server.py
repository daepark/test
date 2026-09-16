"""MCP server exposing your rusa.org ride history as tools.

Credentials are read from the RUSA_USERNAME / RUSA_PASSWORD environment
variables of the process running this server -- never accepted as tool
arguments -- so they never flow through conversation context.
"""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from .client import RusaAuthError, RusaClient, RusaParseError

mcp = MCPServer("rusa-rides")

_client: RusaClient | None = None


def _get_client() -> RusaClient:
    global _client
    if _client is not None:
        return _client
    username = os.environ.get("RUSA_USERNAME")
    password = os.environ.get("RUSA_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "RUSA_USERNAME and RUSA_PASSWORD must be set in the environment running this "
            "MCP server (see .env.example). Credentials are never accepted as tool "
            "arguments so they don't end up in conversation context."
        )
    base_url = os.environ.get("RUSA_BASE_URL", "https://rusa.org")
    _client = RusaClient(username=username, password=password, base_url=base_url)
    return _client


@mcp.tool()
def rusa_login() -> str:
    """Log in to rusa.org with the credentials configured via the RUSA_USERNAME and
    RUSA_PASSWORD environment variables. Optional -- rusa_get_my_rides logs in
    automatically if needed -- but useful to verify credentials work on their own."""
    client = _get_client()
    try:
        client.login()
    except RusaAuthError as exc:
        return f"Login failed: {exc}"
    return "Logged in to rusa.org."


@mcp.tool()
def rusa_discover_member_links() -> list[dict[str, object]]:
    """Log in (if needed) and list links found on the rusa.org homepage that look like
    they lead to your ride/results history (link text or URL containing words like
    'results', 'my rides', 'permanents', 'brevet'), ranked by relevance. Use this to
    find the right URL to pass as rides_url to rusa_get_my_rides if auto-discovery
    picks the wrong page, or if rusa_get_my_rides reports it can't find one."""
    client = _get_client()
    if not client.logged_in:
        client.login()
    return client.discover_member_links()


@mcp.tool()
def rusa_get_my_rides(rides_url: str | None = None) -> list[dict[str, str]]:
    """Fetch your ride results/history from rusa.org, logging in automatically if
    needed. Returns a list of rides as dicts keyed by the result table's own column
    headers (e.g. Date, Event, Distance, Time -- exact keys depend on how rusa.org
    lays out the page). If auto-discovery of the results page picks the wrong link,
    call rusa_discover_member_links first and pass the correct URL as rides_url."""
    client = _get_client()
    try:
        return client.get_my_rides(rides_url=rides_url)
    except (RusaAuthError, RusaParseError) as exc:
        return [{"error": str(exc)}]


@mcp.tool()
def rusa_debug_fetch(path_or_url: str) -> str:
    """Fetch an arbitrary rusa.org page (relative path like '/pages/my-account' or a
    full URL) using the authenticated session and return its raw HTML. For diagnosing
    why auto-discovery or table parsing picked the wrong page -- not for normal use."""
    client = _get_client()
    if not client.logged_in:
        client.login()
    resp = client.fetch(path_or_url)
    return resp.text


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
