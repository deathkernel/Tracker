from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def tracker_url(tmp_path_factory):
    port = _free_port()
    database = tmp_path_factory.mktemp("tracker-browser") / "tracker-e2e.db"
    environment = os.environ.copy()
    environment["TRACKER_HOST"] = "127.0.0.1"
    environment["TRACKER_DB_PATH"] = str(database)
    environment["TRACKER_ACCESS_TOKEN"] = "browser-e2e-access-token"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 45
    ready = False
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Tracker server exited before becoming healthy.")
            try:
                with urlopen(url + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(0.25)
        if not ready:
            raise TimeoutError("Tracker server did not become healthy within 45 seconds.")
        yield url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_real_browser_navigation_and_mobile_layout(tracker_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            response = page.goto(tracker_url, wait_until="networkidle")
            assert response is not None and response.status == 200
            assert page.locator("#pageTitle").inner_text() == "Overview"
            assert page.locator("#nav-overview").is_checked()

            page.locator('label[for="nav-syllabus"]').click()
            assert page.locator("#pageTitle").inner_text() == "Syllabus"
            assert page.locator('[data-page="syllabus"]').is_visible()
            overview_sections = page.locator('[data-page="overview"]')
            assert overview_sections.count() == 2
            assert overview_sections.evaluate_all(
                "(sections) => sections.every(section => section.hidden)"
            )

            page.locator('label[for="nav-settings"]').click()
            assert page.locator("#pageTitle").inner_text() == "Settings"
            assert page.locator('[data-page="settings"]').is_visible()

            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('label[for="nav-plan"]').click()
            assert page.locator("#pageTitle").inner_text() == "Study Plan"
            assert page.locator('[data-page="plan"]').is_visible()
            assert page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth + 1"
            )
            assert page_errors == [], "Browser runtime errors: " + "; ".join(page_errors)
        finally:
            browser.close()


def test_qr_fragment_is_removed_from_address_and_sent_as_authorization_header(tracker_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            api_requests = []
            page.on(
                "request",
                lambda request: api_requests.append(
                    (request.url, request.headers) if "/api/state" in request.url else None
                ),
            )
            page.goto(
                tracker_url + "/#access_token=browser-e2e-access-token",
                wait_until="networkidle",
            )

            assert page.evaluate("() => window.location.hash") == ""
            assert page.evaluate(
                "() => sessionStorage.getItem('tracker-lan-access-token')"
            ) == "browser-e2e-access-token"
            state_requests = [item for item in api_requests if item is not None]
            assert state_requests
            request_url, request_headers = state_requests[0]
            assert "access_token" not in request_url
            assert request_headers.get("authorization") == "Bearer browser-e2e-access-token"
        finally:
            browser.close()
