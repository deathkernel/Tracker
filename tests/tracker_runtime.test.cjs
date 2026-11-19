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
