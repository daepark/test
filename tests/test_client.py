from rusa_rides_mcp.client import RusaClient, RusaParseError
import pytest


def make_client() -> RusaClient:
    return RusaClient(username="testuser", password="testpass")


def test_parse_rides_table_basic():
    client = make_client()
    html = """
    <html><body>
    <table>
      <tr><th>Date</th><th>Event</th><th>Distance</th><th>Time</th></tr>
      <tr><td>2024-06-01</td><td>Spring 200K</td><td>200</td><td>9:45</td></tr>
      <tr><td>2024-07-15</td><td>Summer 300K</td><td>300</td><td>15:20</td></tr>
    </table>
    </body></html>
    """
    rides = client._parse_rides_table(html)
    assert rides == [
        {"Date": "2024-06-01", "Event": "Spring 200K", "Distance": "200", "Time": "9:45"},
        {"Date": "2024-07-15", "Event": "Summer 300K", "Distance": "300", "Time": "15:20"},
    ]


def test_parse_rides_table_picks_largest_table():
    client = make_client()
    html = """
    <html><body>
    <table><tr><td>nav</td></tr></table>
    <table>
      <tr><th>Date</th><th>Event</th></tr>
      <tr><td>2024-01-01</td><td>New Year 100K</td></tr>
      <tr><td>2024-02-01</td><td>Winter 100K</td></tr>
      <tr><td>2024-03-01</td><td>Early Spring 100K</td></tr>
    </table>
    </body></html>
    """
    rides = client._parse_rides_table(html)
    assert len(rides) == 3
    assert rides[0]["Event"] == "New Year 100K"


def test_parse_rides_table_no_tables_raises():
    client = make_client()
    with pytest.raises(RusaParseError):
        client._parse_rides_table("<html><body>no tables here</body></html>")


def test_parse_rides_table_header_only_raises():
    client = make_client()
    html = "<table><tr><th>Date</th><th>Event</th></tr></table>"
    with pytest.raises(RusaParseError):
        client._parse_rides_table(html)


def test_build_login_payload_detects_fields():
    from bs4 import BeautifulSoup

    client = make_client()
    html = """
    <form action="/cgi-bin/login.pl" method="post">
      <input type="hidden" name="csrf_token" value="abc123">
      <input type="text" name="member_email">
      <input type="password" name="member_password">
      <input type="submit" value="Log In">
    </form>
    """
    form = BeautifulSoup(html, "html.parser").find("form")
    payload = client._build_login_payload(form)
    assert payload["member_email"] == "testuser"
    assert payload["member_password"] == "testpass"
    assert payload["csrf_token"] == "abc123"
