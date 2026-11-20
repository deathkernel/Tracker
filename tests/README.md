# Tracker tests

Run these commands from the repository root.

## Install test dependencies

The application dependencies are listed in `requirements.txt`. Install the additional Python test dependencies with:

```bash
python -m pip install -r requirements.txt pytest httpx playwright
python -m playwright install chromium
```

## Run the complete test suite

```bash
node --test tests/*.test.cjs
python tests/check_inline_script.py
python -m compileall -q server.py tests
python -m pytest -q
```

The JavaScript runtime suite covers study-cycle scheduling, priority ordering, progress migration, Missing Topics behavior, backup validation, and revision batch atomicity. The Python suite covers the API, revision engine, Power BI export pipeline, and LAN access controls. The Playwright browser suite launches a disposable Tracker server with a temporary SQLite database and verifies real desktop/mobile navigation plus QR-token handoff.
