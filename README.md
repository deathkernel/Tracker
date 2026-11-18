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

## Strict preparation rules

The tracker includes an evidence-based mastery workflow. A topic requires study notes, at least 15 related PYQs, at least 50 characters of study notes, and a topic test of at least 20 questions with 95% accuracy before mastery completion. Verified topics receive D1, D3, D7, D15, D30 and D60 revision checkpoints. Every revision test also requires at least 20 questions with 95% accuracy. Daily targets default to 4 focused hours and 50 MCQs; CSAT is scheduled on alternate days. Missed targets remain visible for manual recovery. Sunday review combines a mock/test, revision and backlog review.

Existing topic ticks and study records are preserved when upgrading. Previously completed topics without mastery evidence are treated as legacy progress and must be verified before they enter the new mastery/revision workflow.

## Personal data and privacy

The local server binds to `127.0.0.1` by default. Study progress is stored in `tracker.db` in this folder and is not uploaded to a cloud service. Use Export backup regularly. Do not delete `tracker.db` if you want to keep the database.\n\nFor optional phone access, set the `TRACKER_HOST` environment variable to `0.0.0.0` before running `run.bat`. This exposes the app and its unauthenticated state API to your local network. Use this only on a trusted private Wi-Fi network and disable it again after use. Do not expose the app directly to the internet.

## Topic data note

The 65 topic entries and their mapped question counts are approximate editorial mappings for this personal plan, not official UPSC topic-wise statistics.

## Exam date

The default target is 23 May 2027. You can change it in the dashboard. Confirm official exam dates and notices on the UPSC website.

## Strict exam engine (expanded)

- Build a local question bank by entering verified MCQs or importing JSON. The app deliberately does not invent UPSC questions.
- JSON format: `{"questions":[{"id":"q1","subject":"Polity","topic":"Fundamental Rights","question":"...","options":["A","B","C","D"],"correctIndex":0,"explanation":"...","source":"UPSC CSE 2022"}]}`.
- Topic mastery requires 50+ characters of notes, 15+ PYQs and three consecutive timed 20-question tests at 95% accuracy or higher. A failed attempt resets the streak.
- Tests randomize question order, use a timer, award +2 for correct, apply a one-third negative penalty for wrong answers and award zero for unanswered questions.
- Full-length mock mode requires 100 questions and runs for 120 minutes. Add enough verified questions to your bank before starting.
- Scheduled revisions use the D1/D3/D7/D15/D30/D60 checkpoints and require a timed 20-question test at 95% or higher.
- Wrong and unanswered questions are added to the error notebook. Surprise retests are scheduled 3–7 days after mastery. Manual backlog recovery is available in the strict preparation panel.
- Export your question bank separately from your progress backup. Both are stored locally; keep backups safe.
