const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const css = html.match(/<style>([\s\S]*?)<\/style>/)?.[1] || "";

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
  assert.equal((html.match(/<main\b/g) || []).length, 1);
  assert.equal((html.match(/<\/main>/g) || []).length, 1);
  assert.doesNotMatch(html, /<aside\b|<\/aside>/);
  const mainStart = html.indexOf("<main>");
  const mainEnd = html.indexOf("</main>", mainStart);
  for (const page of ["overview", "syllabus", "missing", "logs", "plan", "settings", "revision", "charts"]) {
    const pageIndex = html.indexOf(`data-page="${page}"`);
    assert.ok(pageIndex > mainStart && pageIndex < mainEnd, `${page} must be inside main`);
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

test("Uiverse Halo checkbox is the shared accessible completion control", () => {
  const helperStart = html.indexOf("function createAnimatedCheckbox");
  const helperEnd = html.indexOf("\\nfunction getTodayStudyActivities", helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart);
  const helper = html.slice(helperStart, helperEnd);
  assert.match(helper, /wrapper\\.className="uiverse-checkbox"/);
  assert.match(helper, /input\\.className="uiverse-checkbox__input"/);
  assert.match(helper, /input\\.setAttribute\\("aria-label",ariaLabel\\)/);
  assert.match(helper, /wrapper\\.append\\(input,mark\\)/);

  const phaseStart = html.indexOf("function renderPhaseChecklist");
  const phaseEnd = html.indexOf("\\nfunction ", phaseStart + 1);
  assert.ok(phaseStart >= 0 && phaseEnd > phaseStart);
  const phase = html.slice(phaseStart, phaseEnd);
  assert.match(phase, /createAnimatedCheckbox\\(!!progress\\[field\\]\\?\\.\\[id\\],labelText\\+" · "\\+entry\\.topic\\)/);
  assert.match(phase, /input\\.disabled=phaseDone\\|\\|locked/);
  assert.match(phase, /row\\.append\\(check\\.wrapper,label\\)/);
  assert.doesNotMatch(phase, /document\\.createElement\\("input"\\)/);

  assert.match(css, /\\.uiverse-checkbox__input:checked\\+\\.uiverse-checkbox__mark/);
  assert.match(css, /\\.uiverse-checkbox__input:focus-visible/);
  assert.match(css, /\\.phase-check \\.uiverse-checkbox__input/);
  assert.match(html, /Halo square checkbox by uiverse-astronaut/);
});

test("Uiverse checkbox, buttons and page transitions respect reduced motion", () => {
  assert.match(css, /@keyframes tracker-page-enter/);
  assert.match(css, /\\.main-grid\\.nav-mode \\[data-page\\]:not\\(\\[hidden\\]\\)\\{animation:tracker-page-enter/);
  assert.match(css, /\\.btn:active:not\\(:disabled\\)/);
  assert.match(css, /@media\\(prefers-reduced-motion:reduce\\)\\{[^}]*\\.uiverse-checkbox__input[^}]*animation:none!important/);
});
