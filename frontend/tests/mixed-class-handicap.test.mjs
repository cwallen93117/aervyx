import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

const root = process.cwd();
const require = createRequire(import.meta.url);
const ts = require("typescript");

function loadTsModule(relativePath, deps = {}) {
  const source = readFileSync(join(root, relativePath), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(transpiled, {
    console,
    exports: module.exports,
    module,
    require: (name) => deps[name] ?? require(name),
  });
  return module.exports;
}

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
    assert.match(source, /setHandicapDetailsResult\(result\)/);
    assert.match(source, /className="results-pilot-class"/);
  }
});

test("handicap and penalty helpers format thousands and use normalized pre-penalty base", () => {
  const scorePenalties = loadTsModule("src/lib/scorePenalties.ts");
  const handicap = loadTsModule("src/lib/handicap.ts", { "./scorePenalties": scorePenalties });
  const result = {
    raw_score_points: 800,
    score_points: 850,
    handicap_adjustment_points: 100,
    penalty_calculation: {
      raw_score_points: 800,
      final_score_points: 850,
      manual_penalty_points: 50,
      engine_penalty_points: 25,
      total_display_penalty_points: 75,
      lines: [],
    },
    details_json: {
      handicap: {
        pilot_class: "single_surface",
        multiplier: 1.25,
        official_score_points: 800,
        multiplied_score_points: 1_100,
        normalization_max_score_points: 1_222.2,
        adjusted_score_points: 900,
        adjustment_points: 100,
      },
    },
  };

  assert.equal(scorePenalties.formatScorePoints(1000), "1,000.0");
  assert.equal(scorePenalties.formatPenaltyPointsValue(1234.56), "-1,234.6");
  assert.equal(handicap.formatHandicapAdjustment(1234.56), "+1,234.6");
  assert.equal(scorePenalties.prePenaltyTotalPoints(result), 900);
  assert.equal(JSON.stringify(handicap.handicapDetails(result)), JSON.stringify(result.details_json.handicap));
});
