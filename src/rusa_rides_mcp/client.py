"""HTTP client for authenticating with rusa.org and scraping ride results.

rusa.org is an old-style CGI site (cgi-bin/*.pl scripts) with no public API,
so this client logs in like a browser would (session cookies) and scrapes
HTML. Field names for the login form and the URL of the "my rides" page are
auto-detected rather than hardcoded, since they could not be verified live
against the site from the environment this was built in.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://rusa.org"
USER_AGENT = "rusa-rides-mcp/0.1 (personal ride export tool; run with the owner's own credentials)"
CACHE_PATH = Path.home() / ".cache" / "rusa-rides-mcp" / "discovered_urls.json"

LOGIN_LINK_HINTS = ("log in", "login", "member login", "sign in")
RIDES_LINK_HINTS = (
    "my rides",
    "my results",
    "my perm",
    "ride history",
    "results",
    "permanents",
    "brevet",
)


class RusaAuthError(RuntimeError):
    """Raised when login to rusa.org fails."""


class RusaParseError(RuntimeError):
    """Raised when a page's expected structure can't be found (site layout may differ)."""


@dataclass
class RusaClient:
    username: str
    password: str
    base_url: str = BASE_URL
    session: requests.Session = field(default_factory=requests.Session)
    logged_in: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    # -- low level -------------------------------------------------------
    def fetch(self, path_or_url: str) -> requests.Response:
        url = urljoin(self.base_url + "/", path_or_url)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp

    # -- auth --------------------------------------------------------------
    def login(self) -> None:
        """Log in to rusa.org using self.username / self.password.

        Locates a <form> containing a password input (first on the
        homepage, then by following a "log in"-looking link if needed),
        then submits every field of that form verbatim plus the
        credentials. This avoids hardcoding field names.
        """
        home = self.fetch("/")
        soup = BeautifulSoup(home.text, "html.parser")

        form, page_url = self._find_login_form(soup, home.url)
        if form is None:
            login_link = self._find_link_by_hint(soup, LOGIN_LINK_HINTS)
            if not login_link:
                raise RusaAuthError(
                    "Could not locate a login form or login link on the rusa.org homepage. "
                    "The site layout may differ from what this client expects."
                )
            page_url = urljoin(home.url, login_link)
            login_resp = self.fetch(page_url)
            soup = BeautifulSoup(login_resp.text, "html.parser")
            form, page_url = self._find_login_form(soup, login_resp.url)
            if form is None:
                raise RusaAuthError(f"No login form with a password field found at {page_url}")

        payload = self._build_login_payload(form)
        action = form.get("action") or page_url
        post_url = urljoin(page_url, action)
        method = (form.get("method") or "post").lower()

        if method == "get":
            resp = self.session.get(post_url, params=payload, timeout=30)
        else:
            resp = self.session.post(post_url, data=payload, timeout=30)
        resp.raise_for_status()

        if self._looks_logged_out(resp.text):
            raise RusaAuthError(
                "Login was submitted but rusa.org still looks logged out. Check "
                "RUSA_USERNAME/RUSA_PASSWORD, or the site may need different form "
                "fields than were auto-detected -- try rusa_debug_fetch('/') to inspect."
            )
        self.logged_in = True

    @staticmethod
    def _find_login_form(soup: BeautifulSoup, page_url: str):
        for form in soup.find_all("form"):
            if form.find("input", attrs={"type": "password"}):
                return form, page_url
        return None, page_url

    def _build_login_payload(self, form) -> dict[str, str]:
        payload: dict[str, str] = {}
        user_field = None
        pass_field = None
        for inp in form.find_all(["input", "select", "textarea"]):
            name = inp.get("name")
            if not name:
                continue
            itype = (inp.get("type") or "text").lower()
            if itype == "password":
                pass_field = name
                continue
            if itype in ("submit", "button", "image", "reset", "file"):
                continue
            payload[name] = inp.get("value", "")
            if itype in ("text", "email") and user_field is None:
                lname = name.lower()
                if any(h in lname for h in ("user", "email", "login", "member", "id", "name")):
                    user_field = name
        if user_field is None:
            for inp in form.find_all("input"):
                itype = (inp.get("type") or "text").lower()
                if itype in ("text", "email") and inp.get("name"):
                    user_field = inp["name"]
                    break
        if user_field is None or pass_field is None:
            raise RusaAuthError("Could not determine username/password field names on the login form.")
        payload[user_field] = self.username
        payload[pass_field] = self.password
        return payload

    def _looks_logged_out(self, html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        if soup.find("input", attrs={"type": "password"}):
            return True
        text = soup.get_text(" ", strip=True).lower()
        return "invalid" in text and ("password" in text or "login" in text)

    @staticmethod
    def _find_link_by_hint(soup: BeautifulSoup, hints: tuple[str, ...]) -> str | None:
        for a in soup.find_all("a", href=True):
            label = a.get_text(" ", strip=True).lower()
            href = a["href"]
            if any(h in label for h in hints) or any(h.replace(" ", "") in href.lower() for h in hints):
                return href
        return None

    # -- discovery -----------------------------------------------------
    def discover_member_links(self) -> list[dict[str, Any]]:
        """Return candidate links on the (post-login) homepage that look like
        they lead to the member's own ride/results history, ranked by how
        many hint keywords they match. Used to auto-pick the rides page and
        to let a caller override that choice.
        """
        resp = self.fetch("/")
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []
        for a in soup.find_all("a", href=True):
            label = a.get_text(" ", strip=True)
            href = a["href"]
            score = sum(1 for h in RIDES_LINK_HINTS if h in label.lower() or h.replace(" ", "") in href.lower())
            if score > 0:
                candidates.append({"text": label, "url": urljoin(resp.url, href), "score": score})
        candidates.sort(key=lambda c: -c["score"])
        return candidates

    def _cached_rides_url(self) -> str | None:
        try:
            data = json.loads(CACHE_PATH.read_text())
            return data.get(self.username)
        except Exception:
            return None

    def _cache_rides_url(self, url: str) -> None:
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, str] = {}
            if CACHE_PATH.exists():
                data = json.loads(CACHE_PATH.read_text())
            data[self.username] = url
            CACHE_PATH.write_text(json.dumps(data))
        except Exception:
            pass

    # -- rides -----------------------------------------------------------
    def get_my_rides(self, rides_url: str | None = None) -> list[dict[str, Any]]:
        if not self.logged_in:
            self.login()

        url = rides_url or self._cached_rides_url()
        if not url:
            candidates = self.discover_member_links()
            if not candidates:
                raise RusaParseError(
                    "Could not auto-discover a 'my rides' / results link after logging in. "
                    "Pass rides_url explicitly -- see rusa_discover_member_links for candidates."
                )
            url = candidates[0]["url"]

        resp = self.fetch(url)
        rides = self._parse_rides_table(resp.text)
        if rides:
            self._cache_rides_url(url)
        return rides

    @staticmethod
    def _parse_rides_table(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            raise RusaParseError(
                "No <table> found on the rides page; the page layout may not match "
                "what this client expects."
            )

        best_rows: list[list[str]] = []
        for table in tables:
            rows = [
                [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
                for tr in table.find_all("tr")
            ]
            rows = [r for r in rows if any(c for c in r)]
            if len(rows) > len(best_rows):
                best_rows = rows

        if len(best_rows) < 2:
            raise RusaParseError(
                "Found tables but none looked like a ride results table "
                "(need a header row plus at least one data row)."
            )

        header, *data_rows = best_rows
        header = [h if h else f"col{i}" for i, h in enumerate(header)]
        rides = []
        for row in data_rows:
            if len(row) != len(header):
                continue
            rides.append(dict(zip(header, row)))
        return rides
