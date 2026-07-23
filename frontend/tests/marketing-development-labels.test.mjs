import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const source = readFileSync(
  join(process.cwd(), "src/app/marketing/aervyx-body.html"),
  "utf8",
);

test("unfinished marketing features are labeled under development", () => {
  assert.doesNotMatch(source, /coming soon/i);

  for (const feature of [
    "NOTAMs on the Map",
    "Soaring forecast",
    "Driver Navigation",
    "SOS alerting",
  ]) {
    const featureIndex = source.toLowerCase().indexOf(feature.toLowerCase());
    assert.notEqual(featureIndex, -1, `${feature} claim should exist`);
    assert.match(
      source.slice(featureIndex, featureIndex + 300),
      /class="[^"]*under-development[^"]*">Under Development</,
      `${feature} should be labeled Under Development`,
    );
  }
});

test("marketing identifies the public AGPLv3 release", () => {
  assert.match(source, /GNU Affero General Public License v3\.0/);
  assert.match(source, /AGPLv3 Open Source/);
  assert.doesNotMatch(source, /license pending|source release (?:pending|in preparation)/i);
});
