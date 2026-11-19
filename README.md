# UPSC Prelims 2027 — Personal Study Tracker

A login-free Windows study dashboard with a Python FastAPI backend and local SQLite storage.

## Run on Windows

1. Install Python 3.10 or newer and Ollama for Windows.
2. Download and extract this repository.
3. Install the local model once with `ollama pull qwen3.5:9b`.
4. Double-click `run.bat`. It reuses an available Ollama server or starts one, checks that `qwen3.5:9b` is installed, loads it into memory for 30 minutes, and then starts Tracker.
5. Open http://127.0.0.1:8000 if the browser does not open automatically.

`run.bat` does not silently download the multi-gigabyte model. If the model is missing, it prints the exact pull command and stops before starting Tracker. It does not terminate Ollama when Tracker is closed.

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

## Strict AI Teacher — product concept and implementation target

Tracker is being extended from a timetable generator into a local-first **Strict AI Teacher**. The teacher is the primary AI experience; chat remains available as an optional way to ask questions, not as the main workflow.

### Teacher behaviour

- Take initiative instead of waiting for the student to open chat: ask whether assigned study and revision were completed, request a truthful status, and follow up on incomplete work.
- Ask spontaneous, syllabus-relevant recall and concept-check questions, including questions about previously studied topics and earlier mistakes.
- Evaluate the student's answers, explain errors, identify weak concepts and schedule targeted revision.
- Ask for a short explanation or evidence of understanding rather than accepting an unsupported “done” response.
- Adapt the timetable to verified progress, missed sessions, available study time and revision needs.
- Maintain continuity using study history, prior answers, weak-topic signals, commitments and teacher interaction history.
- Use a firm, disciplined and respectful tone: no insults, humiliation, threats or guilt-based pressure.
- Respect configured quiet hours, rest periods and the student's ability to pause proactive prompts.

### Phase 6 — Intelligent revision foundation

- Newly completed topics receive a first revision date for the next day.
- Revision completion advances a deterministic spaced-revision cadence; due and overdue items remain visible in the Revision workspace.
- Legacy completed topics without a saved revision date are treated as due, so earlier progress is not silently ignored.
- The teacher receives completed topics and revision dates, then prioritizes due revisions while validating every question against the actual Tracker syllabus.
- The revision policy supports a 0–5 recall-quality score in the deterministic engine; the current checkbox workflow records a normal completed review until a future UI step adds explicit recall grading.

### Server-aware operation

- When the Tracker server and local Ollama runtime are available, the teacher engine can run its scheduled checks and deliver proactive prompts.
- When the server is stopped, proactive checks pause; the next start should recover persisted teacher state and resume eligible checks without duplicating prompts.
- Browser notifications require user permission. Reliable notifications when the browser is closed require a separate Windows background/notification component; a web page alone cannot guarantee this.
- Ollama remains local at `http://127.0.0.1:11434`; no hosted AI API is required.

### Safety, control and Tracker data integrity

- The teacher may analyse progress and propose schedule changes, but must not silently mark syllabus topics complete, delete records, or overwrite study history.
- Schedule changes and material progress corrections require explicit student confirmation.
- Tracker's deterministic backend remains authoritative for completion, the Day 1 study → Day 2 MCQ attempt-count + revision cycle, and all persistence rules.
- MCQ attempt counts may be tracked; this feature does not introduce an MCQ question bank or generate/store MCQ question content.
- Proactive questions must be relevant, rate-limited, deduplicated and controlled by configurable study windows and quiet hours.

### First implementation slice

The server-side teacher worker now checks on a 60-second loop while Tracker is running. It creates one Ollama-generated teacher question at the configured interval, queues it in local SQLite, and will not create another while the previous question is unanswered. The floating Teacher panel can show queued questions, submit an answer for local Ollama evaluation, and display feedback. Monitoring can be paused, the interval and quiet hours are configurable, and browser notifications are opt-in. If the browser is closed, the server can still queue a question; it will be shown when the Tracker page is opened again. This first slice does not provide guaranteed native Windows notifications while every browser window is closed, and it does not yet provide voice interaction or a complete long-term mastery model.

## Personal data and privacy

The local server binds to `127.0.0.1` by default. Study progress is stored in `tracker.db` in this folder and is not uploaded to a cloud service. Use Export backup regularly. Do not delete `tracker.db` if you want to keep the database.

For optional phone access, set the `TRACKER_HOST` environment variable to `0.0.0.0` before running `run.bat`. This exposes the app and its unauthenticated state API to your local network. Use this only on a trusted private Wi-Fi network and disable it again after use. Do not expose the app directly to the internet.

## Topic data note

The topic list and mapped PYQ counts are curated editorial references for this personal plan, not official UPSC topic-wise statistics.

## Exam date

The default target is 23 May 2027. You can change it in the dashboard. Confirm official exam dates and notices on the UPSC website.
