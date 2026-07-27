import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

test("editable click-to-add maps keep terrain loaded for waypoint altitude", () => {
  const source = readFileSync(join(process.cwd(), "src/components/TaskMap.tsx"), "utf8");
  assert.match(source, /const needsTerrainElevation = editable && Boolean\(onMapClick\)/);
  assert.match(source, /includeTerrain: isPerspective3D \|\| needsTerrainElevation/);
  assert.match(source, /isPerspective3D \|\| needsTerrainElevation \? \{ source: TERRAIN_SOURCE_ID, exaggeration \} : null/);
  assert.match(source, /elevationM \/ terrainExaggerationRef\.current/);
});

test("measurement mode intercepts map clicks before waypoint and route adds", () => {
  const source = readFileSync(join(process.cwd(), "src/components/TaskMap.tsx"), "utf8");
  assert.match(source, /measurementEnabledRef\.current/);
  assert.match(source, /measurementAvailableRef\.current/);
  assert.match(source, /map\.on\("mousemove", handleMeasurementMouseMove\)/);
  assert.match(source, /map\.on\("dblclick", handleMeasurementDoubleClick\)/);
  assert.match(source, /setMeasurementPoints\(\[\.\.\.measurementPointsRef\.current/);
  assert.ok(source.indexOf("if (measurementEnabledRef.current)") < source.indexOf("if (!editableRef.current"));
  assert.match(source, /formatDistanceLabel\(haversineKm/);
  assert.match(source, /aria-pressed=\{measurementEnabled\}/);
});

test("measurement total is anchored as a map label instead of the picker stack", () => {
  const source = readFileSync(join(process.cwd(), "src/components/TaskMap.tsx"), "utf8");
  const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
  assert.match(source, /id: "measurement-total-label"/);
  assert.match(source, /getPixelOffset: \[0, 30\]/);
  assert.doesNotMatch(source, /Measured route total/);
  assert.doesNotMatch(css, /map-measure-summary/);
});
