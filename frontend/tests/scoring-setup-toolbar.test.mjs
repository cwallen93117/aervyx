import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

test("scoring setup uses one account preset dropdown above the parameter fields", () => {
  const source = readFileSync(join(process.cwd(), "src/components/dashboard/EventsSection.tsx"), "utf8");
  const styles = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
  const toolbarStart = source.indexOf('<div className="scoring-import-strip">');
  const fieldsStart = source.indexOf('<div className="fieldset-grid events-scoring-grid">', toolbarStart);
  const toolbar = source.slice(toolbarStart, fieldsStart);

  assert.ok(toolbarStart >= 0 && fieldsStart > toolbarStart);
  assert.match(toolbar, /<optgroup label="Custom Parameters">/);
  assert.match(toolbar, /<optgroup label="Official Parameters">/);
  assert.match(toolbar, /Save As\s*<\/button>/);
  assert.match(toolbar, />Delete<\/button>/);
  assert.ok(toolbar.indexOf("Save As") < toolbar.indexOf(">Delete</button>"));
  assert.match(toolbar, /className="custom-formula-save-popover" role="dialog"/);
  assert.doesNotMatch(toolbar, /custom-formula-save-row/);
  assert.match(source, /type="submit" form="event-scoring-parameters-form">Save scoring parameters<\/button>/);
  assert.match(source, /id="event-scoring-parameters-form"/);
  assert.match(toolbar, /label="Scoring parameters"/);
  assert.doesNotMatch(toolbar, /Claude-guided placement/);
  assert.doesNotMatch(toolbar, /scoring-setup-group/);
  assert.doesNotMatch(toolbar, /Parameter preset/);
  assert.doesNotMatch(toolbar, /Load from Saved/);
  assert.doesNotMatch(toolbar, /Load Parameters/);
  assert.doesNotMatch(toolbar, /Delete custom formula/);
  assert.equal(source.match(/label="Scoring parameters"/g)?.length, 1);
  assert.equal(source.match(/Save scoring parameters/g)?.length, 1);
  assert.match(styles, /\.scoring-formula-field \.field-help-popover \{[\s\S]*left: calc\(100% \+ 10px\);[\s\S]*right: auto;/);
});

test("scoring cards stack handicap below nominal values and advanced scoring in column three", () => {
  const source = readFileSync(join(process.cwd(), "src/components/dashboard/EventsSection.tsx"), "utf8");
  const gridStart = source.indexOf('<div className="fieldset-grid events-scoring-grid">');
  const gridEnd = source.indexOf("</form>", gridStart);
  const grid = source.slice(gridStart, gridEnd);
  const columns = [...grid.matchAll(/<div className="scoring-fieldset-column">/g)].map((match) => match.index);

  assert.equal(columns.length, 3);
  assert.match(grid.slice(columns[0], columns[1]), /<legend>Formula and points<\/legend>/);
  assert.match(grid.slice(columns[1], columns[2]), /<legend>Nominal values and notes<\/legend>[\s\S]*<legend>Handicap<\/legend>/);
  assert.match(grid.slice(columns[2]), /<legend>Advanced scoring<\/legend>/);
});
