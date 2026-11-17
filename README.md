# UPSC Prelims 2027 — Local Study Tracker

A personal, login-free UPSC preparation dashboard powered by a Python FastAPI backend and SQLite database.

## Windows setup

1. Install Python 3.10 or newer and enable **Add Python to PATH** during installation.
2. Download or clone this repository.
3. Double-click `run.bat`.
4. On first run, the launcher creates a virtual environment and installs the required packages.
5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) if the browser does not open automatically.

Keep the command window open while using the tracker. Press `Ctrl+C` in that window to stop the server.

## Features

- Dashboard summary: days to target, topics completed, study hours and study days.
- Daily checklist with automatic progress calculation.
- Subject-wise progress across 9 subjects and 65 mapped topic entries.
- Topic search, subject filter and pending/completed filter.
- 27-week preparation roadmap.
- Daily study log for hours, MCQs, CSAT practice and notes.
- Weekly targets and recent study history.
- JSON export/import backup and reset controls.
- Responsive layout for desktop, tablet and mobile.
- SQLite persistence through a local Python API; browser storage remains as a fallback.
- No login, signup, cloud account, API key or paid hosting.

## Data and privacy

The app binds only to `127.0.0.1` (your own computer). Progress is stored in `tracker.db` in this folder. It is not uploaded to a server. Back up the database file or use **Export backup** regularly. The JSON backup can be imported using the dashboard's import control.

Do not delete `tracker.db` unless you intend to remove the saved database progress. If the app is used in a different browser on the same computer, it will load the same SQLite data while the local server is running.

## Topic data note

Topic counts are approximate editorial PYQ mappings supplied for this personal study plan. They are not official UPSC topic-wise statistics and should not be treated as a prediction of future paper distribution.

## Exam target

The dashboard is configured for 23 May 2027. Confirm the date and all exam notices against the official UPSC website.
