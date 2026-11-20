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
            assert page.locator("#pageTitle").inner_text() == "Study plan"
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


def test_customization_management_and_device_theme_profiles(tracker_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            page.goto(tracker_url, wait_until="networkidle")
            page.locator('label[for="nav-settings"]').click()

            assert page.locator("body").get_attribute("data-theme-profile") == "desktop"
            page.locator("#themeToggle").check()
            assert "dark" in page.locator("body").get_attribute("class").split()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.locator("body").get_attribute("data-theme-profile") == "desktop"

            page.locator("#targetDate").fill("2027-05-24")
            page.locator("#targetDate").press("Tab")
            page.locator("#newSubject").fill("Optional Studies")
            page.locator("#newTopic").fill("Reading comprehension")
            page.locator("#addCustomTopic").click()
            assert page.locator("#customSyllabusManager").get_by_text("Reading comprehension").count() == 1

            page.once("dialog", lambda dialog: dialog.accept("Advanced comprehension"))
            page.locator('#customSyllabusManager button[data-action="rename-topic"]').click()
            assert page.locator("#customSyllabusManager").get_by_text("Advanced comprehension").count() == 1

            page.once("dialog", lambda dialog: dialog.accept("Extra Studies"))
            page.locator('#customSyllabusManager button[data-action="rename-subject"]').click()
            assert page.locator("#customSyllabusManager").get_by_text("Extra Studies").count() == 1

            page.locator("#newTaskName").fill("Review flashcards")
            page.locator("#addDailyTask").click()
            assert page.locator("#customDailyManager").get_by_text("Review flashcards").count() == 1
            page.once("dialog", lambda dialog: dialog.accept("Review flashcards daily"))
            page.locator('#customDailyManager button[data-action="rename-task"]').click()

            page.reload(wait_until="networkidle")
            page.locator('label[for="nav-settings"]').click()
            assert page.locator("#targetDate").input_value() == "2027-05-24"
            assert "dark" in page.locator("body").get_attribute("class").split()
            assert page.locator("#customSyllabusManager").get_by_text("Advanced comprehension").count() == 1
            assert page.locator("#customDailyManager").get_by_text("Review flashcards daily").count() == 1

            page.once("dialog", lambda dialog: dialog.accept())
            page.locator('#customSyllabusManager button[data-action="delete-subject"]').click()
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator('#customDailyManager button[data-action="delete-task"]').click()
            assert page.locator("#customSyllabusManager").get_by_text("No custom topics yet.").count() == 1
            assert page.locator("#customDailyManager").get_by_text("No custom tasks yet.").count() == 1

            mobile_context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
            )
            mobile_page = mobile_context.new_page()
            mobile_page.goto(tracker_url, wait_until="networkidle")
            assert mobile_page.locator("body").get_attribute("data-theme-profile") == "mobile"
            mobile_context.close()
        finally:
            browser.close()
