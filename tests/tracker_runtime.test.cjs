const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync("index.html", "utf8");
const script = html.match(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i)?.[1] || "";

test("dashboard keeps the active Prelims topics as two-phase study units", () => {
  assert.match(script, /const STUDY_PLAN_TOPICS=BASE_STUDY_PLAN\.flatMap/);
  assert.match(script, /const SHUFFLED_STUDY_PLAN=buildSubjectRotatedStudyPlan\(STUDY_PLAN_TOPICS\)/);
  assert.match(script, /const PRELIMS_STUDY_TOPIC_LIMIT=92/);
  assert.match(script, /const ACTIVE_STUDY_PLAN=SHUFFLED_STUDY_PLAN\.slice\(0,PRELIMS_STUDY_TOPIC_LIMIT\)/);
  assert.match(script, /const DEFERRED_STUDY_PLAN=SHUFFLED_STUDY_PLAN\.slice\(PRELIMS_STUDY_TOPIC_LIMIT\)/);
  assert.match(script, /const DAILY_STUDY_PLAN=ACTIVE_STUDY_PLAN\.flatMap/);
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
  const priorityEnd = script.indexOf("\nfunction syncSyllabusCompletionToStudyPlan", priorityStart);
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
    "\nthis.top50=PRELIMS_TOP_50_KEYS;this.ordered=buildSubjectRotatedStudyPlan(units);this.active=this.ordered.slice(0,92);",
    sandbox
  );
  assert.equal(sandbox.top50.size, 50);
  assert.equal(sandbox.ordered.length, 189);
  assert.equal(sandbox.active.length, 92);
  assert.equal(sandbox.active.filter(entry => entry.priority === "P1").length, 48);
  assert.equal(sandbox.active.filter(entry => entry.priority === "P2").length, 44);
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
  const priorityEnd = script.indexOf("\nfunction syncSyllabusCompletionToStudyPlan", priorityStart);
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

test("alternating schedule pairs each new topic with a revision-only day", () => {
  const start = script.indexOf("function studyPlanDateOffset(entry){");
  const end = script.indexOf("\nfunction getStudyPlanDateKey(entry){",start);
  assert.ok(start>=0&&end>start);
  const sandbox={
    CYCLE_START_DATE:"2026-11-20",
    STUDY_PLAN_TOPICS:Array.from({length:189},()=>({})),
    state:{settings:{targetDate:"2027-11-02"}},
    isValidTargetDate:()=>true
  };
  vm.runInNewContext(script.slice(start,end)+"\nthis.offset=studyPlanDateOffset;",sandbox);
  for(let index=0;index<189;index++){
    assert.equal(sandbox.offset({planIndex:index,scheduleIndex:index}),index*2);
  }
  sandbox.state.settings.targetDate="2027-05-23";
  assert.equal(sandbox.offset({planIndex:91,scheduleIndex:91}),182);
  assert.match(script,/phase:"study",label:"Day 1 · New topic"/);
  assert.match(script,/phase:"mcq_revision",label:"Day 2 · Revision only"/);
  assert.match(script,/priority:isPriority\?"P1":"P2"/);
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

test("target date validation reserves enough calendar days for every study and revision pair", () => {
  const start = script.indexOf("function isValidTargetDate(value){");
  const end = script.indexOf("\nfunction getMinimumTargetDateKey", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {
    CYCLE_START_DATE: "2026-11-20",
    STUDY_PLAN_TOPICS: Array.from({ length: 189 }, () => ({})),
    ACTIVE_STUDY_PLAN: Array.from({ length: 92 }, () => ({})),
    localDateKey: date => [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0")
    ].join("-")
  };
  vm.runInNewContext(script.slice(start,end) + "\nthis.valid=isValidTargetDate;",sandbox);
  assert.equal(sandbox.valid("2027-05-21"),false);
  assert.equal(sandbox.valid("2027-05-22"),true);
  assert.equal(sandbox.valid("2027-05-23"),true);
  assert.equal(sandbox.valid("2026-02-30"),false);
  assert.equal(sandbox.valid("23-02-2027"),false);
  assert.match(script,/state\.settings\.targetDate=value;persist\(\);renderAll\(\)/);
  assert.match(script,/next\.settings\.targetDate="2027-05-23"/);
  assert.match(script,/incoming\.settings\?\.targetDate!==undefined&&!isValidTargetDate/);
});

test("each plan topic is followed by its own revision day", () => {
  const start = script.indexOf("function addDaysToDateKey(dateKey,days){");
  const end = script.indexOf("function getStudyPlanProgressDateKey(entry){",start);
  assert.ok(start>=0&&end>start);
  const sandbox={
    CYCLE_START_DATE:"2026-11-20",
    STUDY_PLAN_TOPICS:Array.from({length:189},()=>({})),
    state:{settings:{targetDate:"2027-11-02"}},
    localDateKey:date=>[date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-")
  };
  vm.runInNewContext(script.slice(start,end)+"\nthis.getDate=getStudyPlanDateKey;",sandbox);
  assert.equal(sandbox.getDate({planIndex:0,scheduleIndex:0,phase:"study"}),"2026-11-20");
  assert.equal(sandbox.getDate({planIndex:0,scheduleIndex:0,phase:"mcq_revision"}),"2026-11-21");
  assert.equal(sandbox.getDate({planIndex:1,scheduleIndex:1,phase:"study"}),"2026-11-22");
  assert.equal(sandbox.getDate({planIndex:1,scheduleIndex:1,phase:"mcq_revision"}),"2026-11-23");
  assert.equal(sandbox.getDate({planIndex:91,scheduleIndex:91,phase:"study"}),"2027-05-21");
  assert.equal(sandbox.getDate({planIndex:91,scheduleIndex:91,phase:"mcq_revision"}),"2027-05-22");
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

test("Day 2 is a revision-only phase with no new-topic MCQ task", () => {
  const completion = script.slice(script.indexOf("async function completePlanRevision"),script.indexOf("function renderPhaseChecklist"));
  assert.match(completion,/if\(!canCompleteStudyPlanPhase\(entry,"mcq_revision"\)\)/);
  assert.doesNotMatch(completion,/progress\.mcqDone=true/);
  assert.doesNotMatch(completion,/How many MCQs did you attempt/);
  assert.match(completion,/askRecallQuality\(entry\.topic,"revision"\)/);
  assert.match(script,/const REVISION_DAY_CHECKLIST=\[[\s\S]*?Revise the concise notes prepared on Day 1/);
});
test("Day 1 and Day 2 checklists gate their own Study Plan phases, not manual syllabus completion", () => {
  assert.match(script, /const STUDY_DAY_CHECKLIST=/);
  assert.match(script, /const REVISION_DAY_CHECKLIST=/);
  assert.match(script, /studyChecklist:normalizePhaseChecklist\(item\.studyChecklist,STUDY_DAY_CHECKLIST,!!item\.studyDone\)/);
  assert.match(script, /revisionChecklist:normalizePhaseChecklist\(item\.revisionChecklist,REVISION_DAY_CHECKLIST,!!item\.revisionDone\)/);
  assert.match(script, /function canCompleteStudyPlanPhase\(entry,phase\)/);
  assert.match(script, /if\(!canCompleteStudyPlanPhase\(entry,"study"\)\)/);
  assert.match(script, /if\(!canCompleteStudyPlanPhase\(entry,"mcq_revision"\)\)/);
  assert.match(script, /progress\.studyDone&&!!progress\.revisionDone&&isPhaseChecklistComplete\(progress,"study"\)&&isPhaseChecklistComplete\(progress,"mcq_revision"\)/);
  assert.match(script, /function completeTopicWithMastery\(subject,topic\)/);
  assert.doesNotMatch(script, /hasCompletedStudyCycleForSyllabusTopic/);
  assert.doesNotMatch(script, /Complete both Day 1 preparation and Day 2 MCQ \+ revision checklists before completing this topic/);
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

test("Missing Topics resolves shuffled schedule rows by stable original plan index", () => {
  const start = script.indexOf("function getStudyPlanEntryByPlanIndex(planIndex,phase){");
  const end = script.indexOf("\nfunction studyPlanDateOffset", start);
  assert.ok(start >= 0 && end > start);
  const entries = [
    { planIndex: 1, phase: "study", topic: "second" },
    { planIndex: 0, phase: "mcq_revision", topic: "first revision" },
    { planIndex: 0, phase: "study", topic: "first" },
    { planIndex: 1, phase: "mcq_revision", topic: "second revision" }
  ];
  const sandbox = { DAILY_STUDY_PLAN: entries };
  vm.runInNewContext(
    script.slice(start, end) + "\nthis.lookup=getStudyPlanEntryByPlanIndex;",
    sandbox
  );
  assert.equal(sandbox.lookup(0, "study").topic, "first");
  assert.equal(sandbox.lookup(1, "mcq_revision").topic, "second revision");
  const missing = script.slice(script.indexOf("function renderMissingTopics()"), script.indexOf("\nfunction renderRevision()", script.indexOf("function renderMissingTopics()")));
  assert.match(missing, /getStudyPlanEntryByPlanIndex\(planIndex,"study"\)/);
  assert.match(missing, /getStudyPlanEntryByPlanIndex\(planIndex,"mcq_revision"\)/);
  assert.doesNotMatch(missing, /DAILY_STUDY_PLAN\[planIndex\*2/);
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

test("legacy alias progress migrates when completion flags are true even if revision checklist is stale", () => {
  const start = script.indexOf("function removeDuplicateStudyPlanSyllabusCompletions(progress){");
  const end = script.indexOf("\nfunction normalizeProgressState(value){", start);
  assert.ok(start >= 0 && end > start);
  const entries = [
    { subject: "Polity", topic: "Constitutional development and historical background" },
    { subject: "Polity", topic: "Constituent Assembly and making of the Constitution" },
    { subject: "Polity", topic: "Preamble: keywords and philosophy" }
  ];
  const sandbox = {
    STUDY_PLAN_TOPICS: entries,
    findMatchingSyllabusTopics: (subject, topic) => topic.includes("Preamble:")
      ? ["Polity::Preamble", "Polity::Philosophy of Constitution"]
      : []
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.migrate=removeDuplicateStudyPlanSyllabusCompletions;", sandbox);
  const progress = {
    topics: {
      "Polity::Preamble": true,
      "Polity::Philosophy of Constitution": true
    },
    studyPlanProgress: {
      "plan:2": {
        studyDone: true,
        revisionDone: true,
        studyChecklist: { source: true, concepts: true, notes: true, recall: true },
        revisionChecklist: { notes: false, recall: false, "weak-points": false, "quick-review": false }
      }
    }
  };
  sandbox.migrate(progress);
  assert.deepEqual(Object.keys(progress.topics), ["Polity::Preamble"]);
});

test("one completed Day 1 + Day 2 study-plan topic counts once in subject progress", () => {
  const start = script.indexOf("function syncStudyPlanCompletionToSyllabus(entry){");
  const end = script.indexOf("\nasync function recordStudyReviewBatch", start);
  assert.ok(start >= 0 && end > start);
  const entry = { subject: "Polity", topic: "Preamble keywords philosophy", phase: "mcq_revision" };
  const sandbox = {
    state: { studyPlanProgress: { "plan:0": { studyDone: true, revisionDone: true } }, topics: {}, revisionSchedule: {} },
    STUDY_PLAN_TOPICS: [entry],
    findMatchingSyllabusTopics: () => ["Polity::Preamble", "Polity::Philosophy of Constitution"],
    isPhaseChecklistComplete: () => true,
    revisionDateAfter: () => "2026-11-22"
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.sync=syncStudyPlanCompletionToSyllabus;", sandbox);
  sandbox.sync(entry);
  sandbox.sync({ ...entry, phase: "study" });
  assert.deepEqual(Object.keys(sandbox.state.topics), ["Polity::Preamble"]);
  assert.deepEqual(Object.keys(sandbox.state.revisionSchedule), ["Polity::Preamble"]);
});

test("uncompletion invalidates linked study but preserves MCQ history", () => {
  assert.match(script, /function syncSyllabusUncompletionToStudyPlan\(subject,topic\)/);
  assert.match(script, /const progress=\{\.\.\.getStudyPlanProgress\(entry\),studyDone:false,mcqDone:false,revisionDone:false,studyChecklist:normalizePhaseChecklist\(null,STUDY_DAY_CHECKLIST,false\),revisionChecklist:normalizePhaseChecklist\(null,REVISION_DAY_CHECKLIST,false\),studyReset:true\}/);
  assert.match(script, /mcqCount:Number\.isInteger\(item\.mcqCount\)/);
  assert.match(script, /mcqDone:!reset&&!!\(current\.mcqDone/);
});

test("revision quality updates shared mastery and retest state through a batch endpoint", () => {
  assert.match(script, /apiFetch\("\/api\/study\/review-batch"/);
  assert.match(script, /previous_mastery:state\.masteryProgress/);
  assert.match(script, /previous_retest:state\.retestSchedule/);
  assert.match(script, /async function completeScheduledRetest\(subject,topic,progressKey=null\)/);
  assert.match(script, /Record retest/);
});

test("revision scheduling remains delegated to one backend batch calculation", () => {
  assert.match(script, /update_revision:updateRevision/);
  assert.match(script, /async function recordStudyReviewBatch\(/);
  assert.doesNotMatch(script, /fetch\("\/api\/revision\/next"/);
});

test("revision review batches do not mutate any topic when the backend batch fails", async () => {
  const start = script.indexOf("async function recordStudyReviewBatch(");
  const end = script.indexOf("async function syncStudyPlanRevisionToSyllabus", start);
  assert.ok(start >= 0 && end > start);
  const initial = {
    revisionSchedule: { "Polity::Rights": { due_date: "2026-11-21" } },
    revisionDone: {},
    masteryProgress: { "Polity::Rights": { reviews: 1, masteryLevel: 1 } },
    retestSchedule: {}
  };
  const sandbox = {
    state: structuredClone(initial),
    localDate: () => "2026-11-20",
    apiFetch: async () => ({ ok: false, status: 422, json: async () => ({}) })
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.run=recordStudyReviewBatch;", sandbox);
  await assert.rejects(
    sandbox.run(["Polity::Rights", "Polity::Basic Structure"], 4, { updateRevision: true }),
    /could not be updated/
  );
  assert.deepEqual(JSON.parse(JSON.stringify(sandbox.state)), initial);
});

test("revision review batch commits all topic results only after a complete response", async () => {
  const start = script.indexOf("async function recordStudyReviewBatch(");
  const end = script.indexOf("async function syncStudyPlanRevisionToSyllabus", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {
    state: { revisionSchedule: {}, revisionDone: {}, masteryProgress: {}, retestSchedule: {} },
    localDate: () => "2026-11-20",
    apiFetch: async (_url, options) => {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        json: async () => ({
          updates: body.reviews.map(item => ({
            key: item.key,
            revision_schedule: item.update_revision ? { due_date: "2026-11-21", interval_days: 1 } : null,
            mastery: { reviews: 1, quality_total: 4, average_quality: 4, mastery_level: 1, consecutive_strong: 1, last_quality: 4, last_reviewed_at: "2026-11-20" },
            retest: { due_date: "2026-11-27", attempts: 0, last_quality: 4, status: "scheduled", interval_days: 7 }
          }))
        })
      };
    }
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.run=recordStudyReviewBatch;", sandbox);
  await sandbox.run(["Polity::Rights", "Polity::Basic Structure"], 4, { updateRevision: true });
  assert.deepEqual(Object.keys(sandbox.state.masteryProgress).sort(), ["Polity::Basic Structure", "Polity::Rights"]);
  assert.equal(sandbox.state.revisionSchedule["Polity::Rights"].due_date, "2026-11-21");
  assert.equal(sandbox.state.revisionDone["Polity::Basic Structure"], true);
  assert.equal(sandbox.state.retestSchedule["Polity::Rights"].due_date, "2026-11-27");
});

test("activity backup validation keeps MCQs and notes and drops legacy duration fields", () => {
  const start = script.indexOf("function isValidDateKey(value){");
  const end = script.indexOf("const STORE=", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {
    localDateKey: date => [date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-")
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.validate=validateBackupLogs;this.normalize=normalizeStudyLogs;", sandbox);
  assert.throws(() => sandbox.validate({ "2026-11-20": null }), /invalid study log entry/);
  assert.throws(() => sandbox.validate({ "2026-02-30": { hours: 1 } }), /invalid study log entry/);
  assert.throws(() => sandbox.validate({ "2026-11-20": { mcqs: 1.5 } }), /invalid mcqs value/);
  assert.throws(() => sandbox.validate({ "2026-11-20": { notes: 7 } }), /invalid notes/);
  assert.doesNotThrow(() => sandbox.validate({ "2026-11-20": { hours: 25, csat: -30, mcqs: 20 } }));
  assert.deepEqual(
    JSON.parse(JSON.stringify(sandbox.normalize({
      "2026-11-20": { hours: 4, mcqs: 20, csat: 30, notes: "valid" },
      "2026-11-21": null,
      "2026-11-22": { hours: 2, csat: 15 },
      "2026-02-30": { hours: 1 }
    }))),
    { "2026-11-20": { mcqs: 20, notes: "valid" } }
  );
});

test("study hour and duration concepts are absent while exam dates and revision schedules remain", () => {
  for (const marker of ['id="hoursDone"', 'id="studyGoal"', 'id="logHours"', 'id="logCsat"', 'id="studyHoursChart"', 'id="logTotalHours"', 'id="newTaskTime"']) {
    assert.equal(html.includes(marker), false, marker);
  }
  for (const marker of ["Focused study time", "Daily study goal (hours)", "Study hours — last 7 days", "Total study hours", "CSAT minutes", "30 min", "10 min", "CSAT timed practice"]) {
    assert.equal(html.includes(marker), false, marker);
  }
  for (const marker of ["studyHoursTotal", "hours-line-graph", "Study hours over the last seven days", "hoursHost"]) {
    assert.equal(script.includes(marker), false, marker);
  }
  assert.match(script, /delete next\.settings\.studyGoal/);
  assert.match(script, /function normalizeStudyLogs\(value\)/);
  assert.match(script, /function normalizeRevisionSchedule\(value\)/);
  assert.match(script, /function normalizeRetestSchedule\(value\)/);
  assert.ok(html.includes('id="targetDate"'));
});

test("overview subject progress uses a dedicated scrollable table wrapper", () => {
  assert.match(html, /class="data-table-wrap subject-progress-wrap" id="subjectOverview"/);
  assert.match(html, /role="region" aria-label="Subject progress table" tabindex="0"/);
  assert.match(script, /table\.className="data-table subject-progress-table"/);
  assert.match(script, /table\.setAttribute\("aria-label","Subject completion by topic"\)/);
});

test("manual syllabus completion updates its mapped Day 1 phase without completing Day 2", () => {
  const start = script.indexOf("function syncSyllabusCompletionToStudyPlan(");
  const end = script.indexOf("\nfunction syncSyllabusUncompletionToStudyPlan", start);
  assert.ok(start >= 0 && end > start);
  const key = "Polity::Constitutional development";
  const entry = {
    subject: "Polity",
    topic: "Constitutional development and historical background",
    phase: "study",
    planIndex: 0
  };
  const items = [["source", "Read"], ["concepts", "Understand"], ["notes", "Notes"], ["recall", "Recall"]];
  const sandbox = {
    state: { topics: { [key]: true }, studyPlanProgress: {} },
    DAILY_STUDY_PLAN: [entry, { ...entry, phase: "mcq_revision" }],
    STUDY_DAY_CHECKLIST: items,
    validTopicKeys: () => new Set([key]),
    findMatchingSyllabusTopics: () => [key],
    getStudyPlanProgressDateKey: item => "plan:" + item.planIndex,
    getStudyPlanProgress: () => ({ revisionDone: false, mcqDone: false })
  };
  vm.runInNewContext(
    script.slice(start, end) + "\nthis.sync=syncSyllabusCompletionToStudyPlan;",
    sandbox
  );
  sandbox.sync("Polity", "Constitutional development");
  const progress = sandbox.state.studyPlanProgress["plan:0"];
  assert.equal(progress.studyDone, true);
  assert.equal(progress.studyReset, false);
  assert.deepEqual(JSON.parse(JSON.stringify(progress.studyChecklist)), {
    source: true, concepts: true, notes: true, recall: true
  });
  assert.equal(progress.revisionDone, false);
  assert.equal(progress.mcqDone, false);
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
  assert.match(script, /apiFetch\("\/api\/state"/);
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
  assert.match(sync, /const reviewKeys=keys\.length\?keys:\["plan:"\+entry\.planIndex\]/);
  assert.doesNotMatch(sync, /if\(!state\.topics\?\.\[key\]\)continue/);
  assert.match(sync, /recordStudyReviewBatch\(reviewKeys,quality/);
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



test("nested backup review records reject malformed and unsafe schedule values", () => {
  const start = script.indexOf("function isValidDateKey(value){");
  const end = script.indexOf("const STORE=", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {
    localDate: () => "2026-11-20",
    localDateKey: date => [date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-")
  };
  vm.runInNewContext(
    script.slice(start, end) +
      "\nthis.validate=validateBackupReviewRecords;" +
      "this.mastery=normalizeMasteryProgress;" +
      "this.revision=normalizeRevisionSchedule;" +
      "this.retest=normalizeRetestSchedule;",
    sandbox
  );

  assert.throws(() => sandbox.validate({
    masteryProgress: { "Polity::Rights": { qualityTotal: "Infinity" } }
  }), /qualityTotal/);
  assert.throws(() => sandbox.validate({
    revisionSchedule: { "Polity::Rights": { interval_days: 99999 } }
  }), /interval_days/);
  assert.throws(() => sandbox.validate({
    retestSchedule: { "Polity::Rights": { due_date: "2026-02-30" } }
  }), /due_date/);
  assert.throws(() => sandbox.validate({
    retestSchedule: { "Polity::Rights": { dueDate: "2026-02-30" } }
  }), /dueDate/);
  assert.throws(() => sandbox.validate({
    revisionSchedule: { "Polity::Rights": { intervalDays: 99999 } }
  }), /intervalDays/);
  assert.throws(() => sandbox.validate({
    masteryProgress: { "Polity::Rights": null }
  }), /invalid masteryProgress record/);
  assert.doesNotThrow(() => sandbox.validate({
    masteryProgress: {
      "Polity::Rights": {
        reviews: 2,
        qualityTotal: 8,
        averageQuality: 4,
        masteryLevel: 2,
        consecutiveStrong: 1,
        lastQuality: 4,
        lastReviewedAt: "2026-11-20"
      }
    },
    revisionSchedule: {
      "Polity::Rights": {
        due_date: "2026-11-21",
        interval_days: 6,
        repetitions: 2,
        ease_factor: 2.5
      },
      "Economy::Inflation": {
        dueDate: "2026-11-24",
        intervalDays: 6,
        repetitions: 2,
        easeFactor: 2.4,
        lastReviewedAt: "2026-11-20",
        lastQuality: 4
      }
    },
    retestSchedule: {
      "Polity::Rights": {
        due_date: "2026-11-23",
        attempts: 1,
        interval_days: 3,
        last_quality: 4,
        status: "scheduled"
      },
      "Economy::Inflation": {
        dueDate: "2026-11-23",
        attempts: 2,
        intervalDays: 3,
        lastQuality: 4,
        status: "scheduled"
      }
    }
  }));

  const mastery = sandbox.mastery({
    key: {
      reviews: 2,
      qualityTotal: "Infinity",
      averageQuality: 6,
      masteryLevel: 99,
      consecutiveStrong: -1
    }
  }).key;
  assert.equal(mastery.qualityTotal, 0);
  assert.equal(mastery.averageQuality, 0);
  assert.equal(mastery.masteryLevel, 0);
  assert.equal(mastery.consecutiveStrong, 0);

  const revision = sandbox.revision({
    key: { due_date: "invalid", interval_days: 99999, repetitions: 1000001, ease_factor: 8 }
  }).key;
  assert.equal(revision.due_date, "2026-11-20");
  assert.equal(revision.interval_days, 1);
  assert.equal(revision.repetitions, 0);
  assert.equal(revision.ease_factor, 2.5);

  const retest = sandbox.retest({ key: { due_date: "invalid", attempts: -1 } }).key;
  assert.equal(retest.due_date, "");
  assert.equal(retest.attempts, 0);

  const camelRevision = sandbox.revision({ key: {
    dueDate: "2026-11-24",
    intervalDays: 6,
    easeFactor: 2.4,
    lastReviewedAt: "2026-11-20",
    lastQuality: 4
  }}).key;
  assert.equal(camelRevision.due_date, "2026-11-24");
  assert.equal(camelRevision.interval_days, 6);
  assert.equal(camelRevision.ease_factor, 2.4);
  assert.equal(camelRevision.last_reviewed_at, "2026-11-20");
  assert.equal(camelRevision.last_quality, 4);

  const camelRetest = sandbox.retest({ key: {
    dueDate: "2026-11-23",
    attempts: 2,
    intervalDays: 3,
    lastQuality: 4
  }}).key;
  assert.equal(camelRetest.due_date, "2026-11-23");
  assert.equal(camelRetest.interval_days, 3);
  assert.equal(camelRetest.last_quality, 4);
  assert.equal(camelRetest.attempts, 2);
});


test("workspace navigation keeps page content below navigation and scopes dashboard metrics to Overview", () => {
  const navStart = html.indexOf('<nav class="cir-tabs" id="workspaceNav"');
  const navEnd = html.indexOf("</nav>", navStart);
  const headingStart = html.indexOf('<section class="page-context"');
  const mainStart = html.indexOf("<main>", navEnd);
  const settingsStart = html.indexOf('<section class="settings-page" data-page="settings"');
  assert.ok(navStart >= 0 && navEnd > navStart);
  assert.ok(navEnd < headingStart && headingStart < mainStart);
  assert.ok(mainStart < settingsStart);
  assert.match(script, /document\.body\.dataset\.view=activeView/);
  assert.match(script, /\$\("pageTitle"\)\.textContent=titles\[activeView\]/);
  assert.match(html, /body\[data-view\]:not\(\[data-view="overview"\]\) \.grid-stats/);
  assert.match(html, /#workspaceNav\.cir-tabs\{[^}]*grid-template-columns:repeat\(8,minmax\(0,1fr\)\)/);
  assert.match(html, /grid-auto-rows:minmax\(40px,auto\)/);
});


test("workspace navigation switches the visible page and updates its heading", () => {
  const start = script.indexOf("function setWorkspaceView(view){");
  const end = script.indexOf("\nfunction activeDevice()", start);
  assert.ok(start >= 0 && end > start);
  const names = ["overview", "syllabus", "missing", "logs", "plan", "settings", "revision", "charts"];
  const pages = names.map(name => ({
    dataset: { page: name },
    hidden: name !== "overview",
    attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; }
  }));
  const radios = names.map(value => ({ value, checked: value === "overview" }));
  const nodes = {
    pageTitle: { textContent: "Overview" },
    pageHint: { textContent: "Your daily preparation at a glance." }
  };
  const sandbox = {
    document: {
      body: { dataset: { view: "overview" } },
      querySelectorAll(selector) {
        if (selector === "[data-page]") return pages;
        if (selector === "#workspaceNav .cir-tabs__r") return radios;
        return [];
      }
    },
    window: { trackerView: "overview" },
    $: id => nodes[id]
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.switchView=setWorkspaceView;", sandbox);
  sandbox.switchView("syllabus");
  assert.equal(sandbox.document.body.dataset.view, "syllabus");
  assert.equal(sandbox.window.trackerView, "syllabus");
  assert.equal(nodes.pageTitle.textContent, "Syllabus");
  assert.equal(pages.find(page => page.dataset.page === "syllabus").hidden, false);
  assert.ok(pages.filter(page => page.dataset.page !== "syllabus").every(page => page.hidden));
  assert.equal(radios.find(radio => radio.value === "syllabus").checked, true);
  assert.ok(radios.filter(radio => radio.value !== "syllabus").every(radio => !radio.checked));
  sandbox.switchView("settings");
  assert.equal(nodes.pageTitle.textContent, "Settings");
  assert.equal(pages.find(page => page.dataset.page === "settings").hidden, false);
  assert.ok(pages.filter(page => page.dataset.page !== "settings").every(page => page.hidden));
});

test("workspace navigation is wired before state initialization and non-Overview pages start hidden", () => {
  const navHandler = script.indexOf('workspaceNavigation?.addEventListener("click"');
  const stateInitialization = script.indexOf("let state=defaultState()");
  assert.ok(navHandler >= 0 && stateInitialization > navHandler);
  assert.match(script, /workspaceNavigation\.contains\(label\)/);
  assert.match(script, /setWorkspaceView\(input\.value\)/);
  assert.match(html, /<body data-view="overview">/);
  assert.match(html, /\[data-page\]\[hidden\]\{display:none!important\}/);
  const pageTags = [...html.matchAll(/<section\b[^>]*\bdata-page="([^"]+)"([^>]*)>/g)];
  assert.ok(pageTags.some(([, page]) => page === "settings"));
  assert.ok(pageTags.filter(([, page]) => page !== "overview").every(([, , attributes]) => /\bhidden\b/.test(attributes)));
});


test("saved-state hydration runs only after study-plan migration dependencies initialize", () => {
  const defaultStateInit = script.indexOf("let state=defaultState()");
  const allSubjects = script.indexOf("const allSubjects=");
  const top50 = script.indexOf("const PRELIMS_TOP_50_KEYS=");
  const planTopics = script.indexOf("const STUDY_PLAN_TOPICS=");
  const dailyPlan = script.indexOf("const DAILY_STUDY_PLAN=");
  const savedStateHydration = script.indexOf("state=normalizeProgressState(readState())");
  assert.ok(defaultStateInit >= 0);
  assert.ok(defaultStateInit < allSubjects);
  assert.ok(allSubjects < top50);
  assert.ok(top50 < planTopics);
  assert.ok(planTopics < dailyPlan);
  assert.ok(dailyPlan < savedStateHydration);
  assert.equal(script.includes("let state=normalizeProgressState(readState())"), false);
});


test("legacy browser recovery snapshots restore saved progress after the primary state was blanked", () => {
  const start = script.indexOf("function hasSavedUserData(value){");
  const end = script.indexOf("\nfunction persist()", start);
  assert.ok(start >= 0 && end > start);
  const legacy = {
    version: 0,
    topics: { "Polity::Fundamental Rights": true },
    logs: { "2026-11-19": { mcqs: 20, notes: "saved notes" } },
    studyPlanProgress: { "plan:0": { studyDone: true } },
    studyPlanProgressSchema: 1
  };
  const storage = new Map([
    ["upsc-dashboard-v2", JSON.stringify({ version: 0, topics: {}, logs: {}, studyPlanProgress: {} })],
    ["upsc-dashboard-v2-recovery", JSON.stringify({
      reason: "The browser progress JSON was corrupt. The original raw value was preserved for recovery.",
      raw: JSON.stringify(legacy)
    })]
  ]);
  const sandbox = {
    STORE: "upsc-dashboard-v2",
    recoveredLegacyProgress: false,
    localStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, value); }
    },
    normalizeProgressState: value => value,
    defaultState: () => ({ version: 0, topics: {}, logs: {}, studyPlanProgress: {} })
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.loadState=readState;", sandbox);
  const recovered = sandbox.loadState();
  assert.equal(recovered.topics["Polity::Fundamental Rights"], true);
  assert.equal(recovered.logs["2026-11-19"].notes, "saved notes");
  assert.equal(sandbox.recoveredLegacyProgress, true);
});

test("legacy recovery never overrides a deliberate versioned empty progress reset", () => {
  const start = script.indexOf("function hasSavedUserData(value){");
  const end = script.indexOf("\nfunction persist()", start);
  assert.ok(start >= 0 && end > start);
  const storage = new Map([
    ["upsc-dashboard-v2", JSON.stringify({ version: 8, topics: {}, logs: {}, studyPlanProgress: {} })],
    ["upsc-dashboard-v2-recovery", JSON.stringify({
      reason: "The browser progress JSON was corrupt. The original raw value was preserved for recovery.",
      raw: JSON.stringify({ version: 2, topics: { "Polity::Fundamental Rights": true } })
    })]
  ]);
  const sandbox = {
    STORE: "upsc-dashboard-v2",
    recoveredLegacyProgress: false,
    localStorage: { getItem: key => storage.get(key) ?? null },
    normalizeProgressState: value => value,
    defaultState: () => ({ version: 0, topics: {}, logs: {}, studyPlanProgress: {} })
  };
  vm.runInNewContext(script.slice(start, end) + "\nthis.loadState=readState;", sandbox);
  const current = sandbox.loadState();
  assert.equal(current.version, 8);
  assert.equal(Object.keys(current.topics).length, 0);
  assert.equal(sandbox.recoveredLegacyProgress, false);
});



test("LAN API calls use a per-tab bearer token captured from the QR URL fragment", () => {
  assert.match(script, /const LAN_ACCESS_TOKEN_KEY="tracker-lan-access-token"/);
  assert.match(script, /new URLSearchParams\(window\.location\.hash\.slice\(1\)\)\.get\("access_token"\)/);
  assert.match(script, /window\.history\.replaceState\(null,"",window\.location\.pathname\+window\.location\.search\)/);
  assert.match(script, /headers\.set\("Authorization","Bearer "\+token\)/);
  assert.doesNotMatch(script, /fetch\("\/api\/(?:state|study\/review-batch|network-info)"/);
});


test("customization normalization preserves invalid-settings progress and sparse device theme fallbacks", () => {
  const start = script.indexOf("const defaultState=()=>");
  const end = script.indexOf("\nlet saveQueue=", start);
  assert.ok(start >= 0 && end > start);
  const subjects = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\r?\nconst ROADMAP/)[1]);
  const sandbox = {
    SUBJECTS: subjects,
    STUDY_PLAN_TOPICS: [],
    STUDY_DAY_CHECKLIST: [],
    REVISION_DAY_CHECKLIST: [],
    LEGACY_CYCLE_START_DATE: "2026-11-20",
    normalizeRevisionSchedule: value => value && typeof value === "object" ? value : {},
    normalizeMasteryProgress: value => value && typeof value === "object" ? value : {},
    normalizeRetestSchedule: value => value && typeof value === "object" ? value : {},
    normalizePhaseChecklist: value => value && typeof value === "object" ? value : {},
    normalizeStudyLogs: value => value && typeof value === "object" ? value : {},
    addDaysToDateKey: value => value,
    isValidTargetDate: () => true
  };

  vm.runInNewContext(
    script.slice(start, end) + "\nthis.normalize=normalizeProgressState;",
    sandbox
  );

  const recovered = sandbox.normalize({
    version: 4,
    settings: null,
    topics: { "Polity::Fundamental Rights": true },
    customSubjects: [{
      name: "polity",
      topics: [
        ["Fundamental Rights", 25, "P1"],
        ["Essay", 1, "P2"],
        ["Essay", 2, "P2"]
      ]
    }],
    studyPlanProgressSchema: 2
  });

  assert.equal(recovered.topics["Polity::Fundamental Rights"], true);
  assert.equal(recovered.settings.targetDate, "2027-05-23");
  assert.equal(recovered.customSubjects.length, 1);
  assert.equal(recovered.customSubjects[0].name, "Polity");
  assert.deepEqual(
    Array.from(recovered.customSubjects[0].topics, topic => topic[0]),
    ["Essay"]
  );

  const sparseTheme = sandbox.normalize({
    settings: {
      theme: "dark",
      deviceThemes: { desktop: "dark", mobile: "auto" }
    },
    studyPlanProgressSchema: 2
  });
  assert.equal(sparseTheme.settings.deviceThemes.desktop, "dark");
  assert.equal(Object.hasOwn(sparseTheme.settings.deviceThemes, "mobile"), false);
  assert.equal(
    sparseTheme.settings.deviceThemes.mobile || sparseTheme.settings.theme,
    "dark"
  );
});

test("custom topic identity migration uses canonical subject keys and rejects cross-subject collisions", () => {
  const subjectsStart = script.indexOf("const allSubjects=()=>{");
  const subjectsEnd = script.indexOf("\nfunction appendSettingsAction", subjectsStart);
  const helpersStart = script.indexOf("function canonicalSubjectName(");
  const helpersEnd = script.indexOf("\nfunction renderSettings(", helpersStart);
  assert.ok(subjectsStart >= 0 && subjectsEnd > subjectsStart);
  assert.ok(helpersStart >= 0 && helpersEnd > helpersStart);
  const subjects = JSON.parse(script.match(/const SUBJECTS=(\[[\s\S]*?\]);\r?\nconst ROADMAP/)[1]);

  const builtInState = {
    customSubjects: [{ name: "polity", topics: [["Essay", 1, "P2"]] }],
    topics: { "Polity::Essay": true },
    topicEvidence: { "Polity::Essay": { score: 4 } },
    pendingTopicEvidence: { "Polity::Essay": { pending: true } },
    revisionSchedule: { "Polity::Essay": { due_date: "2026-11-21" } },
    revisionDone: { "Polity::Essay": true },
    masteryProgress: { "Polity::Essay": { reviews: 2 } },
    retestSchedule: { "Polity::Essay": { due_date: "2026-11-22" } },
    recoveryQueue: [{ key: "Polity::Essay" }]
  };
  const canonicalSandbox = { state: builtInState, SUBJECTS: subjects };
  vm.runInNewContext(
    script.slice(subjectsStart, subjectsEnd) + "\n" +
    script.slice(helpersStart, helpersEnd) +
    "\nthis.rename=renameCustomTopic;this.remove=removeCustomTopic;",
    canonicalSandbox
  );

  assert.equal(canonicalSandbox.rename("polity", "Essay", "Optional Essay"), true);
  for (const key of [
    "topics",
    "topicEvidence",
    "pendingTopicEvidence",
    "revisionSchedule",
    "revisionDone",
    "masteryProgress",
    "retestSchedule"
  ]) {
    assert.ok(Object.hasOwn(builtInState[key], "Polity::Optional Essay"), key + " was not migrated");
    assert.equal(Object.hasOwn(builtInState[key], "Polity::Essay"), false, key + " kept the old key");
  }
  assert.equal(builtInState.recoveryQueue[0].key, "Polity::Optional Essay");
  assert.equal(canonicalSandbox.remove("polity", "Optional Essay"), true);
  for (const key of [
    "topics",
    "topicEvidence",
    "pendingTopicEvidence",
    "revisionSchedule",
    "revisionDone",
    "masteryProgress",
    "retestSchedule"
  ]) {
    assert.equal(Object.hasOwn(builtInState[key], "Polity::Optional Essay"), false, key + " was not cleared");
  }
  assert.equal(builtInState.recoveryQueue.length, 0);

  const collisionState = {
    customSubjects: [
      { name: "A", topics: [["X", 0, "P2"]] },
      { name: "A::B", topics: [["C", 0, "P2"]] }
    ],
    topics: { "A::X": true, "A::B::C": true }
  };
  const collisionSandbox = { state: collisionState, SUBJECTS: [] };
  vm.runInNewContext(
    script.slice(subjectsStart, subjectsEnd) + "\n" +
    script.slice(helpersStart, helpersEnd) +
    "\nthis.rename=renameCustomTopic;",
    collisionSandbox
  );

  assert.equal(collisionSandbox.rename("A", "X", "B::C"), false);
  assert.equal(collisionState.topics["A::X"], true);
  assert.equal(collisionState.topics["A::B::C"], true);
  assert.deepEqual(
    collisionState.customSubjects[0].topics.map(topic => topic[0]),
    ["X"]
  );
});


test("MCQ Tracker has a separate navigation page and persistent 50-question history", () => {
  assert.ok(html.includes('id="nav-mcq" value="mcq"'));
  assert.ok(html.includes('data-page="mcq"'));
  assert.ok(script.includes("next.mcqTests=Array.isArray(source.mcqTests)"));
  assert.ok(script.includes("const wrong=50-correct,unattempted=0,marks=correct*2,percentage=correct/50*100"));
  assert.ok(script.includes("const wrong=50-correct,percentage=correct/50*100"));
  assert.ok(script.includes('test.percentage.toFixed(0)+"%"'));
  assert.ok(script.includes("state.mcqTests.push("));
  assert.ok(script.includes("function getLatestMcqTest(planIndex)"));
  assert.ok(html.includes("Spreadsheet view"));
  assert.ok(script.includes('table.className="data-table mcq-sheet"'));
  assert.ok(script.includes('correctInput.className="mcq-correct-input"'));
  assert.ok(script.includes('const entries=DAILY_STUDY_PLAN.filter(entry=>entry.phase==="study"&&!!getStudyPlanProgress(entry).studyDone);'));
  assert.ok(script.includes("addCell(entry.topic)"));
  assert.ok(script.includes("&&!!getLatestMcqTest(entry.planIndex)"));
});

test("MCQ preparation assessment uses the agreed score bands", () => {
  const start = script.indexOf("function getMcqAssessment(percentage){");
  const end = script.indexOf("\nfunction renderMcqTracker(){", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = {};
  vm.runInNewContext(script.slice(start, end) + "\nthis.assess=getMcqAssessment;", sandbox);
  assert.equal(sandbox.assess(80).label, "Good");
  assert.equal(sandbox.assess(60).label, "Average");
  assert.equal(sandbox.assess(59).label, "Needs Improvement");
});


test("complete preparation timeline flows vertically and includes all milestone types and statuses", () => {
  assert.match(html, /id="nav-timeline" value="timeline"/);
  assert.match(html, /data-page="timeline"/);
  assert.match(html, /id="timelineSummary"/);
  assert.match(html, /Complete preparation timeline/);
  assert.match(html, /completed, in progress, missed and upcoming/);
  assert.match(html, /\.timeline-list::before/);
  assert.match(html, /\.timeline-event\.is-complete/);
  assert.match(html, /\.timeline-event\.is-pending/);
  assert.match(html, /\.timeline-event\.is-missed/);
  assert.match(script, /function renderTimeline\(\)/);
  assert.match(script, /DAILY_STUDY_PLAN\.forEach/);
  assert.match(script, /Object\.entries\(state\.logs\|\|\{\}\)/);
  assert.match(script, /state\.mcqTests\|\|\[\]/);
  assert.match(script, /state\.revisionSchedule/);
  assert.match(script, /state\.retestSchedule/);
  assert.match(script, /statusForDate/);
  assert.match(script, /sort\(\(a,b\)=>a\.localeCompare\(b\)\)/);
  assert.match(script, /renderTimeline\(\);setWorkspaceView/);
});
