const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ctx = {
  crypto: require("node:crypto").webcrypto,
  Uint8Array,
  Map,
  window: {},
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("assets/release.js", "utf8"), ctx);
vm.runInContext(fs.readFileSync("assets/firmware-core.js", "utf8"), ctx);
const core = ctx.window.GCFirmware,
  release = ctx.window.GCRelease;
test("browser release exactly matches pinned bundle and generated output", async () => {
  const pinned = JSON.parse(fs.readFileSync(release.bundle));
  assert.equal(release.version, pinned.version);
  assert.deepEqual(
    JSON.parse(JSON.stringify(release.patchBundle.patches)),
    pinned.patches,
  );
  const stock = new core.HexFile(fs.readFileSync("testdata/gc326.hex", "utf8"));
  assert.equal(await core.canonicalHash(stock), release.baseHash);
  const original = new Map(
    [...stock.index.keys()].map((a) => [a, stock.readByte(a)]),
  );
  core.applyBundle(stock, release.patchBundle);
  const patched = new Set();
  for (const p of pinned.patches) {
    const b = Buffer.from(p.bytes, "hex"),
      a = parseInt(p.addr, 16);
    b.forEach((v, i) => {
      assert.equal(stock.readByte(a + i), v);
      patched.add(a + i);
    });
  }
  for (const [a, v] of original)
    if (!patched.has(a)) assert.equal(stock.readByte(a), v);
  new core.HexFile(stock.toString());
});
test("firmware-generated CC pattern is decoded independently by browser codec", () => {
  const F = require("../../assets/pattern-format.js");
  if (!fs.existsSync("testdata/cc-pattern.fixture.txt"))
    throw new Error(
      "Run tools/test_cc_automation.py to generate the interoperability fixture",
    );
  const p = F.decode(fs.readFileSync("testdata/cc-pattern.fixture.txt"));
  assert.equal(p.source, "GCP1+GCC1");
  assert.deepEqual(p.ccSources[74], { input: 1, min: 0, max: 127 });
  assert.deepEqual(p.steps[1].cc, [[74, 0]]);
  assert.deepEqual(p.steps[2].cc, [[74, 127]]);
  const q = F.decode(F.encode(p));
  assert.deepEqual(q.steps, p.steps);
});
