const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync("index.html", "utf8");
const script = html.match(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i)?.[1] || "";

test("dashboard keeps each syllabus topic as a two-phase study unit", () => {
  assert.match(script, /const STUDY_PLAN_TOPICS=BASE_STUDY_PLAN\.flatMap/);
  assert.match(script, /const SHUFFLED_STUDY_PLAN=buildSubjectRotatedStudyPlan\(STUDY_PLAN_TOPICS\)/);
  assert.match(script, /const DAILY_STUDY_PLAN=SHUFFLED_STUDY_PLAN\.flatMap/);
  assert.match(script, /phase:"study"/);
  assert.match(script, /phase:"mcq_revision"/);
});


test("Top 50 P1 topics are mapped and scheduled before standard topics", () => {
  const subjectData = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\r?\nconst ROADMAP/)[1]);
  const mappingStart = script.indexOf("function normalizePlanTopic(");
  const mappingEnd = script.indexOf("\nconst PRELIMS_TOP_50_KEYS=", mappingStart);
  const planStart = script.indexOf("const BASE_STUDY_PLAN=");
  const planEnd = script.indexOf(";\nconst CYCLE_START_DATE", planStart);
  const rotationStart = script.indexOf("function getStudyPlanRotationSubject(entry){");
  const rotationEnd = script.indexOf("\nfunction addDaysToDateKey", rotationStart);
  const priorityStart = script.indexOf("const PRELIMS_TOP_50_KEYS=");
  const priorityEnd = script.indexOf("\nconst SHUFFLED_STUDY_PLAN=", priorityStart);
  assert.ok(mappingStart >= 0 && mappingEnd > mappingStart);
  assert.ok(planStart >= 0 && planEnd > planStart);
  assert.ok(rotationStart >= 0 && rotationEnd > rotationStart);
  assert.ok(priorityStart >= 0 && priorityEnd > priorityStart);
  const sandbox = { SUBJECTS: subjectData };
  vm.runInNewContext(
    "const allSubjects=()=>SUBJECTS;\n" +
    script.slice(planStart, planEnd + 1) + "\n" +
    script.slice(mappingStart, mappingEnd) + "\n" +
    script.slice(rotationStart, rotationEnd) + "\n" +
    script.slice(priorityStart, priorityEnd) +
    "\nthis.units=BASE_STUDY_PLAN.flatMap(group=>group.days.map(topic=>({subject:group.subject,topic})));"+
    "\nthis.top50=PRELIMS_TOP_50_KEYS;this.ordered=buildSubjectRotatedStudyPlan(units);",
    sandbox
  );
  assert.equal(sandbox.top50.size, 50);
  assert.equal(sandbox.ordered.length, 189);
  const firstStandard = sandbox.ordered.findIndex(entry => entry.priority !== "P1");
  assert.equal(firstStandard, 48);
  assert.ok(Array.from(sandbox.ordered.slice(0, firstStandard)).every(entry => entry.priority === "P1"));
  assert.ok(Array.from(sandbox.ordered.slice(firstStandard)).every(entry => entry.priority === "P2"));
  assert.equal(new Set(Array.from(sandbox.ordered, entry => entry.planIndex)).size, 189);
  const mappedPriority = new Set(Array.from(sandbox.ordered.flatMap(entry => entry.priorityKeys)));
  assert.deepEqual(Array.from(sandbox.top50).filter(key => !mappedPriority.has(key)), []);
  assert.deepEqual(Array.from(sandbox.ordered.slice(0,7), entry => entry.rotationSubject), [
    "Polity","Modern History","Ancient + Medieval History","Economy","Environment","Geography","Science & Technology"
  ]);
});

test("schedule rotates subjects within priority tiers and preserves original progress indexes", () => {
  const rotationStart = script.indexOf("function getStudyPlanRotationSubject(entry){");
  const rotationEnd = script.indexOf("\nfunction addDaysToDateKey", rotationStart);
  const priorityStart = script.indexOf("const PRELIMS_TOP_50_KEYS=");
  const priorityEnd = script.indexOf("\nconst SHUFFLED_STUDY_PLAN=", priorityStart);
  const sandbox = {
    allSubjects:()=>[
      {name:"Polity",topics:[["P1 A",1,"P1"],["P1 B",1,"P1"],["P2 A",1,"P2"],["P2 B",1,"P2"]]},
      {name:"Economy",topics:[["P1 C",1,"P1"],["P2 C",1,"P2"]]},
      {name:"History",topics:[["P1 D",1,"P1"],["P2 D",1,"P2"]]}
    ],
    findMatchingSyllabusTopics:(subject,topic)=>[subject+"::"+topic]
  };
  vm.runInNewContext(
    script.slice(rotationStart,rotationEnd)+"\n"+
    script.slice(priorityStart,priorityEnd)+"\nthis.rotate=buildSubjectRotatedStudyPlan;",
    sandbox
  );
  const source=[
    {subject:"Polity",topic:"P1 A"},
    {subject:"Polity",topic:"P2 A"},
    {subject:"Economy",topic:"P1 C"},
    {subject:"History",topic:"P1 D"},
    {subject:"Economy",topic:"P2 C"},
    {subject:"Polity",topic:"P1 B"},
    {subject:"History",topic:"P2 D"},
    {subject:"Polity",topic:"P2 B"}
  ];
  const ordered=sandbox.rotate(source);
  assert.deepEqual(Array.from(ordered,entry=>entry.planIndex),[0,2,3,5,4,6,1,7]);
  assert.equal(ordered[0].priority,"P1");
  assert.equal(ordered[4].priority,"P2");
  assert.deepEqual(Array.from(ordered,entry=>entry.scheduleIndex),[0,1,2,3,4,5,6,7]);
});

test("priority-first scheduling retains compressed 184-day coverage and two-phase dates", () => {
  const start = script.indexOf("function studyPlanDateOffset(entry){");
  const end = script.indexOf("\nfunction getStudyPlanDateKey(entry){", start);
  assert.ok(start >= 0 && end > start);
  const dateOffset = script.slice(start, end);
  assert.match(dateOffset, /Math\.round\(scheduleIndex\*finalStudyOffset\/\(STUDY_PLAN_TOPICS\.length-1\)\)/);
  const offsets = Array.from({length:189}, (_,index) => Math.round(index*183/188));
  assert.equal(new Set(offsets).size, 184);
  assert.equal(offsets[0], 0);
  assert.equal(offsets[1], 1);
  assert.equal(offsets[offsets.length-1], 183);
  const counts = new Map();
  offsets.forEach(offset => counts.set(offset,(counts.get(offset)||0)+1));
  assert.equal(Array.from(counts.values()).filter(count => count===2).length, 5);
  assert.ok(Array.from(counts.values()).every(count => count===1||count===2));
  assert.match(script, /const DAILY_STUDY_PLAN=SHUFFLED_STUDY_PLAN\.flatMap/);
  assert.match(script, /entry\.phase==="mcq_revision"\?1:0/);
  assert.match(script, /priority:isPriority\?"P1":"P2"/);
});
test("topic checklists render under Daily routine, not Today’s study cycle", () => {
  const routine = script.slice(script.indexOf("function renderDaily(){"), script.indexOf("\nfunction renderSubjectOverview(){"));
  const cycle = script.slice(script.indexOf("function renderOverviewSchedule(){"), script.indexOf("\nfunction renderRoadmap(){"));
  assert.match(routine, /renderPhaseChecklist\(entry,phase,getStudyPlanProgress\(entry\)\)/);
  assert.doesNotMatch(cycle, /renderPhaseChecklist/);
  assert.match(cycle, /Complete its Day 1 preparation tasks in Daily routine/);
  assert.match(script, /const scheduleIndex=Number\.isInteger\(entry\?\.scheduleIndex\)\?entry\.scheduleIndex:entry\.planIndex/);
});

test("PYQ completion indicator color follows completed-topic percentage", () => {
  assert.match(html, /id="topicProgressTrack" role="progressbar"/);
  assert.match(script, /topicFill\.style\.width=topicPercent\+"%"/);
  assert.match(script, /topicTrack\.setAttribute\("aria-valuenow",String\(topicPercent\)\)/);
  const start = script.indexOf("function completionColorClass(percent){");
  const end = script.indexOf("\nfunction renderStats()", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {};
  vm.runInNewContext(script.slice(start, end) + "\nthis.getColorClass=completionColorClass;", sandbox);
  assert.equal(sandbox.getColorClass(0), "is-low");
  assert.equal(sandbox.getColorClass(39), "is-low");
  assert.equal(sandbox.getColorClass(40), "is-medium");
  assert.equal(sandbox.getColorClass(79), "is-medium");
  assert.equal(sandbox.getColorClass(80), "is-high");
  assert.equal(sandbox.getColorClass(100), "is-high");
  assert.equal(sandbox.getColorClass(140), "is-high");
  assert.equal(sandbox.getColorClass(-10), "is-low");
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

test("Day 2 cannot finish until its own checklist is complete", () => {
  const completion = script.slice(script.indexOf("async function completePlanRevision"), script.indexOf("function renderPhaseChecklist"));
  assert.match(completion, /if\(!canCompleteStudyPlanPhase\(entry,"mcq_revision"\)\)/);
  const mcqSave = completion.indexOf("progress.mcqDone=true;");
  const revisionQuality = completion.indexOf('askRecallQuality(entry.topic,"revision")');
  assert.ok(mcqSave >= 0 && revisionQuality > mcqSave);
  assert.doesNotMatch(completion, /confirm\("Have you revised/);
});
test("Day 1 and Day 2 checklists are independent and both gate topic completion", () => {
  assert.match(script, /const STUDY_DAY_CHECKLIST=/);
  assert.match(script, /const REVISION_DAY_CHECKLIST=/);
  assert.match(script, /studyChecklist:normalizePhaseChecklist\(item\.studyChecklist,STUDY_DAY_CHECKLIST,!!item\.studyDone\)/);
  assert.match(script, /revisionChecklist:normalizePhaseChecklist\(item\.revisionChecklist,REVISION_DAY_CHECKLIST,!!item\.revisionDone\)/);
  assert.match(script, /function canCompleteStudyPlanPhase\(entry,phase\)/);
  assert.match(script, /if\(!canCompleteStudyPlanPhase\(entry,"study"\)\)/);
  assert.match(script, /if\(!canCompleteStudyPlanPhase\(entry,"mcq_revision"\)\)/);
  assert.match(script, /progress\.studyDone&&!!progress\.revisionDone&&isPhaseChecklistComplete\(progress,"study"\)&&isPhaseChecklistComplete\(progress,"mcq_revision"\)/);
  assert.match(script, /function hasCompletedStudyCycleForSyllabusTopic\(subject,topic\)/);
  assert.match(script, /if\(!hasCompletedStudyCycleForSyllabusTopic\(subject,topic\)\)/);
  assert.doesNotMatch(html, /id="weeklyTasks"/);
  assert.doesNotMatch(html, /<h2>Weekly targets<\/h2>/);
});
test("legacy completed phases retain completed checklist ticks after upgrade", () => {
  assert.match(script, /normalizePhaseChecklist\(item\.studyChecklist,STUDY_DAY_CHECKLIST,!!item\.studyDone\)/);
  assert.match(script, /normalizePhaseChecklist\(item\.revisionChecklist,REVISION_DAY_CHECKLIST,!!item\.revisionDone\)/);
});

test("checklist completion helper requires every item in the selected phase", () => {
  const definitionsStart = script.indexOf("const STUDY_DAY_CHECKLIST=");
  const definitionsEnd = script.indexOf("const STORE=", definitionsStart);
  const helperStart = script.indexOf("function isPhaseChecklistComplete(progress,phase)");
  const helperEnd = script.indexOf("function getPhaseChecklistCount", helperStart);
  assert.ok(definitionsStart >= 0 && definitionsEnd > definitionsStart && helperEnd > helperStart);
  const sandbox = {};
  vm.runInNewContext(
    script.slice(definitionsStart, definitionsEnd) +
      "\n" + script.slice(helperStart, helperEnd) +
      "\nthis.studyItems=STUDY_DAY_CHECKLIST;this.revisionItems=REVISION_DAY_CHECKLIST;this.isComplete=isPhaseChecklistComplete;this.normalize=normalizePhaseChecklist;",
    sandbox
  );
  const allStudy = sandbox.normalize(null, sandbox.studyItems, true);
  const noStudy = sandbox.normalize(null, sandbox.studyItems, false);
  assert.equal(sandbox.isComplete({studyChecklist:allStudy},"study"), true);
  assert.equal(sandbox.isComplete({studyChecklist:noStudy},"study"), false);
  const partialRevision = sandbox.normalize({mcqs:true},sandbox.revisionItems,false);
  assert.equal(sandbox.isComplete({revisionChecklist:partialRevision},"mcq_revision"), false);
  const allRevision = sandbox.normalize(null,sandbox.revisionItems,true);
  assert.equal(sandbox.isComplete({revisionChecklist:allRevision},"mcq_revision"), true);
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
  assert.match(script, /const progress=\{\.\.\.getStudyPlanProgress\(entry\),studyDone:false,mcqDone:false,revisionDone:false,studyChecklist:normalizePhaseChecklist\(null,STUDY_DAY_CHECKLIST,false\),revisionChecklist:normalizePhaseChecklist\(null,REVISION_DAY_CHECKLIST,false\),studyReset:true\}/);
  assert.match(script, /mcqCount:Number\.isInteger\(item\.mcqCount\)/);
  assert.match(script, /mcqDone:!reset&&!!\(current\.mcqDone/);
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

test("Polity study-plan completion only marks topics covered by that lesson", () => {
  const subjectData = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\r?\nconst ROADMAP/)[1]);
  const resolverStart = script.indexOf("function normalizePlanTopic(");
  const resolverEnd = script.indexOf("\nfunction syncSyllabusCompletionToStudyPlan", resolverStart);
  assert.ok(resolverStart >= 0 && resolverEnd > resolverStart);
  const sandbox = { SUBJECTS: subjectData, allSubjects: () => subjectData };
  vm.runInNewContext(
    script.slice(resolverStart, resolverEnd) + "\nthis.resolve=findMatchingSyllabusTopics;",
    sandbox
  );

  assert.deepEqual(
    Array.from(sandbox.resolve("Polity", "Constitutional development and historical background")),
    ["Polity::Constitutional development"]
  );
  assert.deepEqual(
    Array.from(sandbox.resolve("Polity", "Fundamental Rights: key cases + Basic Structure doctrine + PYQs")),
    ["Polity::Fundamental Rights", "Polity::Basic Structure"]
  );
  assert.deepEqual(
    Array.from(sandbox.resolve("Polity", "Parliament: legislative procedure, Constitutional Amendments + PYQs")),
    [
      "Polity::Legislature",
      "Polity::Money Bill and Finance Bill",
      "Polity::Parliamentary Committees",
      "Polity::Anti-Defection Law",
      "Polity::Constitutional Amendments"
    ]
  );
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


test("study-plan recall always has a planner mastery fallback for unmapped or incomplete syllabus topics", () => {
  const start = script.indexOf("async function syncStudyPlanRevisionToSyllabus");
  const end = script.indexOf("\nfunction revisionDateAfter", start);
  const sync = script.slice(start, end);
  assert.match(sync, /let trackedCanonical=false/);
  assert.doesNotMatch(sync, /if\(!state\.topics\?\.\[key\]\)continue/);
  assert.match(sync, /if\(!trackedCanonical\)await recordMasteryProgress\("plan:"\+entry\.planIndex,quality,false\)/);
});

test("every curated syllabus topic maps to at least one first-pass study unit", () => {
  const subjectData = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\r?\nconst ROADMAP/)[1]);
  const mappingStart = script.indexOf("function normalizePlanTopic(");
  const mappingEnd = script.indexOf("\nfunction findMatchingSyllabusTopic(", mappingStart);
  assert.ok(mappingStart >= 0 && mappingEnd > mappingStart);
  const mappingSandbox = { SUBJECTS: subjectData, allSubjects: () => subjectData };
  vm.runInNewContext(
    script.slice(mappingStart, mappingEnd) + "\nthis.resolve=findMatchingSyllabusTopics;",
    mappingSandbox
  );

  const planStart = script.indexOf("const BASE_STUDY_PLAN=");
  const planEnd = script.indexOf(";\nconst STUDY_PLAN_TOPICS", planStart);
  assert.ok(planStart >= 0 && planEnd > planStart);
  const planSandbox = {};
  vm.runInNewContext(
    script.slice(planStart, planEnd) +
      "\nthis.studyUnits=BASE_STUDY_PLAN.flatMap(group=>group.days.map(topic=>({subject:group.subject,topic})));",
    planSandbox
  );
  const firstPassUnits = planSandbox.studyUnits.filter(unit =>
    !["Revision", "Full GS Revision", "Mock Tests", "Final Revision"].includes(unit.subject)
  );
  const missing = subjectData.flatMap(subject =>
    subject.topics
      .filter(([topic]) => !firstPassUnits.some(unit =>
        mappingSandbox.resolve(unit.subject, unit.topic).includes(subject.name + "::" + topic)
      ))
      .map(([topic]) => subject.name + "::" + topic)
  );

  assert.deepEqual(missing, [], "Unmapped syllabus topics: " + missing.join(", "));
});
