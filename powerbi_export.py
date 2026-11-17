from __future__ import annotations
import csv, json, re, sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH, HTML_PATH, OUT = ROOT / "tracker.db", ROOT / "index.html", ROOT / "powerbi_data"

def extract_array(source: str, declaration: str):
    pos = source.find(declaration)
    if pos < 0: raise RuntimeError(f"Missing {declaration} in index.html")
    start = source.find("[", pos + len(declaration))
    depth = 0
    in_string = escaped = False
    quote = ""
    for i in range(start, len(source)):
        ch = source[i]
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == quote: in_string = False
        elif ch in ("'", '"', "\`"):
            in_string, quote = True, ch
        elif ch == "[": depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0: return json.loads(source[start:i+1])
    raise RuntimeError(f"Could not parse {declaration}")

def write_csv(name, rows):
    path = OUT / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        if rows:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        else: file.write("")
    print(f"{path.name}: {len(rows)} rows")

def main():
    if not DB_PATH.exists(): raise FileNotFoundError("tracker.db not found")
    with sqlite3.connect(DB_PATH) as db:
        record = db.execute("SELECT payload FROM app_state WHERE id=1").fetchone()
    if not record: raise RuntimeError("No saved Tracker state")
    state = json.loads(record[0])
    html = HTML_PATH.read_text(encoding="utf-8")
    subjects = extract_array(html, "const SUBJECTS=")
    daily = extract_array(html, "const DAILY=")
    plan = []
    plan_start = html.find("const DAILY_STUDY_PLAN=")
    plan_end = html.find("];", plan_start) + 1
    plan_source = html[plan_start:plan_end]
    for match in re.finditer(r'\{subject:"([^"]+)",days:\[(.*?)\]\}', plan_source, re.S):
        topics = json.loads("[" + match.group(2) + "]")
        plan.append({"subject": match.group(1), "days": topics})
    topic_rows, progress_rows = [], []
    for subject in subjects + state.get("customSubjects", []):
        for name, pyq, priority in subject["topics"]:
            key = f'{subject["name"]}::{name}'
            topic_rows.append({"TopicKey":key,"Subject":subject["name"],"Topic":name,"Priority":priority,"PYQCount":pyq if pyq is not None else ""})
            progress_rows.append({"TopicKey":key,"Subject":subject["name"],"Topic":name,"Priority":priority,"IsCompleted":bool(state.get("topics",{}).get(key,False)),"IsRevised":bool(state.get("revisionDone",{}).get(key,False))})
    logs = [{"Date":day,"StudyHours":float(v.get("hours") or 0),"MCQs":int(v.get("mcqs") or 0),"CSAT":int(v.get("csat") or 0),"Notes":v.get("notes","")} for day,v in sorted(state.get("logs",{}).items())]
    checklist = []
    for day, checks in sorted(state.get("daily",{}).items()):
        for item in daily + state.get("customDaily",[]):
            checklist.append({"Date":day,"TaskID":item[0],"Task":item[1],"IsCompleted":bool(checks.get(item[0],False))})
    plan_rows, first = [], date(2026,11,17)
    for wi, week in enumerate(plan):
        for di, topic in enumerate(week["days"]):
            d = first + timedelta(days=wi*7+di)
            plan_rows.append({"Date":d.isoformat(),"Week":wi+1,"Subject":week.get("subject",""),"PlannedTopic":topic,"IsCompleted":bool(state.get("studyPlanDone",{}).get(d.isoformat(),False))})
    dates = sorted({r["Date"] for r in logs+checklist+plan_rows})
    calendar = []
    for value in dates:
        d = date.fromisoformat(value)
        calendar.append({"Date":value,"Year":d.year,"MonthNumber":d.month,"Month":d.strftime("%B"),"Weekday":d.strftime("%A"),"WeekdayNumber":d.isoweekday()})
    OUT.mkdir(exist_ok=True)
    for name, rows in [("Topics",topic_rows),("TopicProgress",progress_rows),("StudyLogs",logs),("DailyChecklist",checklist),("StudyPlan",plan_rows),("Calendar",calendar)]:
        write_csv(name, rows)
    print(f"Power BI data exported to {OUT}")

if __name__ == "__main__": main()
