const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync("index.html", "utf8");
const script = html.match(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i)?.[1] || "";

test("dashboard keeps each syllabus topic as a two-phase study unit", () => {
  assert.match(script, /const STUDY_PLAN_TOPICS=BASE_STUDY_PLAN\.flatMap/);
  assert.match(script, /const DAILY_STUDY_PLAN=STUDY_PLAN_TOPICS\.flatMap/);
  assert.match(script, /phase:"study"/);
  assert.match(script, /phase:"mcq_revision"/);
});

test("exam-deadline schedule finishes the final review by the configured target date", () => {
  const start = script.indexOf("function addDaysToDateKey(dateKey,days){");
  const end = script.indexOf("function getStudyPlanProgressDateKey(entry){", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {
    CYCLE_START_DATE: "2026-11-20",
    STUDY_PLAN_TOPICS: Array.from({ length: 189 }, () => ({})),
    state: { settings: { targetDate: "2027-05-23" } },
    localDateKey: date => [date.getFullYear(), String(date.getMonth()+1).padStart(2,"0"), String(date.getDate()).padStart(2,"0")].join("-")
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.getDate=getStudyPlanDateKey;", sandbox);
  assert.equal(sandbox.getDate({ planIndex: 0, phase: "study" }), "2026-11-20");
  assert.equal(sandbox.getDate({ planIndex: 188, phase: "study" }), "2027-05-22");
  assert.equal(sandbox.getDate({ planIndex: 188, phase: "mcq_revision" }), "2027-05-23");
});

test("legacy date-keyed study progress migrates to stable per-topic keys", () => {
  assert.match(script, /studyPlanProgressSchema:2/);
  assert.match(script, /const key="plan:"\+planIndex/);
  assert.match(script, /LEGACY_CYCLE_START_DATE,planIndex\*2/);
  assert.match(script, /const reset=!!\(current\.studyReset\|\|oldStudy\.studyReset\|\|oldRevision\.studyReset\)/);
  assert.match(script, /next\.studyPlanProgressSchema=2/);
});

test("pipelined Day 2 uses the same topic's stable progress record", () => {
  assert.match(script, /function getStudyPlanProgressDateKey\(entry\)/);
  assert.match(script, /return "plan:"\+entry\.planIndex/);
  assert.match(script, /entry\.phase==="mcq_revision"\?1:0/);
  assert.match(script, /studyEntries:getStudyPlanEntriesForDate/);
  assert.match(script, /revisionEntries:getStudyPlanEntriesForDate/);
});

test("Day 2 MCQ count is saved before revision confirmation", () => {
  const completion = script.slice(script.indexOf("async function completePlanRevision"), script.indexOf("function renderOverviewSchedule"));
  const mcqSave = completion.indexOf("progress.mcqDone=true;");
  const persistAfterMcq = completion.indexOf("state.studyPlanProgress[key]=progress;", mcqSave);
  const revisionConfirm = completion.indexOf('confirm("Have you revised "+entry.topic+"?")', mcqSave);
  assert.ok(mcqSave >= 0 && persistAfterMcq > mcqSave && revisionConfirm > persistAfterMcq);
});

test("only overdue study phases enter the recovery queue", () => {
  assert.match(script, /function refreshRecoveryQueue\(today=localDate\(\)\)/);
  assert.match(script, /dueDate<today&&!isStudyPlanEntryDone\(entry\)/);
  assert.match(script, /state\.recoveryQueue=queue/);
});

test("missing-topic action opens and highlights the exact overdue roadmap phase", () => {
  assert.match(script, /setWorkspaceView\("plan"\)/);
  assert.match(script, /"plan-"\+dateKey/);
  assert.match(script, /missing-target-row/);
});

test("subject progress synchronization covers mapped syllabus topics", () => {
  assert.match(script, /function findMatchingSyllabusTopic\(subject,topic\)/);
  assert.match(script, /function syncSyllabusCompletionToStudyPlan\(subject,topic\)/);
  assert.match(script, /function syncStudyPlanCompletionToSyllabus\(entry\)/);
  assert.match(script, /async function syncStudyPlanRevisionToSyllabus\(entry,quality=3\)/);
});

test("uncompletion invalidates linked study but preserves MCQ history", () => {
  assert.match(script, /function syncSyllabusUncompletionToStudyPlan\(subject,topic\)/);
  assert.match(script, /const progress=\{\.\.\.getStudyPlanProgress\(entry\),studyDone:false,mcqDone:false,revisionDone:false,studyReset:true\}/);
  assert.match(script, /mcqCount:Number\.isInteger\(item\.mcqCount\)/);
  assert.match(script, /mcqDone:!!\(current\.mcqDone/);
});

test("revision quality updates shared mastery and retest state", () => {
  assert.match(script, /fetch\("\/api\/study\/review"/);
  assert.match(script, /previous_mastery:state\.masteryProgress/);
  assert.match(script, /previous_retest:state\.retestSchedule/);
  assert.match(script, /async function completeScheduledRetest\(subject,topic,progressKey=null\)/);
  assert.match(script, /Record retest/);
});

test("revision scheduling remains delegated to the backend", () => {
  assert.match(script, /fetch\("\/api\/revision\/next"/);
  assert.match(script, /quality\}\)\}\);/);
});

test("analytics count phase completion and distinct missed dates", () => {
  assert.match(script, /const planTotal=DAILY_STUDY_PLAN\.length/);
  assert.match(script, /missedDates\.add\(dateKey\)/);
  assert.match(script, /label:"phases"/);
});

test("subject progress crosswalk targets only existing canonical syllabus topics", () => {
  const subjectData = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\r?\nconst ROADMAP/)[1]);
  const mappingStart = script.indexOf("const STUDY_PLAN_TOPIC_ALIASES=");
  const mappingEnd = script.indexOf(";\nfunction findMatchingSyllabusTopics", mappingStart);
  assert.ok(mappingStart >= 0 && mappingEnd > mappingStart);
  const sandbox = { SUBJECTS: subjectData, allSubjects: () => subjectData };
  vm.runInNewContext(script.slice(mappingStart, mappingEnd + 1) + "\nthis.crosswalk=STUDY_PLAN_TOPIC_ALIASES;", sandbox);
  const valid = new Set(subjectData.flatMap(subject => subject.topics.map(([topic]) => subject.name + "::" + topic)));
  const invalid = [];
  for (const [planSubject, entries] of Object.entries(sandbox.crosswalk)) {
    for (const [planTopic, targets] of Object.entries(entries)) {
      for (const target of targets) if (!valid.has(target)) invalid.push({ planSubject, planTopic, target });
    }
  }
  assert.deepEqual(invalid, []);
});

test("subject progress mapping supports explicit multi-topic aliases and safe exact fallback", () => {
  assert.match(script, /function findMatchingSyllabusTopics\(subject,topic\)/);
  assert.match(script, /const validKeys=new Set\(allSubjects\(\)\.flatMap/);
  assert.match(script, /return unique\.length===keys\.length&&unique\.length>0&&unique\.every\(key=>validKeys\.has\(key\)\)\?unique:\[\];/);
  assert.match(script, /"indian temple architecture nagara dravida vesara":\["Art & Culture::Nagara Temples","Art & Culture::Dravida Temples","Art & Culture::Vesara Temples"\]/);
});

test("removed MCQ question content and AI study interfaces stay absent", () => {
  for (const marker of ['id="nav-assistant"', 'id="ollamaMessages"', 'id="aiPlannerToggle"', 'id="teacherPrompt"']) {
    assert.equal(html.includes(marker), false, marker);
  }
  for (const marker of ["/api/ollama/", "/api/teacher/", "function generateAiSchedule", "questionBank.forEach", "renderQuestionBank"]) {
    assert.equal(script.includes(marker), false, marker);
  }
});

test("study history, local backup and SQLite synchronization remain wired", () => {
  assert.match(script, /function renderLogs\(\)/);
  assert.match(script, /function persist\(\)/);
  assert.match(script, /fetch\("\/api\/state"/);
  assert.match(script, /"-recovery"/);
  assert.match(script, /function replaceProgressState\(incoming\)/);
});



test("plan-only study activities remain visible for retest", () => {
  assert.match(script, /if\(findMatchingSyllabusTopics\(entry\.subject,entry\.topic\)\.length\)return/);
  assert.match(script, /const key="plan:"\+planIndex/);
  assert.match(script, /planOnly:true/);
  assert.match(script, /completeScheduledRetest\(item\.subject,item\.topic,item\.key\)/);
});

test("weekly plan analytics use the new scheduled phase dates", () => {
  assert.match(script, /const scheduled=getStudyPlanDateKey\(entry\)/);
  assert.match(script, /Completed planned phases · first 8 weeks/);
  assert.doesNotMatch(script, /new Date\(2026,10,17\)/);
});



test("legacy migration resets Day 2 flags but retains MCQ count", () => {
  assert.match(script, /mcqDone:!reset&&!!\(current\.mcqDone/);
  assert.match(script, /revisionDone:!reset&&!!\(current\.revisionDone/);
  assert.match(script, /mcqCount:Number\.isInteger\(current\.mcqCount\)/);
});
