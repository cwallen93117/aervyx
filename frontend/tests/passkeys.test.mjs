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
const source = readFileSync(join(root, "src", "lib", "passkeys.ts"), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const module = { exports: {} };
vm.runInNewContext(transpiled, {
  atob,
  btoa,
  exports: module.exports,
  module,
  require,
  Uint8Array,
});

test("passkey base64url encoding round-trips binary credential values", () => {
  const original = Uint8Array.from([0, 1, 2, 250, 251, 252, 255]).buffer;
  const encoded = module.exports.encodeBase64Url(original);
  assert.equal(encoded, "AAEC-vv8_w");
  assert.deepEqual(
    Array.from(new Uint8Array(module.exports.decodeBase64Url(encoded))),
    Array.from(new Uint8Array(original)),
  );
});

test("login uses conditional mediation and WebAuthn autofill", () => {
  const login = readFileSync(join(root, "src", "app", "login", "page.tsx"), "utf8");
  assert.match(login, /authenticateWithPasskey\("conditional"/);
  assert.match(login, /autoComplete="username webauthn"/);
  assert.match(login, /Sign in with a passkey/);
});

test("passkey setup is only shown in account settings", () => {
  const dashboard = readFileSync(join(root, "src", "app", "dashboard", "page.tsx"), "utf8");
  const settings = readFileSync(join(root, "src", "components", "dashboard", "PasskeyManager.tsx"), "utf8");
  assert.doesNotMatch(dashboard, /Set up a passkey|Not now/);
  assert.match(settings, /Add passkey/);
});

test("Android asset link matches the release application and certificate", () => {
  const assetLinks = JSON.parse(readFileSync(join(root, "public", ".well-known", "assetlinks.json"), "utf8"));
  assert.equal(assetLinks[0].target.package_name, "com.aervyx.aervyx_mobile");
  assert.equal(
    assetLinks[0].target.sha256_cert_fingerprints[0],
    "2B:E7:99:3F:B2:CA:76:E3:F8:6B:F4:FA:31:E1:B4:99:28:50:3E:96:00:9E:31:54:EC:BD:4D:D3:77:91:0D:EF",
  );
});
