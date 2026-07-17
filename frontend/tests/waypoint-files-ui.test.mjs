import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();

test("settings tab row keeps ordinary event waypoint files", () => {
  const source = readFileSync(join(root, "src/components/dashboard/SettingsSection.tsx"), "utf8");
  assert.ok(source.indexOf('label: "Pilot Buddies"') < source.indexOf('label: "Waypoint Files"'));
  assert.match(source, /<WaypointFilesSettings token=\{token\} \/>/);
});

test("waypoint files settings has no personal upload path", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesSettings.tsx"), "utf8");
  assert.doesNotMatch(source, />Add waypoint file</);
  assert.doesNotMatch(source, /challenge-settings/);
  assert.match(source, /\/api\/auth\/waypoint-files/);
});

test("waypoint file rows expose View and Edit actions", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesEditor.tsx"), "utf8");
  assert.match(source, /<th className="participant-table-actions">Actions<\/th>/);
  assert.match(source, /\{canEdit \? "Edit" : "View"\}/);
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

test("waypoint symbol picker bar icon matches the map marker shape", () => {
  const pickerSource = readFileSync(join(root, "src/components/dashboard/WaypointFilesEditor.tsx"), "utf8");
  const mapSource = readFileSync(join(root, "src/components/TaskMap.tsx"), "utf8");
  const barPath = "M9 7h30L27 22v14h8v5H13v-5h8V22L9 7zm8 5l7 8 7-8H17z";
  assert.match(pickerSource, /<svg className="turnpoint-symbol-icon bar"/);
  assert.ok(pickerSource.includes(barPath));
  assert.ok(mapSource.includes(barPath));
  assert.match(pickerSource, /<circle cx="34" cy="12" r="4" fill="#ef4444"/);
});

test("map renders LZ and Launch waypoint symbols as marker icons", () => {
  const source = readFileSync(join(root, "src/components/TaskMap.tsx"), "utf8");
  assert.match(source, /lz:/);
  assert.match(source, /launch:/);
  assert.match(source, /\["grass_strip", "paved_runway", "bar", "lz", "launch"\]/);
});
