# UPSC Prelims 2027 — Personal Study Tracker

A login-free Windows study dashboard with a Python FastAPI backend and local SQLite storage.

## Run on Windows

1. Install Python 3.10 or newer.
2. Download and extract this repository.
3. Double-click `run.bat`.
4. Open http://127.0.0.1:8000 if the browser does not open automatically.

Keep the command window open while using the tracker. Press Ctrl+C to stop the local server.

## Dashboard

- Daily checklist and completion progress.
- 9 base subjects and 65 approximate PYQ topic mappings.
- Subject-wise progress, topic search and completion filters.
- Weekly roadmap with date, subject and study focus.
- Study log for focused hours, MCQs, CSAT and notes.
- Weekly targets and JSON backup/restore.
- Customize the exam target date and daily study-hour goal.
- Switch between light and dark themes.
- Add your own subjects, topics and daily checklist tasks.
- Local SQLite persistence with browser storage fallback.
- No login, signup, cloud account or paid hosting.

## Personal data and privacy

The local server listens only on 127.0.0.1. Study progress is stored in `tracker.db` in this folder and is not uploaded to a cloud service. Use Export backup regularly. Do not delete `tracker.db` if you want to keep the database.

## Topic data note

The 65 topic entries and their mapped question counts are approximate editorial mappings for this personal plan, not official UPSC topic-wise statistics.

## Exam date

The default target is 23 May 2027. You can change it in the dashboard. Confirm official exam dates and notices on the UPSC website.
