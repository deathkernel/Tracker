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
- Two-day topic cycle: Day 1 study, Day 2 MCQ attempt count + revision for the same topic.
- 9 base subjects and 256 curated syllabus topics.
- Subject-wise progress, topic search and completion filters.
- Weekly roadmap with date, subject and study focus.
- Study log for focused hours, MCQs, CSAT and notes.
- Weekly targets and JSON backup/restore.
- Customize the exam target date and daily study-hour goal.
- Switch between light and dark themes.
- Add your own subjects, topics and daily checklist tasks.
- Local SQLite persistence with browser storage fallback.
- No login, signup, cloud account or paid hosting.

## Preparation tracking

The tracker records daily MCQ counts, study hours, CSAT minutes and notes. It tracks the number of questions attempted; it does not store, display, import or run MCQ question content.

## Dashboard charts and local AI

The Charts section provides built-in dashboard visuals for syllabus completion, subject progress, revision status, study hours, MCQ counts and study consistency. Power BI export is optional and is not required for normal Tracker use.

The floating AI Study Planner connects to Ollama at `http://127.0.0.1:11434` and automatically lists models already installed on this PC. Open the floating planner, choose a local model, and generate a 7- or 14-day timetable from the current pending syllabus, study-hour goal and recent study logs. Review the proposed time blocks, then explicitly apply the schedule to save it in Tracker. The current day’s AI timetable is also shown on the overview. Existing study-plan completion records are preserved. The separate AI Assistant chat remains available as an optional secondary feature.

Tracker sends the selected prompt or planning context only to the local Ollama service. It does not call a hosted AI API. AI-generated schedules are validated against pending syllabus topics and checked for duplicate dates and overlapping time blocks. If Ollama is not running, the rest of Tracker continues to work normally.

## Personal data and privacy

The local server binds to `127.0.0.1` by default. Study progress is stored in `tracker.db` in this folder and is not uploaded to a cloud service. Use Export backup regularly. Do not delete `tracker.db` if you want to keep the database.

For optional phone access, set the `TRACKER_HOST` environment variable to `0.0.0.0` before running `run.bat`. This exposes the app and its unauthenticated state API to your local network. Use this only on a trusted private Wi-Fi network and disable it again after use. Do not expose the app directly to the internet.

## Topic data note

The topic list and mapped PYQ counts are curated editorial references for this personal plan, not official UPSC topic-wise statistics.

## Exam date

The default target is 23 May 2027. You can change it in the dashboard. Confirm official exam dates and notices on the UPSC website.

