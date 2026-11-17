# Power BI Dashboard — UPSC Tracker

## Export data
1. Keep powerbi_export.py beside tracker.db and index.html.
2. Open Command Prompt in the Tracker folder.
3. Run: python powerbi_export.py
4. In Power BI Desktop, import all CSV files from powerbi_data.

The exporter reads the SQLite saved state and syllabus/planner definitions. It never modifies tracker.db.

## Relationships
- Topics[TopicKey] → TopicProgress[TopicKey]
- Calendar[Date] → StudyLogs[Date]
- Calendar[Date] → DailyChecklist[Date]
- Calendar[Date] → StudyPlan[Date]

Use one-to-many, single-direction relationships from dimensions to facts.

## Relevant report visuals
### Overview
- KPI cards: syllabus completion, completed topics, study hours, MCQs, CSAT.
- Line chart: study hours over time.
- Line chart: MCQs and CSAT over time (separate charts if scales differ).
- Calendar heatmap: study activity.
- Slicers: Subject, Priority, Date.

### Subject analysis
- Dot plot: completion percentage by subject.
- Treemap: completed topics by subject and priority.
- Matrix: subject → topic with completion and revision status.

### Consistency and planning
- Line chart: weekly study hours.
- Line chart: study-plan days completed by week.
- Calendar heatmap: daily checklist activity.

### Revision
- Gauge/progress ring: revised topics vs completed topics.
- Dot plot: revision completion by subject.
- Matrix: topic-level revision status.

## DAX measures
```DAX
Completed Topics =
CALCULATE(COUNTROWS(TopicProgress), TopicProgress[IsCompleted] = TRUE())

Total Topics = COUNTROWS(TopicProgress)

Syllabus Completion % = DIVIDE([Completed Topics], [Total Topics], 0)

Revised Topics =
CALCULATE(COUNTROWS(TopicProgress), TopicProgress[IsCompleted] = TRUE(), TopicProgress[IsRevised] = TRUE())

Revision Completion % = DIVIDE([Revised Topics], [Completed Topics], 0)

Study Hours = SUM(StudyLogs[StudyHours])
MCQs Solved = SUM(StudyLogs[MCQs])
CSAT Attempts = SUM(StudyLogs[CSAT])

Study Plan Days Completed =
CALCULATE(COUNTROWS(StudyPlan), StudyPlan[IsCompleted] = TRUE())

Study Plan Completion % =
DIVIDE([Study Plan Days Completed], COUNTROWS(StudyPlan), 0)
```

## Refresh
After logging more study in Tracker, run python powerbi_export.py again, then click Refresh in Power BI Desktop. This is a snapshot export, not a live database connection.

No synthetic study values are generated. Missing study logs are not fabricated.
