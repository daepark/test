# rusa-rides-mcp

An MCP server that logs into [rusa.org](https://rusa.org) (Randonneurs USA)
with your own member credentials and exposes your ride history to
MCP-compatible clients (Claude Code, Claude Desktop, etc.) as tools.

## How it works

rusa.org is an older CGI-based site with no public API, so this server logs
in like a browser (session cookies) and scrapes HTML:

- **Login** (`rusa_login`, or automatically on first use): fetches the
  rusa.org homepage, locates a login link/form, and submits your
  credentials. Form field names are auto-detected (by finding the `<form>`
  containing a password input) rather than hardcoded, since the exact field
  names could not be verified against the live site while this was built —
  the sandbox this was developed in has no network access to rusa.org.
- **Discovery** (`rusa_discover_member_links`): after login, scans the
  homepage for links that look like they lead to your ride/results history
  (text or URL containing "results", "my rides", "permanents", "brevet",
  etc.) and ranks them.
- **Rides** (`rusa_get_my_rides`): logs in if needed, picks the
  best-ranked discovered link (or uses `rides_url` if you pass one), fetches
  it, and parses the largest HTML `<table>` on the page into a list of
  dicts keyed by that table's own column headers. The discovered URL is
  cached in `~/.cache/rusa-rides-mcp/discovered_urls.json` so it doesn't
  need to be rediscovered every call.
- **Debug** (`rusa_debug_fetch`): fetches an arbitrary rusa.org path/URL
  with the authenticated session and returns raw HTML, for diagnosing a
  wrong guess by the two tools above.

**Because this was built without live access to rusa.org, verify it against
the real site before relying on it** — see "First run" below.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env   # then fill in RUSA_USERNAME / RUSA_PASSWORD
```

Credentials are read only from the `RUSA_USERNAME` and `RUSA_PASSWORD`
environment variables of the process running the server. They are never
accepted as MCP tool arguments, so they never appear in conversation
context or transcripts.

### First run

The login form and the "my rides" URL were auto-detected/guessed, not
verified live. After setup, sanity-check both:

1. Run `rusa_login` — confirm it reports success, not an auth error.
2. Run `rusa_discover_member_links` — check the top-ranked link is
   actually your results/ride-history page. If it picked the wrong one,
   pass the right URL explicitly via `rusa_get_my_rides(rides_url=...)`.
3. Run `rusa_get_my_rides` — check the returned rows/columns look right.
   If it errors or returns nothing sensible, use `rusa_debug_fetch` to pull
   the raw HTML of the page in question and adjust `client.py` accordingly
   (in particular `_find_login_form`/`_build_login_payload` for login, or
   `_parse_rides_table` if the results page isn't a plain HTML table).

## Registering with an MCP client

Example `claude_desktop_config.json` / Claude Code MCP config entry:

```json
{
  "mcpServers": {
    "rusa-rides": {
      "command": "/absolute/path/to/.venv/bin/rusa-rides-mcp",
      "env": {
        "RUSA_USERNAME": "your_username_or_member_id",
        "RUSA_PASSWORD": "your_password"
      }
    }
  }
}
```

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Tests cover the HTML table parser and login-form field auto-detection with
synthetic HTML fixtures (again, no live rusa.org access was available to
build fixtures from real pages).

## Security notes

- Credentials live only in your own environment/config, never in code or
  in tool-call arguments.
- This tool only ever authenticates as you, to read your own data — it
  performs a single login and a small number of GET requests per call, not
  bulk crawling.
