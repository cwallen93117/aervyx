import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const root = process.cwd();
const page = readFileSync(join(root, "src/app/contact/page.tsx"), "utf8");
const marketing = readFileSync(join(root, "src/app/marketing/aervyx-body.html"), "utf8");

test("contact form sends only to the Aervyx inbox", () => {
  assert.match(page, /const CONTACT_EMAIL = "aervyxnet@gmail\.com"/);
  assert.match(page, /to: CONTACT_EMAIL/);
  assert.match(page, /process\.env\.GMAIL_APP_PASSWORD/);
  assert.match(page, /import "\.\.\/marketing\/aervyx-landing\.css"/);
  assert.match(page, /className="contact-page"/);
  assert.match(marketing, /href="\/contact">Contact</);
});
