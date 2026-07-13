import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();

test("settings tab row includes waypoint files after pilot buddies", () => {
  const source = readFileSync(join(root, "src/components/dashboard/SettingsSection.tsx"), "utf8");
  assert.ok(source.indexOf('label: "Pilot Buddies"') < source.indexOf('label: "Waypoint Files"'));
  assert.match(source, /<WaypointFilesSettings token=\{token\} \/>/);
});

test("waypoint files settings exposes an add waypoint file upload", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesSettings.tsx"), "utf8");
  assert.match(source, />Add waypoint file</);
  assert.match(source, /accept="\.csv,\.geojson,\.json,\.gpx"/);
  assert.match(source, /\/api\/auth\/challenge-settings\/turnpoints\/upload/);
});

test("waypoint symbol picker keeps icon and text for LZ and Launch", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesEditor.tsx"), "utf8");
  assert.match(source, /label: "LZ"/);
  assert.match(source, /label: "Launch"/);
  assert.match(source, />◎↓<\/span>/);
  assert.match(source, />▲↗<\/span>/);
  assert.match(source, /<TurnpointSymbolIcon symbol=\{option\.value\} \/>/);
  assert.match(source, /<span>\{option\.label\}<\/span>/);
});

test("map renders LZ and Launch waypoint symbols as marker icons", () => {
  const source = readFileSync(join(root, "src/components/TaskMap.tsx"), "utf8");
  assert.match(source, /lz:/);
  assert.match(source, /launch:/);
  assert.match(source, /\["grass_strip", "paved_runway", "bar", "lz", "launch"\]/);
});
