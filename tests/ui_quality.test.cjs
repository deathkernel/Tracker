const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const css = html.match(/<style>([\s\S]*?)<\/style>/)?.[1] || "";\nconst script = html.match(/<script\\b[^>]*>([\\s\\S]*?)<\\/script>/i)?.[1] || "";

function inspectCss(source) {
  let depth = 0;
  let quote = null;
  let escaped = false;
  let comment = false;
  const nestedMedia = [];

  for (let index = 0; index < source.length; index += 1) {
    const current = source[index];
    const next = source[index + 1];

    if (comment) {
      if (current === "*" && next === "/") {
        comment = false;
        index += 1;
      }
      continue;
    }

    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (current === "\\") {
        escaped = true;
        continue;
      }
      if (current === quote) quote = null;
      continue;
    }

    if (current === "/" && next === "*") {
      comment = true;
      index += 1;
      continue;
    }

    if (current === "\"" || current === "'") {
      quote = current;
      continue;
    }

    if (source.startsWith("@media", index) && depth !== 0) {
      nestedMedia.push(index);
    }

    if (current === "{") depth += 1;
    if (current === "}") {
      depth -= 1;
      assert.ok(depth >= 0, "CSS has an unmatched closing brace");
    }
  }

  return { depth, nestedMedia };
}

function relativeLuminance(hex) {
  const channels = [0, 2, 4].map((offset) => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground, background) {
  const first = relativeLuminance(foreground.replace("#", ""));
  const second = relativeLuminance(background.replace("#", ""));
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

test("UI stylesheet has balanced blocks and top-level responsive media queries", () => {
  const result = inspectCss(css);
  assert.equal(result.depth, 0, "Every CSS rule must be closed");
  assert.deepEqual(result.nestedMedia, [], "Responsive media queries must not be nested inside selectors");
  assert.match(css, /@media\s*\(max-width:\s*1100px\)/);
  assert.match(css, /@media\s*\(max-width:\s*760px\)/);
});

test("every workspace view is inside the main content landmark", () => {
  // Ignore CSS selectors and JavaScript strings: they can contain data-page
  // text before the actual HTML element and produce false positives.
  const markup = html
    .replace(/<style\b[\s\S]*?<\/style>/gi, "")
    .replace(/<script\b[\s\S]*?<\/script>/gi, "");

  assert.equal((markup.match(/<main\b/g) || []).length, 1);
  assert.equal((markup.match(/<\/main>/g) || []).length, 1);
  assert.doesNotMatch(markup, /<aside\b|<\/aside>/);
  const mainStart = markup.indexOf("<main>");
  const mainEnd = markup.indexOf("</main>", mainStart);
  assert.ok(mainStart >= 0 && mainEnd > mainStart, "main content landmark exists");

  for (const page of ["overview", "syllabus", "missing", "logs", "plan", "settings", "revision", "charts"]) {
    const pageElement = new RegExp("<(?:section|article|div)\\b[^>]*\\bdata-page=\"" + page + "\"");
    const match = pageElement.exec(markup);
    assert.ok(match, page + " workspace element exists");
    assert.ok(match.index > mainStart && match.index < mainEnd, page + " must be inside main");
  }
});
test("search and filter controls expose accessible names", () => {
  const ids = [
    "missingTopicSearch",
    "missingSubjectFilter",
    "missingPriorityFilter",
    "topicSearch",
    "subjectFilter",
    "topicStatus",
    "revisionSearch",
    "revisionSubject",
    "revisionStatus",
    "importFile"
  ];

  for (const id of ids) {
    const tag = html.match(new RegExp(`<(?:input|select)\\b[^>]*\\bid="${id}"[^>]*>`))?.[0];
    assert.ok(tag, `Control ${id} exists`);
    assert.match(tag, /aria-label="[^"]+"/, `Control ${id} needs an accessible label`);
  }
});

test("dashboard KPI describes all syllabus topics and starts with the correct base total", () => {
  assert.match(html, /class="stat-label">Syllabus topics completed/);
  assert.match(html, /id="topicsDone">0\/291/);
});

test("Overview syllabus progress uses one canonical snapshot and ignores stale or invalid topic keys", () => {
  assert.match(html, /aria-label="Syllabus topics completed"/);
  assert.match(script, /const getSyllabusProgressSummary=\(\)=>\{/);
  const start = script.indexOf("const getSyllabusProgressSummary=()=>{");
  const end = script.indexOf("\nconst totalTopics=", start);
  const summary = script.slice(start, end);
  assert.match(summary, /new Set\(Object\.entries\(state\.topics\|\|\{\}\)/);
  assert.match(summary, /validKeys\.has\(key\)&&done===true/);
  assert.match(summary, /completed:completedKeys\.size,total,percent:/);
  const statsStart = script.indexOf("function renderStats(){");
  const statsEnd = script.indexOf("\nfunction ", statsStart + 10);
  const stats = script.slice(statsStart, statsEnd);
  assert.match(stats, /syllabusProgress=getSyllabusProgressSummary\(\)/);
  assert.match(stats, /syllabusProgress\.completed\+"\/"\+syllabusProgress\.total/);
  assert.match(stats, /const topicPercent=syllabusProgress\.percent/);
});

test("toast notifications are announced and mobile tables remain touch-scrollable", () => {
  assert.match(html, /id="toast"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-atomic="true"/);
  assert.match(css, /\.data-table-wrap[^}]*overflow-x:auto/);
  assert.match(css, /-webkit-overflow-scrolling:touch/);
  assert.match(css, /\.daily-plan-table\{min-width:680px\}/);
});

test("completed and missed labels meet WCAG AA contrast for normal text", () => {
  assert.ok(contrastRatio("#526b5b", "#f3f8f5") >= 4.5);
  assert.ok(contrastRatio("#526b5b", "#ffffff") >= 4.5);
  assert.ok(contrastRatio("#80551e", "#fff8f6") >= 4.5);
});

test("customization controls support management and clearly separate self-paced topics", () => {
  assert.match(html, /id="customSyllabusManager"/);
  assert.match(html, /id="customDailyManager"/);
  assert.match(html, /Custom topics are included in syllabus progress and are self-paced/);
  assert.match(html, /"rename-topic"/);
  assert.match(html, /"delete-topic"/);
  assert.match(html, /"rename-task"/);
  assert.match(html, /"delete-task"/);
  assert.match(html, /function moveTopicStateKey\(/);
  assert.match(html, /function clearTopicStateKey\(/);
  assert.match(html, /function renderSettings\(/);
});

test("device theme selection is independent of responsive viewport width", () => {
  assert.match(html, /navigator\.userAgentData\?\.mobile/);
  assert.match(html, /navigator\.maxTouchPoints/);
  assert.doesNotMatch(html, /matchMedia\("\(max-width: 760px\)"\)\.addEventListener\("change",applyDeviceTheme\)/);
  assert.match(html, /document\.body\.dataset\.themeProfile=device/);
});
