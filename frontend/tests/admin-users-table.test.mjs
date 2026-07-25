import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

test("admin users creation date column is sortable", () => {
  const source = readFileSync(join(process.cwd(), "src/components/dashboard/AdminSection.tsx"), "utf8");
  assert.match(source, /UserSortField = [^;]*"created_at"/);
  assert.match(source, /case "created_at":\s*return dir \* a\.created_at\.localeCompare\(b\.created_at\)/);
  assert.match(source, /<SortHeader field="created_at" label="Created"/);
});
