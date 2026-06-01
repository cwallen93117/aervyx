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
const source = readFileSync(join(root, "src", "lib", "dateLabels.ts"), "utf8");
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

const { formatCalendarDateLabel } = module.exports;

test("date-only labels do not shift one day in western time zones", () => {
  assert.equal(formatCalendarDateLabel("2026-05-29"), "05/29/2026");
});

test("datetime labels still use normal locale formatting", () => {
  assert.equal(formatCalendarDateLabel("not-a-date"), "not-a-date");
  assert.notEqual(formatCalendarDateLabel("2026-05-29T12:00:00Z"), "-");
});
