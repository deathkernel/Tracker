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
  assert.match(script, /state\.studyPlanProgress\[entry\.progressDateKey\]=progress/);
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


test("topic completion is synchronized with exact matching study-plan entries", () => {
  assert.match(script, /function findMatchingSyllabusTopic\(subject,topic\)/);
  assert.match(script, /function syncSyllabusCompletionToStudyPlan\(subject,topic\)/);
  assert.match(script, /syncSyllabusCompletionToStudyPlan\(subject,topic\)/);
  assert.match(script, /function syncStudyPlanCompletionToSyllabus\(entry\)/);
  assert.match(script, /syncStudyPlanCompletionToSyllabus\(entry\)/);
  assert.match(script, /function syncStudyPlanRevisionToSyllabus\(entry\)/);
});

test("removed AI interfaces and endpoints stay absent", () => {
  for (const marker of ['id="nav-assistant"', 'id="ollamaMessages"', 'id="aiPlannerToggle"', 'id="teacherPrompt"', "AI suggestions never mark topics complete"]) {
    assert.equal(html.includes(marker), false, marker);
  }
  for (const marker of ["/api/ollama/", "/api/teacher/", "function generateAiSchedule"]) {
    assert.equal(script.includes(marker), false, marker);
  }
});

test("MCQ prompt cancellation does not become a zero-attempt submission", () => {
  assert.ok(script.includes("const rawAmount=prompt("));
  assert.ok(script.includes("if(rawAmount===null)return"));
  assert.ok(script.includes('rawAmount.trim()===""'));
});

test("all study completion paths initialize a next-day revision schedule", () => {
  const syllabusSync = script.slice(script.indexOf("function syncStudyPlanCompletionToSyllabus"), script.indexOf("function syncStudyPlanRevisionToSyllabus"));
  const topicCompletion = script.slice(script.indexOf("function completeTopicWithMastery"), script.indexOf("async function completeScheduledRevision"));
  assert.ok(syllabusSync.includes("revisionSchedule[key]={due_date:revisionDateAfter(1)"));
  assert.ok(topicCompletion.includes("revisionSchedule[key]={due_date:revisionDateAfter(1)"));
});

test("workspace navigation and core tracking handlers remain wired", () => {
  assert.ok(script.includes('input.addEventListener("change"'));
  assert.ok(script.includes("function initFilters()"));
  assert.ok(script.includes("function renderAll()"));
  assert.ok(script.includes('$("saveLog").addEventListener("click"'));
});

test("revision completion delegates scheduling to the shared backend policy", () => {
  const completion = script.slice(script.indexOf("async function completeScheduledRevision"), script.indexOf("function renderTopics"));
  assert.ok(completion.includes('fetch("/api/revision/next"'));
});

test("revision analytics count due dates rather than permanent historical checkmarks", () => {
  assert.match(script, /revisionToday=localDate\(\)/);
  assert.match(script, /revisionSchedule\?\.\[key\]\?\.due_date/);
  assert.match(script, /dueDate<=revisionToday/);
});
