import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = readFileSync(join(root, "src", "lib", "live-tracking-utils.ts"), "utf8");
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
  process: { env: {} },
  require,
  URL,
  window: undefined,
});

const {
  buildTrackCollection,
  displayPositionsForLiveTrack,
  latestDisplayPositionsBySubject,
  mergePositionGroup,
  segmentPositionsForLiveTrack,
} = module.exports;

function position(overrides) {
  return {
    id: overrides.id,
    pilot_id: 1,
    task_id: 10,
    lat: overrides.lat,
    lon: overrides.lon,
    alt: null,
    speed: null,
    heading: null,
    accuracy: null,
    timestamp: overrides.timestamp,
    source: overrides.source ?? "app",
    device_id: overrides.device_id ?? null,
    battery_level: null,
    aircraft_icon: "hang_glider",
    position_source: overrides.position_source ?? (overrides.source === "mqtt_gateway" || overrides.source === "mesh_relay" ? "mesh" : "cellular"),
    received_at: overrides.received_at,
  };
}

test("live display ignores delayed older fixes that arrive after newer fixes", () => {
  const first = position({
    id: "first",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T12:00:00Z",
    received_at: "2026-05-28T12:00:01Z",
  });
  const newer = position({
    id: "newer",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T12:02:00Z",
    received_at: "2026-05-28T12:02:01Z",
  });
  const delayed = position({
    id: "delayed",
    lat: 40.0005,
    lon: -75.0005,
    timestamp: "2026-05-28T12:01:00Z",
    received_at: "2026-05-28T12:03:00Z",
  });

  const merged = mergePositionGroup(new Map(), [first, newer, delayed]);
  assert.equal(JSON.stringify(merged.get("pilot:1").map((item) => item.id)), JSON.stringify(["first", "newer", "delayed"]));
  assert.equal(JSON.stringify(displayPositionsForLiveTrack(merged.get("pilot:1")).map((item) => item.id)), JSON.stringify(["first", "newer"]));
  assert.equal(latestDisplayPositionsBySubject(merged).get("pilot:1").id, "newer");

  const track = buildTrackCollection(merged, new Map([["pilot:1", "Mick Howard"]]));
  assert.equal(JSON.stringify(track.features[0].properties.timestamps), JSON.stringify(["2026-05-28T12:00:00Z", "2026-05-28T12:02:00Z"]));
  assert.equal(
    JSON.stringify(track.features[0].geometry.coordinates),
    JSON.stringify([
      [-75.0, 40.0, 0],
      [-75.001, 40.001, 0],
    ]),
  );
});

test("live track rendering keeps slow movement across large timestamp gaps connected", () => {
  const homeStart = position({
    id: "home-start",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T12:00:00Z",
    received_at: "2026-05-28T12:00:01Z",
  });
  const homeEnd = position({
    id: "home-end",
    lat: 40.0005,
    lon: -75.0005,
    timestamp: "2026-05-28T12:00:30Z",
    received_at: "2026-05-28T12:00:31Z",
  });
  const bankStart = position({
    id: "bank-start",
    lat: 40.01,
    lon: -75.01,
    timestamp: "2026-05-28T12:10:00Z",
    received_at: "2026-05-28T12:10:01Z",
  });
  const bankEnd = position({
    id: "bank-end",
    lat: 40.0105,
    lon: -75.0105,
    timestamp: "2026-05-28T12:10:30Z",
    received_at: "2026-05-28T12:10:31Z",
  });

  const positions = [homeStart, homeEnd, bankStart, bankEnd];
  const segments = segmentPositionsForLiveTrack(positions);
  assert.equal(JSON.stringify(segments.map((segment) => segment.map((item) => item.id))), JSON.stringify([
    ["home-start", "home-end", "bank-start", "bank-end"],
  ]));

  const track = buildTrackCollection(new Map([["pilot:1", positions]]), new Map([["pilot:1", "Mick Howard"]]));
  assert.equal(track.features.length, 1);
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.segment_index)), JSON.stringify([0]));
  assert.equal(JSON.stringify(track.features[0].geometry.coordinates), JSON.stringify([
    [-75.0, 40.0, 0],
    [-75.0005, 40.0005, 0],
    [-75.01, 40.01, 0],
    [-75.0105, 40.0105, 0],
  ]));
});

test("live track rendering keeps sparse long movement below 65 mph connected", () => {
  const beforeJumpA = position({
    id: "before-jump-a",
    lat: 40.0404933,
    lon: -75.3648283,
    timestamp: "2026-05-28T20:53:40Z",
    received_at: "2026-05-28T20:53:40Z",
  });
  const beforeJumpB = position({
    id: "before-jump-b",
    lat: 40.0405933,
    lon: -75.3647283,
    timestamp: "2026-05-28T20:53:57Z",
    received_at: "2026-05-28T20:53:57Z",
  });
  const afterJumpA = position({
    id: "after-jump-a",
    lat: 40.0550166,
    lon: -75.352,
    timestamp: "2026-05-28T20:56:00Z",
    received_at: "2026-05-28T20:56:00Z",
  });
  const afterJumpB = position({
    id: "after-jump-b",
    lat: 40.0551166,
    lon: -75.3519,
    timestamp: "2026-05-28T20:56:15Z",
    received_at: "2026-05-28T20:56:15Z",
  });

  const positions = [beforeJumpA, beforeJumpB, afterJumpA, afterJumpB];
  const track = buildTrackCollection(new Map([["pilot:1", positions]]), new Map([["pilot:1", "Jim Messina"]]));
  assert.equal(track.features.length, 1);
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.timestamps)), JSON.stringify([
    [
      "2026-05-28T20:53:40Z",
      "2026-05-28T20:53:57Z",
      "2026-05-28T20:56:00Z",
      "2026-05-28T20:56:15Z",
    ],
  ]));
});

test("live track rendering splits jumps above 65 mph", () => {
  const beforeJumpA = position({
    id: "before-fast-jump-a",
    lat: 40.0404933,
    lon: -75.3648283,
    timestamp: "2026-05-28T20:53:40Z",
    received_at: "2026-05-28T20:53:40Z",
  });
  const beforeJumpB = position({
    id: "before-fast-jump-b",
    lat: 40.0405933,
    lon: -75.3647283,
    timestamp: "2026-05-28T20:53:57Z",
    received_at: "2026-05-28T20:53:57Z",
  });
  const afterJumpA = position({
    id: "after-fast-jump-a",
    lat: 40.0550166,
    lon: -75.352,
    timestamp: "2026-05-28T20:54:35Z",
    received_at: "2026-05-28T20:54:35Z",
  });
  const afterJumpB = position({
    id: "after-fast-jump-b",
    lat: 40.0551166,
    lon: -75.3519,
    timestamp: "2026-05-28T20:54:50Z",
    received_at: "2026-05-28T20:54:50Z",
  });

  const positions = [beforeJumpA, beforeJumpB, afterJumpA, afterJumpB];
  const track = buildTrackCollection(new Map([["pilot:1", positions]]), new Map([["pilot:1", "Jim Messina"]]));
  assert.equal(track.features.length, 2);
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.timestamps)), JSON.stringify([
    ["2026-05-28T20:53:40Z", "2026-05-28T20:53:57Z"],
    ["2026-05-28T20:54:35Z", "2026-05-28T20:54:50Z"],
  ]));
});

test("live track rendering keeps cellular and mesh trails separate for the same subject", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const nearbyMesh = position({
    id: "nearby-mesh",
    lat: 40.01,
    lon: -75.01,
    timestamp: "2026-05-28T20:00:30Z",
    received_at: "2026-05-28T20:00:30Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const appB = position({
    id: "app-b",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:01:00Z",
    received_at: "2026-05-28T20:01:00Z",
  });
  const fallbackMeshA = position({
    id: "fallback-mesh-a",
    lat: 40.02,
    lon: -75.02,
    timestamp: "2026-05-28T20:05:00Z",
    received_at: "2026-05-28T20:05:00Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const fallbackMeshB = position({
    id: "fallback-mesh-b",
    lat: 40.021,
    lon: -75.021,
    timestamp: "2026-05-28T20:05:30Z",
    received_at: "2026-05-28T20:05:30Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const display = displayPositionsForLiveTrack([appA, nearbyMesh, appB, fallbackMeshA, fallbackMeshB]);
  assert.equal(JSON.stringify(display.map((item) => item.id)), JSON.stringify(["app-a", "nearby-mesh", "app-b", "fallback-mesh-a", "fallback-mesh-b"]));

  const latest = latestDisplayPositionsBySubject(new Map([["pilot:1", display]])).get("pilot:1");
  assert.equal(latest.id, "fallback-mesh-b");

  const track = buildTrackCollection(new Map([["pilot:1", display]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track.features.length, 2);
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.source_bucket)), JSON.stringify(["cellular", "mesh"]));
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.timestamps)), JSON.stringify([
    ["2026-05-28T20:00:00Z", "2026-05-28T20:01:00Z"],
    ["2026-05-28T20:00:30Z", "2026-05-28T20:05:00Z", "2026-05-28T20:05:30Z"],
  ]));
});

test("live marker prefers recent cellular points without hiding mesh geometry", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const meshA = position({
    id: "mesh-a",
    lat: 40.01,
    lon: -75.01,
    timestamp: "2026-05-28T20:00:30Z",
    received_at: "2026-05-28T20:00:30Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const appB = position({
    id: "app-b",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:01:00Z",
    received_at: "2026-05-28T20:01:00Z",
  });
  const meshB = position({
    id: "mesh-b",
    lat: 40.011,
    lon: -75.011,
    timestamp: "2026-05-28T20:01:30Z",
    received_at: "2026-05-28T20:01:30Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const latest = latestDisplayPositionsBySubject(new Map([["pilot:1", [appA, meshA, appB, meshB]]])).get("pilot:1");
  assert.equal(latest.id, "app-b");
});
