import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();

test("public live map passes public airspace settings into TaskMap", () => {
  const source = readFileSync(join(root, "src/app/live/LiveWatchClient.tsx"), "utf8");
  assert.match(source, /setPublicAirspaceCategories\(normalizeAirspaceCategories\(settings\.public_airspace_categories_json\)\)/);
  assert.match(source, /setLiveTaskAirspaces\(task\.airspaces \?\? \[\]\)/);
  assert.match(source, /airspaces=\{liveTaskAirspaces\}/);
  assert.match(source, /faaAirspaceCategories=\{publicAirspaceCategories\}/);
  assert.match(source, /overlayConfig=\{overlayConfig\}/);
});

test("public live overlay defaults include FAA airspace", () => {
  const source = readFileSync(join(root, "../backend/app/services/map_overlay_config.py"), "utf8");
  assert.match(source, /"public_live": \{[\s\S]*"faa_airspace": True/);
  assert.match(source, /"public_live": \{[\s\S]*"airspace": \["faa_airspace"\]/);
});

test("airspace chip is above the basemap picker and exposes browser-verifiable state", () => {
  const source = readFileSync(join(root, "src/components/TaskMap.tsx"), "utf8");
  assert.match(source, /data-faa-airspace-enabled=\{faaAirspaceEnabled \? "true" : "false"\}/);
  assert.match(source, /data-faa-airspace-count=\{faaAirspaceData\.features\.length\}/);
  assert.match(source, /data-uploaded-airspace-count=\{effectiveAirspaces\.length\}/);
  assert.match(source, /const effectiveAirspaces = showFaaAirspace/);
  assert.match(source, /removeFaaAirspaceOverlay\(map\)/);
  assert.match(source, /map\.triggerRepaint\(\)/);
  assert.match(source, /if \(!faaAirspaceEnabled\) \{/);
  assert.ok(source.indexOf("<span>Show Airspace</span>") < source.indexOf("<span>Map</span>"));
});
