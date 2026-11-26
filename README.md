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
- Exam-deadline study cycle: each topic has a Day 1 preparation checklist and a separate Day 2 MCQ + revision checklist; both must be completed before the syllabus topic is marked complete. A new Day 1 topic can overlap with another topic’s Day 2.
- The base roadmap contains 189 study-plan entries. The active Prelims cycle schedules 92 priority-first topics as Day 1 preparation + Day 2 revision phases; the remaining 97 entries are deferred beyond the configured target date.
- The target date must be at least 183 days after the cycle start (184 calendar dates inclusive) to fit all 92 active topics, with each topic's Day 1 and Day 2 scheduled on consecutive days. The 27-week roadmap is a broader reference plan, not a promise that all 189 entries are in the active daily cycle.
- 9 base subjects and 291 curated syllabus topics, with every topic explicitly mapped to at least one first-pass study unit. Related topics may share a lesson.
- Subject-wise progress, topic search and completion filters.
- Weekly roadmap with date, subject and study focus.
- Daily activity log for MCQ counts and study notes.
- JSON backup/restore.
- Customize the exam target date.
- Add your own subjects, topics and daily checklist tasks.
- Local SQLite persistence with browser storage fallback.
- No login, signup, cloud account or paid hosting.

## Design

The interface uses a calm, monochromatic light theme defined in `theme.css`. The server loads it after the page's built-in styles, so the whole look can be changed in that one file.

- **One hue.** Every neutral surface, border, button, chip and active navigation state is a tint or shade of a single slate-blue ramp (`--mono-50` to `--mono-600`). There are no dark surfaces and no dark theme.
- **Colour means status.** Green marks done or good, amber marks pending or in progress, and red marks missed or needs work. Nothing else is coloured, so a coloured element always asks for attention.
- **Persistent sidebar.** On desktop the navigation stays beside the content instead of sitting below the summary cards. On phones it becomes a bottom dock.
- **Readable text.** Body, muted and status text all meet WCAG AA contrast (4.5:1) on the surfaces they appear on.

To adjust the palette, edit the variables at the top of `theme.css`.

## Preparation tracking

The tracker records daily MCQ counts and study notes, and includes a PYQ question bank sourced from the independent UPSC Prelims Test public API. It supports subject/year/search filters, answer feedback, and scheduled 50-question Day 2 topic tests with saved attempts and same-question retests. Topic-test question snapshots and selected answers are stored with the local tracker data so an unfinished attempt can be resumed. This is not an official UPSC question or answer-key feed; verify disputed answers against official UPSC keys. The tracker does not collect study durations or daily hour targets.

## Personal data and privacy

The local server binds to `127.0.0.1` by default. Study progress is stored in `tracker.db` in this folder and is not uploaded to a cloud service. Use Export backup regularly. Do not delete `tracker.db` if you want to keep the database.

For optional phone access, set the `TRACKER_HOST` environment variable to `0.0.0.0` before running `run.bat`. Open **Open on phone** on the host PC and scan its QR code. LAN API access is protected by a random bearer token generated at startup; the QR code carries it in a URL fragment, which browsers do not send in the initial page request or Referer header. The phone stores it only for that browser tab and sends it in the Authorization header for API calls. The token changes when the server restarts, so scan a fresh QR code after restarting. Use this only on a trusted private Wi-Fi network and never expose the app directly to the internet.

## Topic data note

The topic list and mapped PYQ counts are curated editorial references for this personal plan, not official UPSC topic-wise statistics.

## Exam date

The default target is 23 May 2027. You can change it in the dashboard. Confirm official exam dates and notices on the UPSC website.


## Android / iOS app (Capacitor)

The repository includes an initial Capacitor native-app shell. See [CAPACITOR.md](CAPACITOR.md) before building. Install Node.js, run `npm install`, then `npx cap add android` and `npm run cap:sync`. Android builds require Android Studio and the Android SDK; iOS builds require macOS and Xcode.

**Current scope:** the Capacitor shell is a setup screen that can check whether an existing Tracker server is reachable. The full dashboard still runs in the Python/FastAPI service and uses its SQLite database. Native embedding of the full dashboard and secure transfer of the LAN bearer token are not implemented yet. Do not disable the API access guard or expose the local server to the public internet.
