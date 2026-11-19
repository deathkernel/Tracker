const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

const html = fs.readFileSync("index.html", "utf8");
const script = html.match(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i)?.[1] || "";

test("dashboard script iterates the flattened two-day plan safely", () => {
  assert.match(script, /DAILY_STUDY_PLAN\.forEach\(\(entry,index\)=>/);
  assert.doesNotMatch(script, /DAILY_STUDY_PLAN\.forEach\(\(week,weekIndex\)=>week\.days/);
});

test("syllabus and revision completion handlers exist", () => {
  assert.match(script, /function completeTopicWithMastery\(subject,topic\)/);
  assert.match(script, /function completeScheduledRevision\(subject,topic\)/);
});

test("two-day progress is normalized and persisted in browser state", () => {
  assert.match(script, /studyPlanProgress=Object\.fromEntries/);
  assert.match(script, /studyPlanProgress:\{\}/);
  assert.match(script, /state\.studyPlanProgress\[today\]=progress/);
});

test("missing-topic navigation opens the actual plan page", () => {
  assert.match(script, /setWorkspaceView\("plan"\)/);
  assert.doesNotMatch(script, /setWorkspaceView\("roadmap"\)/);
});

test("MCQ tracking records counts without rendering a question bank", () => {
  assert.match(script, /How many MCQs did you attempt for this topic/);
  assert.doesNotMatch(script, /questionBank\.forEach|renderQuestionBank/);
});

test("only dates strictly before today count as overdue", () => {
  assert.match(script, /const isPlanDateOverdue=\(dateKey,today=localDate\(\)\)=>dateKey<today/);
  assert.match(script, /isPlanDateOverdue\(studyDateKey,today\)/);
  assert.match(script, /isPlanDateOverdue\(revisionDateKey,today\)/);
  assert.match(script, /else if\(date<todayDate\)missed\+\+;else if\(date>todayDate\)upcoming\+\+/);
  assert.match(script, /if\(date<todayDate\)\{if\(isStudyPlanEntryDone/);
});

test("missing-topic action opens and highlights the exact overdue roadmap date", () => {
  assert.match(script, /row\.id="plan-"\+dateKey/);
  assert.match(script, /getElementById\("plan-"\+dueDate\)/);
  assert.match(script, /missing-target-row/);
});

test("Day 2 uses the previous day's Day 1 progress record", () => {
  assert.match(script, /function getStudyPlanProgressDateKey\(entry\)/);
  assert.match(script, /previousDate\.setDate\(previousDate\.getDate\(\)-1\)/);
  assert.match(script, /locked:entry\.phase==="mcq_revision"&&!progress\.studyDone/);
  assert.match(script, /state\.studyPlanProgress\[entry\.progressDateKey\]=progress/);
  assert.match(script, /const progress=getStudyPlanProgress\(entry\)/);
});

test("Day 2 MCQ attempt count is saved before revision confirmation", () => {
  const mcqSave = script.indexOf('progress.mcqDone=true;progress.mcqCount=amount;');
  const persistAfterMcq = script.indexOf('state.studyPlanProgress[entry.progressDateKey]=progress;', mcqSave);
  const revisionConfirm = script.indexOf('confirm("Have you revised this same topic?")', mcqSave);
  assert.ok(mcqSave >= 0 && persistAfterMcq > mcqSave && revisionConfirm > persistAfterMcq);
});
