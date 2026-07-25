import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();

test("event settings expose Mixed Class and all four handicap tiers", () => {
  const source = readFileSync(join(root, "src/components/dashboard/EventsSection.tsx"), "utf8");
  const handicap = readFileSync(join(root, "src/lib/handicap.ts"), "utf8");
  assert.match(source, /<span>Mixed Class<\/span>/);
  assert.match(source, /<legend>Handicap<\/legend>/);
  for (const label of ["Modern Topless", "High Performance Kingpost", "Intermediate Kingpost", "Single Surface"]) {
    assert.ok(handicap.includes(`label: "${label}"`));
  }
});

test("participant roster edits the event-specific pilot class", () => {
  const page = readFileSync(join(root, "src/app/dashboard/page.tsx"), "utf8");
  const roster = readFileSync(join(root, "src/components/dashboard/ParticipantCards.tsx"), "utf8");
  assert.match(page, /\/api\/events\/\$\{selectedEventId\}\/pilots\/\$\{pilotId\}\/class/);
  assert.match(roster, /<th>Class<\/th>/);
  assert.match(roster, /aria-label=\{`Class for \$\{pilot\.first_name\} \$\{pilot\.last_name\}`\}/);
});

test("internal and public task scores conditionally show handicap and class", () => {
  for (const relativePath of [
    "src/components/dashboard/ScoringSection.tsx",
    "src/app/scores/PublicScoresClient.tsx",
  ]) {
    const source = readFileSync(join(root, relativePath), "utf8");
    assert.match(source, /mixedClass \? <th>Handicap<\/th> : null/);
    assert.match(source, /formatHandicapAdjustment\(result\.handicap_adjustment_points\)/);
    assert.match(source, /className="results-pilot-class"/);
  }
});
