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
const carBrowserModule = { exports: {} };
vm.runInNewContext(transpiled, {
  console,
  exports: module.exports,
  module,
  process: { env: {} },
  require,
  URL,
  window: undefined,
});
vm.runInNewContext(transpiled, {
  console,
  exports: carBrowserModule.exports,
  module: carBrowserModule,
  process: {
    env: {
      NEXT_PUBLIC_API_BASE_URL: "/backend",
      NEXT_PUBLIC_STREAM_API_BASE_URL: "https://api.aervyx.net",
    },
  },
  require,
  URL,
  window: { location: { hostname: "car.aervyx.net", protocol: "https:" } },
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
  colorForSubject,
  displaySegmentsForLiveTrack,
  displayPositionsForLiveTrack,
  latestDisplayPositionsBySubject,
  mergePositionGroup,
  segmentPositionsForLiveTrack,
} = module.exports;
const { adminDebugBatterySummary } = batteryModule.exports;

test("car hostname keeps live stream traffic on the same origin", () => {
  assert.equal(carBrowserModule.exports.resolveApiBase(), "/backend");
  assert.equal(carBrowserModule.exports.resolveStreamApiBase(), "/backend");
});

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

test("live display keeps delayed phone fixes for history without moving current marker backward", () => {
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
  assert.equal(JSON.stringify(displayPositionsForLiveTrack(merged.get("pilot:1")).map((item) => item.id)), JSON.stringify(["first", "delayed", "newer"]));
  assert.equal(latestDisplayPositionsBySubject(merged).get("pilot:1").id, "newer");

  const track = buildTrackCollection(merged, new Map([["pilot:1", "Mick Howard"]]));
  assert.equal(track, null);
});

test("phone-only 1 Hz live points produce one solid track", () => {
  const positions = [
    position({ id: "app-a", lat: 40.0, lon: -75.0, timestamp: "2026-05-28T20:00:00Z", received_at: "2026-05-28T20:00:00Z" }),
    position({ id: "app-b", lat: 40.0001, lon: -75.0001, timestamp: "2026-05-28T20:00:01Z", received_at: "2026-05-28T20:00:01Z" }),
    position({ id: "app-c", lat: 40.0002, lon: -75.0002, timestamp: "2026-05-28T20:00:02Z", received_at: "2026-05-28T20:00:02Z" }),
  ];

  const segments = displaySegmentsForLiveTrack(positions);
  assert.equal(segments.length, 1);
  assert.equal(segments[0].display_source, "cellular");
  assert.equal(segments[0].line_style, "solid");

  const track = buildTrackCollection(new Map([["pilot:1", positions]]), new Map([["pilot:1", "Mick Howard"]]));
  assert.equal(track.features.length, 1);
  assert.equal(track.features[0].properties.line_style, "solid");
  assert.equal(
    JSON.stringify(track.features[0].geometry.coordinates),
    JSON.stringify([
      [-75.0, 40.0, 0],
      [-75.0001, 40.0001, 0],
      [-75.0002, 40.0002, 0],
    ]),
  );
});

test("phone outage with mesh points produces solid phone and dashed mesh-fill segments", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const appB = position({
    id: "app-b",
    lat: 40.0001,
    lon: -75.0001,
    timestamp: "2026-05-28T20:00:01Z",
    received_at: "2026-05-28T20:00:01Z",
  });
  const meshGapA = position({
    id: "mesh-gap-a",
    lat: 40.0004,
    lon: -75.0004,
    timestamp: "2026-05-28T20:00:04Z",
    received_at: "2026-05-28T20:00:04Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const meshGapB = position({
    id: "mesh-gap-b",
    lat: 40.0006,
    lon: -75.0006,
    timestamp: "2026-05-28T20:00:06Z",
    received_at: "2026-05-28T20:00:06Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const appC = position({
    id: "app-c",
    lat: 40.0008,
    lon: -75.0008,
    timestamp: "2026-05-28T20:00:08Z",
    received_at: "2026-05-28T20:00:08Z",
  });
  const appD = position({
    id: "app-d",
    lat: 40.0009,
    lon: -75.0009,
    timestamp: "2026-05-28T20:00:09Z",
    received_at: "2026-05-28T20:00:09Z",
  });

  const positions = [appA, appB, meshGapA, meshGapB, appC, appD];
  const segments = displaySegmentsForLiveTrack(positions);
  assert.equal(JSON.stringify(segments.map((segment) => segment.positions.map((item) => item.id))), JSON.stringify([
    ["app-a", "app-b"],
    ["app-b", "mesh-gap-a", "mesh-gap-b", "app-c"],
    ["app-c", "app-d"],
  ]));
  assert.equal(JSON.stringify(segments.map((segment) => segment.line_style)), JSON.stringify(["solid", "dashed", "solid"]));

  const track = buildTrackCollection(new Map([["pilot:1", positions]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.line_style)), JSON.stringify(["solid", "dashed", "solid"]));
});

test("phone outage without mesh creates a visual gap instead of a connector", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const appB = position({
    id: "app-b",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:00:10Z",
    received_at: "2026-05-28T20:00:10Z",
  });

  assert.equal(displaySegmentsForLiveTrack([appA, appB]).length, 0);
  assert.equal(buildTrackCollection(new Map([["pilot:1", [appA, appB]]]), new Map([["pilot:1", "Charles Allen"]]), ["pilot:1"]), null);
  assert.equal(latestDisplayPositionsBySubject(new Map([["pilot:1", [appA, appB]]])).get("pilot:1").id, "app-b");
});

test("recent phone reception holds newer mesh briefly before using it", () => {
  const appA = position({
    id: "app-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:00Z",
  });
  const meshNewer = position({
    id: "mesh-newer",
    lat: 40.0003,
    lon: -75.0003,
    timestamp: "2026-05-28T20:00:03Z",
    received_at: "2026-05-28T20:00:01Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });

  const heldNow = Date.parse("2026-05-28T20:00:01.200Z");
  const eligibleNow = Date.parse("2026-05-28T20:00:02.600Z");
  assert.equal(JSON.stringify(displayPositionsForLiveTrack([appA, meshNewer], { nowMs: heldNow }).map((item) => item.id)), JSON.stringify(["app-a"]));
  assert.equal(JSON.stringify(displayPositionsForLiveTrack([appA, meshNewer], { nowMs: eligibleNow }).map((item) => item.id)), JSON.stringify(["app-a", "mesh-newer"]));
  const track = buildTrackCollection(new Map([["pilot:1", [appA, meshNewer]]]), new Map([["pilot:1", "Charles Allen"]]), ["pilot:1"], { nowMs: eligibleNow });
  assert.equal(track.features[0].properties.line_style, "dashed");
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

test("visible live tracks keep colors from the full active subject order", () => {
  const secondPilotStart = {
    ...position({
      id: "second-pilot-start",
      lat: 40.01,
      lon: -75.01,
      timestamp: "2026-05-28T20:00:00Z",
      received_at: "2026-05-28T20:00:00Z",
    }),
    pilot_id: 2,
  };
  const secondPilotEnd = {
    ...position({
      id: "second-pilot-end",
      lat: 40.011,
      lon: -75.011,
      timestamp: "2026-05-28T20:00:01Z",
      received_at: "2026-05-28T20:00:01Z",
    }),
    pilot_id: 2,
  };

  const activeSubjects = ["pilot:1", "pilot:2"];
  const visibleTrack = buildTrackCollection(
    new Map([["pilot:2", [secondPilotStart, secondPilotEnd]]]),
    new Map([["pilot:2", "Second Pilot"]]),
    activeSubjects,
  );

  assert.equal(colorForSubject("pilot:2", activeSubjects), "#dc2626");
  assert.equal(visibleTrack.features[0].properties.color, "#dc2626");
});

test("delayed buffered phone points replace mesh fill when history is rebuilt", () => {
  const meshGap = position({
    id: "mesh-gap",
    lat: 40.0004,
    lon: -75.0004,
    timestamp: "2026-05-28T20:00:04Z",
    received_at: "2026-05-28T20:00:04Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
  });
  const cellular = Array.from({ length: 9 }, (_, index) => position({
    id: `app-${index}`,
    lat: 40 + index * 0.0001,
    lon: -75 - index * 0.0001,
    timestamp: `2026-05-28T20:00:0${index}Z`,
    received_at: index < 2 || index > 6 ? `2026-05-28T20:00:0${index}Z` : "2026-05-28T20:01:00Z",
  }));

  const track = buildTrackCollection(new Map([["pilot:1", [...cellular, meshGap]]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track.features.length, 1);
  assert.equal(track.features[0].properties.line_style, "solid");
  assert.equal(track.features[0].geometry.coordinates.length, 9);
});

test("mesh-only pilot track remains continuous with mesh sequence ordering", () => {
  const meshA = position({
    id: "mesh-a",
    lat: 40.0,
    lon: -75.0,
    timestamp: "2026-05-28T20:00:00Z",
    received_at: "2026-05-28T20:00:03Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
    mesh_seq_number: 11,
  });
  const meshB = position({
    id: "mesh-b",
    lat: 40.001,
    lon: -75.001,
    timestamp: "2026-05-28T20:00:30Z",
    received_at: "2026-05-28T20:00:31Z",
    source: "mqtt_gateway",
    device_id: "!tracker",
    mesh_seq_number: 12,
  });

  const track = buildTrackCollection(new Map([["pilot:1", [meshB, meshA]]]), new Map([["pilot:1", "Charles Allen"]]));
  assert.equal(track.features.length, 1);
  assert.equal(track.features[0].properties.line_style, "dashed");
  assert.equal(JSON.stringify(track.features[0].properties.timestamps), JSON.stringify(["2026-05-28T20:00:00Z", "2026-05-28T20:00:30Z"]));
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
