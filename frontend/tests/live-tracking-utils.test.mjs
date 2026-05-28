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
    source: "app",
    device_id: null,
    battery_level: null,
    aircraft_icon: "hang_glider",
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

test("live track rendering splits across large timestamp and distance gaps", () => {
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
    ["home-start", "home-end"],
    ["bank-start", "bank-end"],
  ]));

  const track = buildTrackCollection(new Map([["pilot:1", positions]]), new Map([["pilot:1", "Mick Howard"]]));
  assert.equal(track.features.length, 2);
  assert.equal(JSON.stringify(track.features.map((feature) => feature.properties.segment_index)), JSON.stringify([0, 1]));
  assert.equal(JSON.stringify(track.features[0].geometry.coordinates), JSON.stringify([
    [-75.0, 40.0, 0],
    [-75.0005, 40.0005, 0],
  ]));
  assert.equal(JSON.stringify(track.features[1].geometry.coordinates), JSON.stringify([
    [-75.01, 40.01, 0],
    [-75.0105, 40.0105, 0],
  ]));
});
