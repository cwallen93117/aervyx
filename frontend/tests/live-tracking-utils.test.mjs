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
const batterySource = readFileSync(join(root, "src", "lib", "admin-debug-battery.ts"), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    esModuleInterop: true,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const batteryTranspiled = ts.transpileModule(batterySource, {
  compilerOptions: {
    esModuleInterop: true,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

const module = { exports: {} };
const batteryModule = { exports: {} };
vm.runInNewContext(transpiled, {
  console,
  exports: module.exports,
  module,
  process: { env: {} },
  require,
  URL,
  window: undefined,
});
vm.runInNewContext(batteryTranspiled, {
  console,
  exports: batteryModule.exports,
  module: batteryModule,
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
const { adminDebugBatterySummary } = batteryModule.exports;

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
    mesh_seq_number: overrides.mesh_seq_number ?? null,
    battery_level: null,
    aircraft_icon: "hang_glider",
    position_source: overrides.position_source ?? (overrides.source === "mqtt_gateway" || overrides.source === "mesh_relay" ? "mesh" : "cellular"),
    received_at: overrides.received_at,
  };
}

test("admin debug battery summary labels phone and tracker batteries", () => {
  assert.equal(
    JSON.stringify(adminDebugBatterySummary({ phoneBatteryLevel: 87, trackerBatteryLevel: 96 })),
    JSON.stringify([
      { label: "Phone", level: 87 },
      { label: "Tracker", level: 96 },
    ]),
  );
  assert.equal(JSON.stringify(adminDebugBatterySummary({ phoneBatteryLevel: 87 })), JSON.stringify([{ label: "Phone", level: 87 }]));
  assert.equal(JSON.stringify(adminDebugBatterySummary({ trackerBatteryLevel: 96 })), JSON.stringify([{ label: "Tracker", level: 96 }]));
  assert.equal(JSON.stringify(adminDebugBatterySummary({})), JSON.stringify([]));
});

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

test("live track rendering fuses cellular and mesh into one subject trail", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const nearbyMesh = position({
    id: "mesh-gap",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:00:30Z",
    received_at: "2026-05-28T20:00:30Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const appB = position({
    id: "app-b",
    lat: 40.002,
    lon: -75.002,
    timestamp: "2026-05-28T20:01:00Z",
    received_at: "2026-05-28T20:01:00Z",
  });

  const display = displayPositionsForLiveTrack([appA, nearbyMesh, appB]);
  assert.equal(JSON.stringify(display.map((item) => item.id)), JSON.stringify(["app-a", "mesh-gap", "app-b"]));

  const latest = latestDisplayPositionsBySubject(new Map([["pilot:1", display]])).get("pilot:1");
  assert.equal(latest.id, "app-b");

  const track = buildTrackCollection(new Map([["pilot:1", display]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track.features.length, 1);
  assert.equal(track.features[0].properties.source_bucket, undefined);
  assert.equal(JSON.stringify(track.features[0].properties.timestamps), JSON.stringify([
    "2026-05-28T20:00:00Z",
    "2026-05-28T20:00:30Z",
    "2026-05-28T20:01:00Z",
  ]));
});

test("live fused track rejects app and mesh ping-pong connectors", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const meshA = position({
    id: "mesh-far",
    lat: 40.02,
    lon: -75.02,
    timestamp: "2026-05-28T20:00:01Z",
    received_at: "2026-05-28T20:00:01Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const appB = position({
    id: "app-b",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:00:30Z",
    received_at: "2026-05-28T20:00:30Z",
  });

  const latest = latestDisplayPositionsBySubject(new Map([["pilot:1", [appA, meshA, appB]]])).get("pilot:1");
  assert.equal(latest.id, "app-b");

  const track = buildTrackCollection(new Map([["pilot:1", [appA, meshA, appB]]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track.features.length, 1);
  assert.equal(JSON.stringify(track.features[0].properties.timestamps), JSON.stringify([
    "2026-05-28T20:00:00Z",
    "2026-05-28T20:00:30Z",
  ]));
});

test("live fused track collapses only near-identical duplicate relay points", () => {
  const meshA = position({
    id: "mesh-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const meshDuplicate = position({
    id: "mesh-duplicate",
    lat: 40.00001,
    lon: -75.00001,
    timestamp: "2026-05-28T20:00:00.500Z",
    received_at: "2026-05-28T20:00:00.500Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const meshMoved = position({
    id: "mesh-moved",
    lat: 40.00006,
    lon: -75.00006,
    timestamp: "2026-05-28T20:00:01Z",
    received_at: "2026-05-28T20:00:01Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const display = displayPositionsForLiveTrack([meshA, meshDuplicate, meshMoved]);
  assert.equal(JSON.stringify(display.map((item) => item.id)), JSON.stringify(["mesh-duplicate", "mesh-moved"]));
});

test("live fused track collapses duplicate mesh packets by device sequence", () => {
  const mqttMesh = position({
    id: "mqtt-mesh",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:03Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
    mesh_seq_number: 42,
  });
  const relayMesh = position({
    id: "relay-mesh",
    lat: 40.0002,
    lon: -75.0002,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:01Z",
    source: "mesh_relay",
    device_id: "!tracker",
    mesh_seq_number: 42,
  });
  const nextMesh = position({
    id: "next-mesh",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:00:30Z",
    received_at: "2026-05-28T20:00:31Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
    mesh_seq_number: 43,
  });

  const display = displayPositionsForLiveTrack([mqttMesh, relayMesh, nextMesh]);
  assert.equal(JSON.stringify(display.map((item) => item.id)), JSON.stringify(["relay-mesh", "next-mesh"]));
});

test("live fused track falls back to timestamp distance duplicate logic when mesh sequence is missing", () => {
  const meshA = position({
    id: "mesh-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const meshDuplicate = position({
    id: "mesh-duplicate",
    lat: 40.00001,
    lon: -75.00001,
    timestamp: "2026-05-28T20:00:00.500Z",
    received_at: "2026-05-28T20:00:00.500Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const display = displayPositionsForLiveTrack([meshA, meshDuplicate]);
  assert.equal(JSON.stringify(display.map((item) => item.id)), JSON.stringify(["mesh-duplicate"]));
});

test("live fused track keeps cellular when a nearby mesh point is only a close tie", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const meshTie = position({
    id: "mesh-tie",
    lat: 40.00001,
    lon: -75.00001,
    timestamp: "2026-05-28T20:00:01Z",
    received_at: "2026-05-28T20:00:01Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const track = buildTrackCollection(new Map([["pilot:1", [appA, meshTie]]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track, null);
});

test("latest live position uses newest fix even when track fusion prefers another source", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const meshNewer = position({
    id: "mesh-newer",
    lat: 40.00001,
    lon: -75.00001,
    timestamp: "2026-05-28T20:00:01Z",
    received_at: "2026-05-28T20:00:01Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const latest = latestDisplayPositionsBySubject(new Map([["pilot:1", [appA, meshNewer]]])).get("pilot:1");
  assert.equal(latest.id, "mesh-newer");

  const track = buildTrackCollection(new Map([["pilot:1", [appA, meshNewer]]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track, null);
});
