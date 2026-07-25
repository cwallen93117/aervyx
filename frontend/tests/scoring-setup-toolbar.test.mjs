import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

test("scoring setup promotes formula and saved-meet controls above the parameter fields", () => {
  const source = readFileSync(join(process.cwd(), "src/components/dashboard/EventsSection.tsx"), "utf8");
  const toolbarStart = source.indexOf('<div className="scoring-import-strip">');
  const fieldsStart = source.indexOf('<div className="fieldset-grid events-scoring-grid">', toolbarStart);
  const toolbar = source.slice(toolbarStart, fieldsStart);

  assert.ok(toolbarStart >= 0 && fieldsStart > toolbarStart);
  assert.match(toolbar, /<strong>Current formula<\/strong>/);
  assert.match(toolbar, /<strong>Load from Saved<\/strong>/);
  assert.match(toolbar, />Save As<\/button>/);
  assert.match(toolbar, />\s*Load Parameters\s*<\/button>/);
  assert.match(toolbar, /label="Scoring formula"/);
  assert.doesNotMatch(toolbar, /Claude-guided placement/);
  assert.equal(source.match(/label="Scoring formula"/g)?.length, 1);
});
