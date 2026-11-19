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


test("subject progress crosswalk targets only existing canonical syllabus topics", () => {
  const subjectData = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\nconst ROADMAP/)[1]);
  const mappingStart = script.indexOf("const STUDY_PLAN_TOPIC_ALIASES=");
  const mappingEnd = script.indexOf(";\nfunction findMatchingSyllabusTopics", mappingStart);
  assert.ok(mappingStart >= 0 && mappingEnd > mappingStart);
  const sandbox = { SUBJECTS: subjectData, allSubjects: () => subjectData };
  require("node:vm").runInNewContext(script.slice(mappingStart, mappingEnd + 1) + "\nthis.crosswalk=STUDY_PLAN_TOPIC_ALIASES;", sandbox);
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

test("subject uncompletion invalidates linked Day 1 records without deleting Day 2 attempt history", () => {
  assert.match(script, /function syncSyllabusUncompletionToStudyPlan\(subject,topic\)/);
  assert.match(script, /syncSyllabusUncompletionToStudyPlan\(s\.name,name\)/);
  assert.match(script, /studyPlanDone\[dateKey\]=false/);
  assert.match(script, /return entry\.phase==="study"\?!!progress\.studyDone:!!progress\.studyDone&&!!progress\.mcqDone&&!!progress\.revisionDone/);
});

test("Day 2 mapped revision advances the shared next-review schedule", () => {
  const revisionSync = script.slice(script.indexOf("async function syncStudyPlanRevisionToSyllabus"), script.indexOf("function revisionDateAfter"));
  assert.match(revisionSync, /fetch\("\/api\/revision\/next"/);
  assert.match(revisionSync, /state\.revisionSchedule\[key\]=await response\.json\(\)/);
  assert.match(script, /await syncStudyPlanRevisionToSyllabus\(entry\)/);
});

test("empty custom subjects render zero progress instead of NaN", () => {
  assert.match(script, /s\.topics\.length\?Math\.round\(done\/s\.topics\.length\*100\):0/);
});


test("legacy Day 2 records cannot override an explicit Day 1 uncompletion", () => {
  const progress = script.slice(script.indexOf("function getStudyPlanProgress(entry)"), script.indexOf("function getStudyPlanEntry("));
  assert.match(progress, /studyDone:!!progress\.studyReset\?false:!!\(progress\.studyDone\|\|legacy\.studyDone\)/);
  assert.match(script, /studyReset:!!item\.studyReset/);
  assert.match(script, /state\.studyPlanProgress\[revisionDateKey\]=\{\.\.\.getStudyPlanProgress\(\{\.\.\.revisionEntry,dateKey:revisionDateKey\}\),studyDone:false,studyReset:true\}/);
  assert.match(script, /state\.studyPlanDone\[revisionDateKey\]=false/);
});

test("remaining subject-labelled lessons are either mapped or explicitly classified as activities", () => {
  assert.match(script, /"systems government full polity":\["Polity::Systems of Government"\]/);
  assert.match(script, /"indices hdi cpi wpi other indicators":\["Economy::Economic Indicators and Indices","Economy::CPI and WPI"\]/);
  assert.match(script, /"scientific developments in current affairs":\["Science & Technology::Emerging Tech"\]/);
});


test("subject progress mapping executes exact multi-topic aliases", () => {
  const subjectData = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\nconst ROADMAP/)[1]);
  const start = script.indexOf("function normalizePlanTopic(value){");
  const end = script.indexOf("function syncSyllabusCompletionToStudyPlan(subject,topic)", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = { allSubjects: () => subjectData };
  require("node:vm").runInNewContext(script.slice(start, end) + "\nthis.resolve=findMatchingSyllabusTopics;", sandbox);
  assert.deepEqual(Array.from(sandbox.resolve("Art & Culture", "Indian temple architecture: Nagara, Dravida, Vesara")), [
    "Art & Culture::Nagara Temples",
    "Art & Culture::Dravida Temples",
    "Art & Culture::Vesara Temples"
  ]);
  assert.deepEqual(Array.from(sandbox.resolve("Modern History", "Rise of British power and expansion")), [
    "History::Rise of British Power and Expansion"
  ]);
  assert.deepEqual(Array.from(sandbox.resolve("Mock Tests", "Full GS mock test 2 + analysis")), []);
});
