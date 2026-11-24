"""The dashboard must load the monochrome light theme and keep its indicator tokens."""
from test_server import client  # noqa: F401  (reuse the app/database fixture)


def test_dashboard_loads_theme_stylesheet(client):
    page = client.get("/")
    assert page.status_code == 200
    assert 'href="/theme.css"' in page.text
    assert page.text.count("theme.css") == 1

    css = client.get("/theme.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")


def test_theme_is_light_only_with_indicator_tokens(client):
    css = client.get("/theme.css").text
    assert "color-scheme: light" in css
    for token in ("--ok:", "--warn:", "--bad:", "--mono-500:"):
        assert token in css
