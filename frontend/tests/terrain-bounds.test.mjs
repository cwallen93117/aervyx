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
const source = readFileSync(join(root, "src", "lib", "terrain-bounds.ts"), "utf8");
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
  require,
});

const {
  DEFAULT_TERRAIN_TILE_WARNING_THRESHOLD,
  collectTerrainBounds,
  estimateTerrainTileCount,
  intersectTerrainBounds,
  padTerrainBounds,
  terrainBoundsKey,
} = module.exports;

test("collectTerrainBounds unions tracks, task points, routes, and live positions with moderate padding", () => {
  const bounds = collectTerrainBounds({
    track: {
      features: [
        {
          geometry: {
            type: "LineString",
            coordinates: [
              [-105.0, 39.0, 2500],
              [-104.0, 40.0, 2600],
            ],
          },
        },
      ],
    },
    taskPoints: [{ latitude: 38.5, longitude: -104.5 }],
    optimizedRoute: [[-103.5, 39.5]],
    livePositions: [{ latitude: 40.5, longitude: -104.25 }],
  });

  assert.deepEqual(Array.from(bounds ?? []).map((value) => Number(value.toFixed(2))), [-105.15, 38.3, -103.35, 40.7]);
});

test("padTerrainBounds enforces a minimum buffer and clamps to Web Mercator limits", () => {
  const bounds = padTerrainBounds([179.99, 85.04, 180, 85.05]);
  assert.deepEqual(Array.from(bounds).map((value) => Number(value.toFixed(6))), [179.97, 85.02, 180, 85.051129]);
});

test("estimateTerrainTileCount counts intersected DEM tiles for the clipped viewport", () => {
  const terrainBounds = [-105, 39, -104, 40];
  const viewportBounds = [-104.8, 39.2, -104.2, 39.8];
  const clipped = intersectTerrainBounds(terrainBounds, viewportBounds);

  assert.equal(estimateTerrainTileCount(clipped, 8), 1);
  assert.equal(estimateTerrainTileCount(null, 8), 0);
});

test("terrainBoundsKey is stable for style source comparisons", () => {
  assert.equal(terrainBoundsKey([-105.123456, 39.1, -104.1, 40.987654]), "-105.12346,39.10000,-104.10000,40.98765");
  assert.equal(terrainBoundsKey(null), "global");
});

test("terrain warning threshold remains intentionally high enough for ordinary local views", () => {
  assert.equal(DEFAULT_TERRAIN_TILE_WARNING_THRESHOLD, 96);
  assert.equal(estimateTerrainTileCount([-105, 39, -104, 40], 10) < DEFAULT_TERRAIN_TILE_WARNING_THRESHOLD, true);
});
