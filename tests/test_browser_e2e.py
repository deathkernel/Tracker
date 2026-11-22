from __future__ import annotations

import json
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


def test_overview_subject_progress_renders_counts_and_contains_mobile_overflow(tracker_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            current = page.request.get(tracker_url + "/api/state")
            assert current.status == 200
            original_state = current.json()
            payload = {
                **original_state,
                "topics": {
                    "Polity::Preamble": True,
                    "Polity::Fundamental Rights": True,
                },
                "customSubjects": [{
                    "name": "Custom audit subject",
                    "topics": [["Responsive test topic", 1, "P2"]],
                }],
            }
            saved = page.request.put(tracker_url + "/api/state", data=payload)
            assert saved.status == 200

            page.goto(tracker_url, wait_until="networkidle")
            host = page.locator("#subjectOverview")
            table = host.locator("table")
            assert table.count() == 1
            assert table.get_attribute("aria-label") == "Subject completion by topic"
            assert host.get_attribute("role") == "region"
            assert host.get_attribute("tabindex") == "0"

            rows = host.locator("tbody tr")
            assert rows.count() == int(page.locator("#subjectCount").inner_text().split()[0])
            row_values = rows.evaluate_all(
                "(items) => items.map(row => Array.from(row.cells, cell => cell.textContent.trim()))"
            )
            polity = next(row for row in row_values if row[0] == "Polity")
            custom = next(row for row in row_values if row[0] == "Custom audit subject")
            assert polity[1].startswith("2 /")
            assert custom[1] == "0 / 1"
            assert custom[2] == "1"
            assert custom[3].endswith("0%")

            assert host.evaluate("(element) => getComputedStyle(element).overflowX === 'auto'")
            assert host.evaluate("(element) => element.scrollWidth <= element.clientWidth + 1")

            page.set_viewport_size({"width": 390, "height": 844})
            assert host.evaluate("(element) => element.scrollWidth > element.clientWidth")
            assert page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth + 1"
            )
        finally:
            if "original_state" in locals():
                latest = page.request.get(tracker_url + "/api/state")
                if latest.status == 200:
                    restore = {
                        **original_state,
                        "version": latest.json().get("version", original_state["version"]),
                    }
                    page.request.put(tracker_url + "/api/state", data=restore)
            browser.close()


def test_manual_syllabus_completion_updates_overview_subject_progress(tracker_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1365, "height": 900})
        try:
            current = page.request.get(tracker_url + "/api/state")
            assert current.status == 200
            original_state = current.json()
            payload = {
                **original_state,
                "topics": {},
                "studyPlanProgress": {},
            }
            saved = page.request.put(tracker_url + "/api/state", data=payload)
            assert saved.status == 200

            page.goto(tracker_url, wait_until="networkidle")
            page.locator('label[for="nav-syllabus"]').click()
            page.locator("#subjectFilter").select_option(label="Polity")
            page.locator("#topicSearch").fill("Constitutional development")
            topic_checkbox = page.locator(
                '#topicChecklist input[aria-label="Mark Constitutional development complete"]'
            )
            assert topic_checkbox.count() == 1
            topic_checkbox.check()

            status = page.locator("#topicChecklist tbody tr").inner_text()
            assert "Completed" in status

            page.wait_for_function("""async () => {
                const response = await fetch("/api/state");
                if (!response.ok) return false;
                const saved = await response.json();
                return saved.topics?.["Polity::Constitutional development"] === true;
            }""")
            persisted = page.request.get(tracker_url + "/api/state").json()
            plan_progress = persisted["studyPlanProgress"]["plan:0"]
            assert plan_progress["studyDone"] is True
            assert all(plan_progress["studyChecklist"].values())
            assert plan_progress["revisionDone"] is False
            assert plan_progress["mcqDone"] is False

            page.locator('label[for="nav-overview"]').click()
            polity_row = page.locator("#subjectOverview tbody tr").filter(has_text="Polity")
            assert polity_row.count() == 1
            assert polity_row.locator("td").nth(1).inner_text().startswith("1 /")
            progress_percent = int(
                polity_row.locator("td").nth(3).inner_text().replace("%", "")
            )
            assert progress_percent > 0
        finally:
            if "original_state" in locals():
                latest = page.request.get(tracker_url + "/api/state")
                if latest.status == 200:
                    restore = {
                        **original_state,
                        "version": latest.json().get("version", original_state["version"]),
                    }
                    page.request.put(tracker_url + "/api/state", data=restore)
            browser.close()



def test_early_syllabus_completion_survives_initial_sqlite_sync(tracker_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1365, "height": 900})
        held_state_reads = []
        try:
            current = page.request.get(tracker_url + "/api/state")
            assert current.status == 200
            original_state = current.json()
            payload = {
                **original_state,
                "topics": {},
                "studyPlanProgress": {},
            }
            saved = page.request.put(tracker_url + "/api/state", data=payload)
            assert saved.status == 200
            initial_state = page.request.get(tracker_url + "/api/state").json()
            page.add_init_script(
                "localStorage.setItem('upsc-dashboard-v2', "
                + json.dumps(json.dumps(initial_state))
                + ");"
            )

            def hold_first_state_read(route):
                if route.request.method == "GET" and not held_state_reads:
                    held_state_reads.append((route, route.fetch()))
                    return
                route.continue_()

            page.route("**/api/state", hold_first_state_read)
            page.goto(tracker_url, wait_until="domcontentloaded")
            assert held_state_reads, "The initial SQLite state read was not intercepted."

            page.locator('label[for="nav-syllabus"]').click()
            page.locator("#subjectFilter").select_option(label="Polity")
            page.locator("#topicSearch").fill("Constitutional development")
            topic_checkbox = page.locator(
                '#topicChecklist input[aria-label="Mark Constitutional development complete"]'
            )
            assert topic_checkbox.count() == 1
            with page.expect_response(
                lambda response: response.url.endswith("/api/state")
                and response.request.method == "PUT"
                and response.status == 200
            ):
                topic_checkbox.check()

            held_route, stale_response = held_state_reads[0]
            held_route.fulfill(response=stale_response)

            page.locator('label[for="nav-overview"]').click()
            polity_row = page.locator("#subjectOverview tbody tr").filter(has_text="Polity")
            page.wait_for_function(
                """() => {
                    const row = Array.from(document.querySelectorAll("#subjectOverview tbody tr"))
                        .find(item => item.cells[0]?.textContent.trim() === "Polity");
                    return row?.cells[1]?.textContent.trim().startsWith("1 /");
                }"""
            )
            assert polity_row.locator("td").nth(1).inner_text().startswith("1 /")
            persisted = page.request.get(tracker_url + "/api/state").json()
            assert persisted["topics"]["Polity::Constitutional development"] is True
        finally:
            if held_state_reads:
                try:
                    held_state_reads[0][0].fulfill(response=held_state_reads[0][1])
                except Exception:
                    pass
            if "original_state" in locals():
                latest = page.request.get(tracker_url + "/api/state")
                if latest.status == 200:
                    restore = {
                        **original_state,
                        "version": latest.json().get("version", original_state["version"]),
                    }
                    page.request.put(tracker_url + "/api/state", data=restore)
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
            subject_names = page.locator("#customSyllabusManager .settings-manage-copy > strong").all_text_contents()
            assert subject_names.count("Extra Studies") == 1
            assert "Optional Studies" not in subject_names

            page.locator("#newTaskName").fill("Review flashcards")
            page.locator("#addDailyTask").click()
            assert page.locator("#customDailyManager").get_by_text("Review flashcards").count() == 1
            page.once("dialog", lambda dialog: dialog.accept("Review flashcards daily"))
            page.locator('#customDailyManager button[data-action="rename-task"]').click()

            page.reload(wait_until="networkidle")
            navigation = page.locator("#workspaceNav")
            assert navigation.evaluate("(element) => element.scrollWidth > element.clientWidth")
            navigation.evaluate("(element) => { element.scrollLeft = element.scrollWidth; }")

            settings_label = page.locator('label[for="nav-settings"]')
            assert settings_label.evaluate(
                "(element) => { const rect = element.getBoundingClientRect(); return rect.left >= 0 && rect.right <= window.innerWidth; }"
            )
            settings_label.click()
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
            mobile_context.add_init_script("""
                Object.defineProperty(navigator, "userAgentData", {
                    configurable: true,
                    value: { mobile: false }
                });
            """)
            mobile_page = mobile_context.new_page()
            mobile_page.goto(tracker_url, wait_until="networkidle")
            assert mobile_page.evaluate("() => navigator.userAgentData.mobile") is False
            assert mobile_page.locator("body").get_attribute("data-theme-profile") == "mobile"
            mobile_context.close()
        finally:
            browser.close()
