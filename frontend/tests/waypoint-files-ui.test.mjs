import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();

test("settings exposes the staff-only Turnpoint Library", () => {
  const source = readFileSync(join(root, "src/components/dashboard/SettingsSection.tsx"), "utf8");
  assert.match(source, /WaypointFilesSettings/);
  assert.match(source, /Turnpoint Library/);
  assert.match(source, /canManagePlatform/);
  assert.match(source, /turnpoint_library/);
});

test("event turnpoint files select from the shared library", () => {
  const eventsSource = readFileSync(join(root, "src/components/dashboard/EventsSection.tsx"), "utf8");
  const catalogSource = readFileSync(join(root, "src/components/dashboard/WaypointFilesSettings.tsx"), "utf8");
  assert.match(eventsSource, /\/api\/turnpoint-library/);
  assert.match(eventsSource, /\/api\/events\/\$\{selectedEventId\}\/turnpoint-sources\/\$\{source\.id\}/);
  assert.match(eventsSource, /type="checkbox"/);
  assert.doesNotMatch(eventsSource, /turnpoint-sources\/upload/);
  assert.match(catalogSource, /\/api\/turnpoint-library/);
  assert.match(catalogSource, /\/api\/turnpoint-library\/upload/);
});

test("pilot navigation defaults to Tasks and omits Events", () => {
  const source = readFileSync(join(root, "src/app/dashboard/page.tsx"), "utf8");
  const pilotItemsStart = source.indexOf("const pilotSidebarItems = [");
  const pilotItemsEnd = source.indexOf("] satisfies SidebarItem[];", pilotItemsStart);
  const pilotItems = source.slice(pilotItemsStart, pilotItemsEnd);
  assert.doesNotMatch(pilotItems, /id: "events"/);
  assert.match(pilotItems, /id: "tasks"/);
  assert.match(source, /if \(role === "pilot"\) return "tasks";/);
});

test("Tasks exposes selected event waypoint and airspace downloads", () => {
  const source = readFileSync(join(root, "src/components/dashboard/TasksSection.tsx"), "utf8");
  assert.match(source, /turnpointSources: TurnpointSourceRecord\[\]/);
  assert.match(source, /airspaceSources: AirspaceSourceRecord\[\]/);
  assert.match(source, /<legend>Downloads<\/legend>/);
  assert.match(source, /\/api\/events\/\$\{selectedEventId\}\/turnpoint-sources\/\$\{source\.id\}\/download\?format=/);
  assert.match(source, /\/api\/events\/\$\{selectedEventId\}\/airspace-sources\/\$\{source\.id\}\/download/);
});

test("library table has the requested columns and file operations", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesEditor.tsx"), "utf8");
  assert.match(source, /<th>Selection<\/th>/);
  assert.match(source, /<th>File name<\/th>/);
  assert.match(source, /<th>Format<\/th>/);
  assert.match(source, /<th>Waypoints<\/th>/);
  assert.match(source, /<th className="participant-table-actions">Actions<\/th>/);
  assert.doesNotMatch(source, /<th>Context<\/th>/);
  assert.doesNotMatch(source, /<th>Uploaded<\/th>/);
  assert.doesNotMatch(source, /<th>Visible<\/th>/);
  assert.match(source, /Merge selected/);
  assert.match(source, /className="compact-slot-actions"/);
});

test("Save As defaults to the source format and supports conversion", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesEditor.tsx"), "utf8");
  assert.match(source, /setSaveAsFormat\(defaultExportFormat\(source\.file_format\)\)/);
  assert.match(source, /value: "gpx", label: "GPX"/);
  assert.match(source, /value: "csv", label: "CSV"/);
  assert.match(source, /value: "cup", label: "CUP"/);
  assert.match(source, /value: "wpt", label: "WPT"/);
  assert.match(source, /value: "kmz", label: "KMZ"/);
  assert.doesNotMatch(source, /<option value="geojson">GeoJSON<\/option>/);
  assert.match(source, /\/api\/turnpoint-library\/\$\{saveAsSource\.id\}\/save-as/);
});

test("turnpoint library upload picker no longer advertises GeoJSON", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesSettings.tsx"), "utf8");
  assert.match(source, /accept="\.csv,\.gpx"/);
  assert.doesNotMatch(source, /accept="\.csv,\.geojson,\.json,\.gpx"/);
});

test("open file detail keeps only the upper-right close control above the map", () => {
  const source = readFileSync(join(root, "src/components/dashboard/WaypointFilesEditor.tsx"), "utf8");
  const detailStart = source.indexOf('<div className="turnpoint-file-detail">');
  const mapStart = source.indexOf("<TaskMap", detailStart);
  const detailHeader = source.slice(detailStart, mapStart);
  assert.match(detailHeader, /className="results-sheet-header turnpoint-detail-header"/);
  assert.match(detailHeader, /className="turnpoint-detail-close"/);
  assert.doesNotMatch(detailHeader, />Download</);
  assert.doesNotMatch(detailHeader, />Rename</);
  assert.doesNotMatch(detailHeader, />Save as</);
  assert.doesNotMatch(detailHeader, />Refresh</);
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
